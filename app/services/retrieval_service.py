from functools import cached_property
from pathlib import Path

from app.config import Settings
from app.embedding.backends import (
    DEFAULT_EMBEDDING_BACKEND,
    index_dir_name,
    resolve_embedding_model,
    supported_embedding_backend_keys,
)
from app.embedding.biomedical import BiomedicalEmbedder
from app.embedding.faiss_index import DiseaseEmbeddingIndex
from app.etl.processed_store import load_processed_knowledge_base
from app.llm.phenotype_qc import PhenotypeLLMSelector, build_phenotype_llm_selector
from app.reranking.hybrid import HybridReranker
from app.retrieval.doc2hpo_mapper import Doc2HPOMapper
from app.retrieval.ic_baseline import ICBaselineRanker
from app.retrieval.knowledge import KnowledgeIndex
from app.retrieval.note_matcher import ClinicalNoteMatcher, ExtractedPhenotype
from app.retrieval.original_hpo_mapper import OriginalHPOMapperAdapter
from app.schemas.retrieval import CandidateDisease


class RetrievalService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._embedding_indexes: dict[tuple[str, str], DiseaseEmbeddingIndex] = {}

    @cached_property
    def knowledge(self) -> KnowledgeIndex:
        return KnowledgeIndex(load_processed_knowledge_base(self.settings.processed_dir))

    @cached_property
    def ic_ranker(self) -> ICBaselineRanker:
        return ICBaselineRanker(self.knowledge)

    def embedding_index(self, options: dict[str, str | int | float | bool] | None = None) -> DiseaseEmbeddingIndex:
        ranking_options = options or {}
        backend = str(ranking_options.get("embedding_backend") or DEFAULT_EMBEDDING_BACKEND)
        requested_model = str(ranking_options.get("embedding_model") or "").strip() or None
        model_name = resolve_embedding_model(backend, requested_model)
        cache_key = (backend, model_name)
        cached = self._embedding_indexes.get(cache_key)
        if cached is not None:
            return cached

        index = DiseaseEmbeddingIndex(self.knowledge, BiomedicalEmbedder(model_name))
        index_dir = self._embedding_index_dir(backend, model_name)
        legacy_index_dir = self.settings.processed_dir / "faiss"
        if _faiss_index_exists(index_dir):
            index.load(index_dir)
        elif backend == DEFAULT_EMBEDDING_BACKEND and _faiss_index_exists(legacy_index_dir):
            index.load(legacy_index_dir)
        self._embedding_indexes[cache_key] = index
        return index

    @cached_property
    def reranker(self) -> HybridReranker:
        return HybridReranker(
            ic_weight=self.settings.ic_weight,
            embedding_weight=self.settings.embedding_weight,
            graph_weight=self.settings.graph_weight,
        )

    @cached_property
    def note_matcher(self) -> ClinicalNoteMatcher:
        return ClinicalNoteMatcher(self.knowledge)

    @cached_property
    def doc2hpo_mapper(self) -> Doc2HPOMapper:
        return Doc2HPOMapper(
            knowledge=self.knowledge,
            endpoint_url=self.settings.doc2hpo_url,
            timeout_seconds=self.settings.doc2hpo_timeout_seconds,
            source="doc2hpo",
            llm_selector_factory=self.build_llm_selector,
        )

    @cached_property
    def original_hpo_mapper(self) -> OriginalHPOMapperAdapter:
        return OriginalHPOMapperAdapter(
            knowledge=self.knowledge,
            endpoint_url=self.settings.original_hpo_mapper_url,
            timeout_seconds=self.settings.doc2hpo_timeout_seconds,
            source="original_hpo_mapper",
            llm_selector_factory=self.build_llm_selector,
        )

    def build_llm_selector(self, options: dict[str, str | int | float | bool]) -> PhenotypeLLMSelector | None:
        provider = str(options.get("llm_provider") or self.settings.llm_provider).strip().lower()
        if provider == "off":
            return None
        model = str(options.get("chat_model") or "").strip() or None
        return build_phenotype_llm_selector(self.settings, provider_override=provider, model_override=model)

    def extract_hpo_terms(
        self,
        clinical_note: str,
        limit: int = 30,
        mapper_mode: str = "dictionary",
        mapper_options: dict[str, str | int | float | bool] | None = None,
    ) -> list[ExtractedPhenotype]:
        options = mapper_options or {}
        if mapper_mode == "off":
            raise ValueError("hpo_mapper is off; use HPO terms input or enable a mapper")
        if mapper_mode == "dictionary":
            return self.note_matcher.extract(clinical_note, limit=limit)
        if mapper_mode == "doc2hpo":
            return self.doc2hpo_mapper.extract(clinical_note, limit=limit, options=options)
        if mapper_mode == "original_hpo_mapper":
            return self.original_hpo_mapper.extract(clinical_note, limit=limit, options=options)
        if mapper_mode == "dictionary_doc2hpo":
            return _merge_extracted(
                [
                    *self.note_matcher.extract(clinical_note, limit=limit),
                    *self.doc2hpo_mapper.extract(clinical_note, limit=limit, options=options),
                ],
                limit=limit,
            )
        raise ValueError(f"unsupported hpo_mapper: {mapper_mode}")

    def search_phenotypes(self, query: str, limit: int = 10) -> list[tuple[str, str]]:
        normalized = query.strip().lower()
        if not normalized:
            return []
        exact: list[tuple[str, str]] = []
        partial: list[tuple[str, str]] = []
        for hpo_id, term in self.knowledge.phenotypes.items():
            name = term.name.lower()
            if normalized == hpo_id.lower() or normalized == name:
                exact.append((hpo_id, term.name))
            elif normalized in hpo_id.lower() or normalized in name:
                partial.append((hpo_id, term.name))
        partial.sort(key=lambda item: (not item[1].lower().startswith(normalized), len(item[1]), item[1]))
        return (exact + partial)[:limit]

    def rank_ic(
        self,
        hpo_terms: list[str],
        top_k: int,
        options: dict[str, str | int | float | bool] | None = None,
    ) -> list[CandidateDisease]:
        _validate_ic_options(options or {})
        self._validate_hpo_terms(hpo_terms)
        return self.ic_ranker.rank(hpo_terms, top_k)

    def rank_embedding(
        self,
        hpo_terms: list[str],
        top_k: int,
        options: dict[str, str | int | float | bool] | None = None,
    ) -> list[CandidateDisease]:
        ranking_options = options or {}
        _validate_embedding_options(ranking_options)
        self._validate_hpo_terms(hpo_terms)
        return self.embedding_index(ranking_options).search(hpo_terms, top_k)

    def rank_graph(
        self,
        hpo_terms: list[str],
        top_k: int,
        options: dict[str, str | int | float | bool] | None = None,
    ) -> list[CandidateDisease]:
        ranking_options = options or {}
        _validate_graph_options(ranking_options)
        self._validate_hpo_terms(hpo_terms)
        return self._graph_evidence_rank(hpo_terms, top_k, ranking_options)

    def rank_hybrid(
        self,
        hpo_terms: list[str],
        top_k: int,
        options: dict[str, str | int | float | bool] | None = None,
    ) -> list[CandidateDisease]:
        ranking_options = options or {}
        _validate_embedding_options(ranking_options)
        _validate_graph_options(ranking_options)
        self._validate_hpo_terms(hpo_terms)
        ic_candidates = self.rank_ic(hpo_terms, max(top_k * 3, 30), options=ranking_options)
        embedding_candidates = self.rank_embedding(hpo_terms, max(top_k * 3, 30), options=ranking_options)
        graph_candidates = self._graph_evidence_rank(hpo_terms, max(top_k * 3, 30), ranking_options)
        reranker = self._reranker_for_options(ranking_options)
        return reranker.rerank(ic_candidates, embedding_candidates, graph_candidates, top_k)

    def _reranker_for_options(self, options: dict[str, str | int | float | bool]) -> HybridReranker:
        if not any(key in options for key in ("ic_weight", "embedding_weight", "graph_weight")):
            return self.reranker
        return HybridReranker(
            ic_weight=_float_option(options, "ic_weight", self.settings.ic_weight),
            embedding_weight=_float_option(options, "embedding_weight", self.settings.embedding_weight),
            graph_weight=_float_option(options, "graph_weight", self.settings.graph_weight),
        )

    def _embedding_index_dir(self, backend: str, model_name: str) -> Path:
        return self.settings.processed_dir / "faiss" / index_dir_name(backend, model_name)

    def _graph_evidence_rank(
        self,
        hpo_terms: list[str],
        top_k: int,
        options: dict[str, str | int | float | bool],
    ) -> list[CandidateDisease]:
        mode = str(options.get("graph_evidence_mode") or "local_overlap")
        candidates = self.ic_ranker.rank(hpo_terms, max(top_k, 100))
        query_size = len(set(hpo_terms)) or 1
        for candidate in candidates:
            graph_score = self._graph_evidence_score(candidate, hpo_terms, mode)
            candidate.score = graph_score
            candidate.score_components.graph_score = graph_score
            candidate.graph_paths = [
                f"Patient -> {phenotype.hpo_id} -> {candidate.disease_id}"
                for phenotype in candidate.matched_phenotypes
            ]
        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates[:top_k]

    def _graph_evidence_score(self, candidate: CandidateDisease, hpo_terms: list[str], mode: str) -> float:
        if mode == "local_overlap":
            return len(candidate.matched_phenotypes) / (len(set(hpo_terms)) or 1)
        if mode == "frequency_weighted_graph":
            return self._frequency_weighted_graph_score(candidate, hpo_terms)
        if mode == "gene_path":
            return self._gene_path_graph_score(candidate, hpo_terms)
        if mode == "source_confidence_graph":
            return self._source_confidence_graph_score(candidate, hpo_terms)
        raise ValueError(f"unsupported graph evidence mode: {mode}")

    def _frequency_weighted_graph_score(self, candidate: CandidateDisease, hpo_terms: list[str]) -> float:
        annotations = self.knowledge.disease_annotations.get(candidate.disease_id, [])
        annotation_by_hpo = {annotation.hpo_id: annotation for annotation in annotations}
        weights = [
            _frequency_weight(annotation_by_hpo[hpo_id].frequency)
            for hpo_id in set(hpo_terms)
            if hpo_id in annotation_by_hpo
        ]
        return sum(weights) / (len(set(hpo_terms)) or 1)

    def _gene_path_graph_score(self, candidate: CandidateDisease, hpo_terms: list[str]) -> float:
        by_hpo = self.knowledge.disease_gene_phenotypes.get(candidate.disease_id, {})
        matched_support = sum(1 for hpo_id in set(hpo_terms) if by_hpo.get(hpo_id))
        overlap_score = matched_support / (len(set(hpo_terms)) or 1)
        disease_gene_count = max(len(self.knowledge.disease_genes.get(candidate.disease_id, set())), 1)
        matched_gene_count = len(set().union(*(by_hpo.get(hpo_id, set()) for hpo_id in set(hpo_terms)))) if by_hpo else 0
        gene_specificity = min(1.0, matched_gene_count / disease_gene_count)
        return 0.7 * overlap_score + 0.3 * gene_specificity

    def _source_confidence_graph_score(self, candidate: CandidateDisease, hpo_terms: list[str]) -> float:
        annotations = self.knowledge.disease_annotations.get(candidate.disease_id, [])
        annotation_by_hpo = {annotation.hpo_id: annotation for annotation in annotations}
        weights = [
            _source_confidence_weight(annotation_by_hpo[hpo_id].evidence, annotation_by_hpo[hpo_id].source)
            for hpo_id in set(hpo_terms)
            if hpo_id in annotation_by_hpo
        ]
        return sum(weights) / (len(set(hpo_terms)) or 1)

    def _validate_hpo_terms(self, hpo_terms: list[str]) -> None:
        unknown = [hpo_id for hpo_id in hpo_terms if hpo_id not in self.knowledge.phenotypes]
        if unknown:
            raise ValueError(f"unknown HPO term(s): {', '.join(unknown)}")


