from app.schemas.retrieval import CandidateDisease, ScoreComponents


class HybridReranker:
    def __init__(self, ic_weight: float, embedding_weight: float, graph_weight: float) -> None:
        total = ic_weight + embedding_weight + graph_weight
        if total <= 0:
            raise ValueError("at least one reranking weight must be positive")
        self.ic_weight = ic_weight / total
        self.embedding_weight = embedding_weight / total
        self.graph_weight = graph_weight / total

    def rerank(
        self,
        ic_candidates: list[CandidateDisease],
        embedding_candidates: list[CandidateDisease],
        graph_candidates: list[CandidateDisease],
        top_k: int,
    ) -> list[CandidateDisease]:
        merged: dict[str, CandidateDisease] = {}

        for candidate in ic_candidates:
            merged[candidate.disease_id] = candidate.model_copy(deep=True)
            merged[candidate.disease_id].score_components.ic_score = candidate.score_components.ic_score

        for candidate in embedding_candidates:
            existing = merged.get(candidate.disease_id)
            if existing is None:
                existing = candidate.model_copy(deep=True)
                existing.score_components = ScoreComponents()
                merged[candidate.disease_id] = existing
            existing.score_components.embedding_score = _normalize_cosine(candidate.score_components.embedding_score)
            if not existing.matched_phenotypes:
                existing.matched_phenotypes = candidate.matched_phenotypes
            if not existing.missing_phenotypes:
                existing.missing_phenotypes = candidate.missing_phenotypes
            if not existing.associated_genes:
                existing.associated_genes = candidate.associated_genes

        for candidate in graph_candidates:
            existing = merged.get(candidate.disease_id)
            if existing is None:
                existing = candidate.model_copy(deep=True)
                existing.score_components = ScoreComponents()
                merged[candidate.disease_id] = existing
            existing.score_components.graph_score = candidate.score_components.graph_score
            existing.graph_paths = candidate.graph_paths
            if candidate.associated_genes:
                existing.associated_genes = candidate.associated_genes

        for candidate in merged.values():
            components = candidate.score_components
            candidate.score = (
                self.ic_weight * components.ic_score
                + self.embedding_weight * components.embedding_score
                + self.graph_weight * components.graph_score
            )

        ranked = sorted(merged.values(), key=lambda candidate: candidate.score, reverse=True)
        return ranked[:top_k]


def _normalize_cosine(score: float) -> float:
    return max(0.0, min(1.0, (score + 1.0) / 2.0))

