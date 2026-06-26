from functools import cached_property

from app.config import Settings
from app.embedding.biomedical import BiomedicalEmbedder
from app.embedding.faiss_index import DiseaseEmbeddingIndex
from app.etl.processed_store import load_processed_knowledge_base
from app.llm.phenotype_qc import PhenotypeLLMSelector, build_phenotype_llm_selector
from app.reranking.hybrid import HybridReranker
from app.retrieval.doc2hpo_mapper import Doc2HPOMapper
from app.retrieval.ic_baseline import ICBaselineRanker
from app.retrieval.knowledge import KnowledgeIndex
from app.retrieval.note_matcher import ClinicalNoteMatcher, ExtractedPhenotype
from app.schemas.retrieval import CandidateDisease


class RetrievalService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @cached_property
    def knowledge(self) -> KnowledgeIndex:
        return KnowledgeIndex(load_processed_knowledge_base(self.settings.processed_dir))

    @cached_property
    def ic_ranker(self) -> ICBaselineRanker:
        return ICBaselineRanker(self.knowledge)

    @cached_property
    def embedding_index(self) -> DiseaseEmbeddingIndex:
        index = DiseaseEmbeddingIndex(self.knowledge, BiomedicalEmbedder(self.settings.embedding_model))
        index_dir = self.settings.processed_dir / "faiss"
        if (index_dir / "disease.faiss").exists() and (index_dir / "disease_ids.json").exists():
            index.load(index_dir)
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
    def original_hpo_mapper(self) -> Doc2HPOMapper:
        return Doc2HPOMapper(
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

    def rank_ic(self, hpo_terms: list[str], top_k: int) -> list[CandidateDisease]:
        self._validate_hpo_terms(hpo_terms)
        return self.ic_ranker.rank(hpo_terms, top_k)

    def rank_embedding(self, hpo_terms: list[str], top_k: int) -> list[CandidateDisease]:
        self._validate_hpo_terms(hpo_terms)
        return self.embedding_index.search(hpo_terms, top_k)

    def rank_hybrid(self, hpo_terms: list[str], top_k: int) -> list[CandidateDisease]:
        self._validate_hpo_terms(hpo_terms)
        ic_candidates = self.rank_ic(hpo_terms, max(top_k * 3, 30))
        embedding_candidates = self.rank_embedding(hpo_terms, max(top_k * 3, 30))
        graph_candidates = self._local_graph_overlap(hpo_terms, max(top_k * 3, 30))
        return self.reranker.rerank(ic_candidates, embedding_candidates, graph_candidates, top_k)

    def _local_graph_overlap(self, hpo_terms: list[str], top_k: int) -> list[CandidateDisease]:
        candidates = self.ic_ranker.rank(hpo_terms, top_k)
        query_size = len(set(hpo_terms)) or 1
        for candidate in candidates:
            graph_score = len(candidate.matched_phenotypes) / query_size
            candidate.score = graph_score
            candidate.score_components.graph_score = graph_score
            candidate.graph_paths = [
                f"Patient -> {phenotype.hpo_id} -> {candidate.disease_id}"
                for phenotype in candidate.matched_phenotypes
            ]
        return candidates

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