def _merge_extracted(items: list[ExtractedPhenotype], limit: int) -> list[ExtractedPhenotype]:
    merged: dict[str, ExtractedPhenotype] = {}
    for item in items:
        current = merged.get(item.hpo_id)
        if current is None or item.confidence > current.confidence:
            merged[item.hpo_id] = item
    return sorted(merged.values(), key=lambda item: (-item.confidence, item.name))[:limit]


def _validate_ic_options(options: dict[str, str | int | float | bool]) -> None:
    if bool(options.get("use_ancestor_terms")):
        raise ValueError("ancestor-aware IC ranking is not implemented yet")
    ic_mode = str(options.get("ic_mode") or "direct")
    if ic_mode != "direct":
        raise ValueError(f"unsupported IC mode: {ic_mode}")


def _validate_embedding_options(options: dict[str, str | int | float | bool]) -> None:
    backend = str(options.get("embedding_backend") or DEFAULT_EMBEDDING_BACKEND)
    if backend not in supported_embedding_backend_keys():
        raise ValueError(f"unsupported disease embedding backend: {backend}")
    requested_model = str(options.get("embedding_model") or "").strip() or None
    resolve_embedding_model(backend, requested_model)


def _validate_graph_options(options: dict[str, str | int | float | bool]) -> None:
    mode = str(options.get("graph_evidence_mode") or "local_overlap")
    supported = {"local_overlap", "frequency_weighted_graph", "gene_path", "source_confidence_graph"}
    if mode not in supported:
        raise ValueError(f"unsupported graph evidence mode: {mode}")


