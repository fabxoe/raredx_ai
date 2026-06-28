from __future__ import annotations

import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from app.retrieval.knowledge import KnowledgeIndex
from app.schemas.retrieval import CandidateDisease, MatchedPhenotype, ScoreComponents


class HPOGraphEmbeddingIndex:
    def __init__(
        self,
        knowledge: KnowledgeIndex,
        *,
        dimensions: int = 128,
        walk_length: int = 20,
        walks_per_node: int = 8,
        window_size: int = 4,
        seed: int = 13,
        walk_strategy: str = "deepwalk",
        return_param: float = 1.0,
        in_out_param: float = 0.5,
    ) -> None:
        self.knowledge = knowledge
        self.dimensions = dimensions
        self.walk_length = walk_length
        self.walks_per_node = walks_per_node
        self.window_size = window_size
        self.seed = seed
        self.walk_strategy = walk_strategy
        self.return_param = return_param
        self.in_out_param = in_out_param
        self._index: object | None = None
        self._disease_ids: list[str] = []
        self._vectors: np.ndarray | None = None
        self._phenotype_vectors: dict[str, np.ndarray] | None = None

    def build(self, cache_dir: Path | None = None) -> None:
        phenotype_vectors = self._load_or_build_phenotype_vector_cache(cache_dir)
        disease_ids: list[str] = []
        vectors: list[np.ndarray] = []
        for disease_id, profile in self.knowledge.disease_profiles.items():
            term_vectors = [phenotype_vectors[hpo_id] for hpo_id in sorted(profile.phenotype_ids) if hpo_id in phenotype_vectors]
            if not term_vectors:
                continue
            disease_vector = _normalize(np.vstack(term_vectors).mean(axis=0))
            disease_ids.append(disease_id)
            vectors.append(disease_vector)

        if not vectors:
            raise ValueError("cannot build FAISS index without disease graph embeddings")

        matrix = np.vstack(vectors).astype(np.float32)
        self._vectors = matrix
        self._disease_ids = disease_ids
        self._phenotype_vectors = phenotype_vectors
        self._index = _build_inner_product_index(matrix)

    def save(self, output_dir: Path, *, manifest: dict[str, Any] | None = None) -> None:
        if self._index is None:
            raise RuntimeError("index must be built before saving")
        output_dir.mkdir(parents=True, exist_ok=True)
        import faiss

        faiss.write_index(self._index, str(output_dir / "disease.faiss"))
        (output_dir / "disease_ids.json").write_text(json.dumps(self._disease_ids, indent=2), encoding="utf-8")
        if manifest is not None:
            (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def load(self, input_dir: Path) -> None:
        import faiss

        self._index = faiss.read_index(str(input_dir / "disease.faiss"))
        self._disease_ids = json.loads((input_dir / "disease_ids.json").read_text(encoding="utf-8"))
        cache_dir = input_dir / "hpo_cache"
        if (cache_dir / "hpo_ids.json").exists() and (cache_dir / "hpo_vectors.npz").exists():
            self._phenotype_vectors = self._load_or_build_phenotype_vector_cache(cache_dir)

    def search(self, hpo_terms: list[str], top_k: int) -> list[CandidateDisease]:
        if self._index is None:
            self.build()
        if self._phenotype_vectors is None:
            self._phenotype_vectors = self._build_phenotype_vector_cache()

        term_vectors = [self._phenotype_vectors[hpo_id] for hpo_id in hpo_terms if hpo_id in self._phenotype_vectors]
        if not term_vectors:
            return []

        query_vector = _normalize(np.vstack(term_vectors).mean(axis=0)).astype(np.float32).reshape(1, -1)
        scores, indexes = self._index.search(query_vector, top_k)
        candidates: list[CandidateDisease] = []
        query_set = set(hpo_terms)

        for score, index in zip(scores[0].tolist(), indexes[0].tolist(), strict=False):
            if index < 0:
                continue
            disease_id = self._disease_ids[index]
            profile = self.knowledge.disease_profiles[disease_id]
            matched = query_set.intersection(profile.phenotype_ids)
            candidates.append(
                CandidateDisease(
                    disease_id=disease_id,
                    disease_name=profile.disease_name,
                    score=float(score),
                    score_components=ScoreComponents(embedding_score=float(score)),
                    matched_phenotypes=[
                        MatchedPhenotype(hpo_id=hpo_id, name=self.knowledge.get_phenotype_name(hpo_id))
                        for hpo_id in sorted(matched)
                    ],
                    missing_phenotypes=[
                        MatchedPhenotype(hpo_id=hpo_id, name=self.knowledge.get_phenotype_name(hpo_id))
                        for hpo_id in sorted(query_set.difference(profile.phenotype_ids))
                    ],
                    associated_genes=sorted(self.knowledge.disease_genes.get(disease_id, set())),
                )
            )
        return candidates

    def _load_or_build_phenotype_vector_cache(self, cache_dir: Path | None) -> dict[str, np.ndarray]:
        if cache_dir is None:
            return self._build_phenotype_vector_cache()

        hpo_ids_path = cache_dir / "hpo_ids.json"
        vectors_path = cache_dir / "hpo_vectors.npz"
        if hpo_ids_path.exists() and vectors_path.exists():
            hpo_ids = json.loads(hpo_ids_path.read_text(encoding="utf-8"))
            vectors = np.load(vectors_path)["vectors"]
            return {hpo_id: vectors[index] for index, hpo_id in enumerate(hpo_ids)}

        cache_dir.mkdir(parents=True, exist_ok=True)
        vectors_by_hpo = self._build_phenotype_vector_cache()
        hpo_ids = sorted(vectors_by_hpo)
        vectors = np.vstack([vectors_by_hpo[hpo_id] for hpo_id in hpo_ids]).astype(np.float32)
        np.savez_compressed(vectors_path, vectors=vectors)
        hpo_ids_path.write_text(json.dumps(hpo_ids, indent=2), encoding="utf-8")
        return vectors_by_hpo

    def _build_phenotype_vector_cache(self) -> dict[str, np.ndarray]:
        adjacency = _hpo_adjacency(self.knowledge)
        hpo_ids = sorted(
            {
                hpo_id
                for profile in self.knowledge.disease_profiles.values()
                for hpo_id in profile.phenotype_ids
                if hpo_id in self.knowledge.phenotypes
            }
        )
        vectors: dict[str, np.ndarray] = {hpo_id: np.zeros(self.dimensions, dtype=np.float32) for hpo_id in hpo_ids}
        context_vector_cache: dict[str, np.ndarray] = {}
        rng = random.Random(self.seed)
        for hpo_id in hpo_ids:
            for _ in range(self.walks_per_node):
                walk = _random_walk(
                    hpo_id,
                    adjacency,
                    self.walk_length,
                    rng,
                    strategy=self.walk_strategy,
                    return_param=self.return_param,
                    in_out_param=self.in_out_param,
                )
                _add_walk_context(vectors, walk, self.window_size, self.dimensions, context_vector_cache)
        return {
            hpo_id: _normalize(vector if np.linalg.norm(vector) > 0 else _hashed_context_vector(hpo_id, self.dimensions, context_vector_cache))
            for hpo_id, vector in vectors.items()
        }


def _hpo_adjacency(knowledge: KnowledgeIndex) -> dict[str, list[str]]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    for hpo_id, term in knowledge.phenotypes.items():
        adjacency.setdefault(hpo_id, set())
        for parent in term.parents:
            if parent in knowledge.phenotypes:
                adjacency[hpo_id].add(parent)
                adjacency[parent].add(hpo_id)
    return {hpo_id: sorted(neighbors) for hpo_id, neighbors in adjacency.items()}


def _random_walk(
    start: str,
    adjacency: dict[str, list[str]],
    walk_length: int,
    rng: random.Random,
    *,
    strategy: str,
    return_param: float,
    in_out_param: float,
) -> list[str]:
    walk = [start]
    current = start
    for _ in range(max(walk_length - 1, 0)):
        neighbors = adjacency.get(current) or []
        if not neighbors:
            break
        if strategy == "node2vec" and len(walk) > 1:
            current = _node2vec_next_node(
                previous=walk[-2],
                current=current,
                neighbors=neighbors,
                adjacency=adjacency,
                rng=rng,
                return_param=return_param,
                in_out_param=in_out_param,
            )
        else:
            current = rng.choice(neighbors)
        walk.append(current)
    return walk


def _node2vec_next_node(
    *,
    previous: str,
    current: str,
    neighbors: list[str],
    adjacency: dict[str, list[str]],
    rng: random.Random,
    return_param: float,
    in_out_param: float,
) -> str:
    previous_neighbors = set(adjacency.get(previous) or [])
    weights: list[float] = []
    for neighbor in neighbors:
        if neighbor == previous:
            weight = 1.0 / max(return_param, 1e-9)
        elif neighbor in previous_neighbors:
            weight = 1.0
        else:
            weight = 1.0 / max(in_out_param, 1e-9)
        weights.append(weight)
    return _weighted_choice(neighbors, weights, rng)


def _weighted_choice(items: list[str], weights: list[float], rng: random.Random) -> str:
    total = sum(weights)
    if total <= 0:
        return rng.choice(items)
    threshold = rng.random() * total
    cumulative = 0.0
    for item, weight in zip(items, weights, strict=True):
        cumulative += weight
        if cumulative >= threshold:
            return item
    return items[-1]


def _add_walk_context(
    vectors: dict[str, np.ndarray],
    walk: list[str],
    window_size: int,
    dimensions: int,
    context_vector_cache: dict[str, np.ndarray],
) -> None:
    for center_index, center in enumerate(walk):
        if center not in vectors:
            continue
        start = max(0, center_index - window_size)
        end = min(len(walk), center_index + window_size + 1)
        for context_index in range(start, end):
            if context_index == center_index:
                continue
            distance = abs(context_index - center_index)
            context = walk[context_index]
            vectors[center] += _hashed_context_vector(context, dimensions, context_vector_cache) / distance


def _hashed_context_vector(hpo_id: str, dimensions: int, cache: dict[str, np.ndarray]) -> np.ndarray:
    cached = cache.get(hpo_id)
    if cached is not None:
        return cached
    seed = int.from_bytes(hashlib.sha256(hpo_id.encode("utf-8")).digest()[:8], "big", signed=False)
    rng = np.random.default_rng(seed)
    vector = rng.normal(0.0, 1.0, dimensions).astype(np.float32)
    cache[hpo_id] = vector
    return vector


def _build_inner_product_index(matrix: np.ndarray) -> object:
    try:
        import faiss
    except ModuleNotFoundError:
        return _NumpyInnerProductIndex(matrix)

    index = faiss.IndexFlatIP(matrix.shape[1])
    index.add(matrix)
    return index


class _NumpyInnerProductIndex:
    def __init__(self, matrix: np.ndarray) -> None:
        self.matrix = matrix

    def search(self, query_vector: np.ndarray, top_k: int) -> tuple[np.ndarray, np.ndarray]:
        scores = query_vector @ self.matrix.T
        order = np.argsort(-scores, axis=1)[:, :top_k]
        sorted_scores = np.take_along_axis(scores, order, axis=1)
        return sorted_scores.astype(np.float32), order.astype(np.int64)


def _normalize(vector: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vector)
    if norm == 0:
        return vector
    return vector / norm
