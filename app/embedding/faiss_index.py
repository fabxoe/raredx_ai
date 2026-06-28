import json
from pathlib import Path
from typing import Any

import numpy as np

from app.embedding.biomedical import BiomedicalEmbedder, phenotype_text
from app.retrieval.knowledge import KnowledgeIndex
from app.schemas.retrieval import CandidateDisease, MatchedPhenotype, ScoreComponents


class DiseaseEmbeddingIndex:
    def __init__(self, knowledge: KnowledgeIndex, embedder: BiomedicalEmbedder) -> None:
        self.knowledge = knowledge
        self.embedder = embedder
        self._index: object | None = None
        self._disease_ids: list[str] = []
        self._vectors: np.ndarray | None = None

    def build(self, cache_dir: Path | None = None) -> None:
        disease_ids: list[str] = []
        vectors: list[np.ndarray] = []
        phenotype_vectors = self._load_or_build_phenotype_vector_cache(cache_dir)
        for disease_id, profile in self.knowledge.disease_profiles.items():
            term_vectors = [phenotype_vectors[hpo_id] for hpo_id in sorted(profile.phenotype_ids) if hpo_id in phenotype_vectors]
            if not term_vectors:
                continue
            disease_vector = np.vstack(term_vectors).mean(axis=0)
            disease_vector = _normalize(disease_vector)
            disease_ids.append(disease_id)
            vectors.append(disease_vector)

        if not vectors:
            raise ValueError("cannot build FAISS index without disease embeddings")

        matrix = np.vstack(vectors).astype(np.float32)
        self._vectors = matrix
        self._disease_ids = disease_ids
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

    def search(self, hpo_terms: list[str], top_k: int) -> list[CandidateDisease]:
        if self._index is None:
            self.build()
        query_texts = [self._text_for_hpo(hpo_id) for hpo_id in hpo_terms]
        query_texts = [text for text in query_texts if text]
        if not query_texts:
            return []

        query_vectors = self.embedder.encode(query_texts)
        query_vector = _normalize(query_vectors.mean(axis=0)).astype(np.float32).reshape(1, -1)
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

    def _text_for_hpo(self, hpo_id: str) -> str | None:
        term = self.knowledge.phenotypes.get(hpo_id)
        if not term:
            return None
        return phenotype_text(term.name, term.definition)

    def _build_phenotype_vector_cache(self) -> dict[str, np.ndarray]:
        hpo_ids = sorted(
            {
                hpo_id
                for profile in self.knowledge.disease_profiles.values()
                for hpo_id in profile.phenotype_ids
                if hpo_id in self.knowledge.phenotypes
            }
        )
        texts = [self._text_for_hpo(hpo_id) or hpo_id for hpo_id in hpo_ids]
        vectors = self.embedder.encode(texts)
        return {hpo_id: vectors[index] for index, hpo_id in enumerate(hpo_ids)}

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


def _build_inner_product_index(matrix: np.ndarray) -> object:
    import faiss

    index = faiss.IndexFlatIP(matrix.shape[1])
    index.add(matrix)
    return index


def _normalize(vector: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vector)
    if norm == 0:
        return vector
    return vector / norm