def _float_option(options: dict[str, str | int | float | bool], key: str, default: float) -> float:
    value = options.get(key, default)
    if isinstance(value, bool):
        raise ValueError(f"{key} must be a number")
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError as exc:
            raise ValueError(f"{key} must be a number") from exc
    return default


def _frequency_weight(frequency: str | None) -> float:
    if not frequency:
        return 0.30
    normalized = frequency.strip().lower()
    if normalized in {"hp:0040280", "obligate", "100%"}:
        return 1.00
    if normalized in {"hp:0040281", "very frequent", "very frequent (99-80%)", "80%-99%"}:
        return 0.90
    if normalized in {"hp:0040282", "frequent", "frequent (79-30%)", "30%-79%"}:
        return 0.75
    if normalized in {"hp:0040283", "occasional", "occasional (29-5%)", "5%-29%"}:
        return 0.40
    if normalized in {"hp:0040284", "very rare", "very rare (<4-1%)", "1%-4%"}:
        return 0.15
    if "/" in normalized:
        numerator, denominator = normalized.split("/", 1)
        try:
            return max(0.0, min(1.0, float(numerator) / float(denominator)))
        except ValueError:
            return 0.30
    if normalized.endswith("%"):
        try:
            return max(0.0, min(1.0, float(normalized.removesuffix("%")) / 100.0))
        except ValueError:
            return 0.30
    return 0.30


def _source_confidence_weight(evidence: str | None, source: str | None) -> float:
    evidence_weight = {
        "TAS": 0.90,
        "PCS": 0.85,
        "IEA": 0.55,
    }.get((evidence or "").strip().upper(), 0.70)
    source_text = (source or "").strip().lower()
    if "hpo:" in source_text:
        return min(1.0, evidence_weight + 0.05)
    return evidence_weight


def _faiss_index_exists(index_dir: Path) -> bool:
    return (index_dir / "disease.faiss").exists() and (index_dir / "disease_ids.json").exists()
