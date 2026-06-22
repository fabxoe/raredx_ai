import math
from dataclasses import dataclass

from app.retrieval.knowledge import KnowledgeIndex
from app.schemas.retrieval import CandidateDisease, MatchedPhenotype, ScoreComponents


@dataclass(frozen=True)
class ICScore:
    hpo_id: str
    value: float


class ICBaselineRanker:
    def __init__(self, knowledge: KnowledgeIndex) -> None:
        self.knowledge = knowledge
        self._ic = self._compute_ic()

    def rank(self, hpo_terms: list[str], top_k: int) -> list[CandidateDisease]:
        query = set(hpo_terms)
        candidates: list[CandidateDisease] = []
        max_possible = sum(self._ic.get(hpo_id, 0.0) for hpo_id in query) or 1.0

        for profile in self.knowledge.disease_profiles.values():
            matched = query.intersection(profile.phenotype_ids)
            if not matched:
                continue
            raw_score = sum(self._ic.get(hpo_id, 0.0) for hpo_id in matched)
            normalized_score = raw_score / max_possible
            candidates.append(
                CandidateDisease(
                    disease_id=profile.disease_id,
                    disease_name=profile.disease_name,
                    score=normalized_score,
                    score_components=ScoreComponents(ic_score=normalized_score),
                    matched_phenotypes=[
                        MatchedPhenotype(
                            hpo_id=hpo_id,
                            name=self.knowledge.get_phenotype_name(hpo_id),
                            ic=self._ic.get(hpo_id, 0.0),
                        )
                        for hpo_id in sorted(matched)
                    ],
                    missing_phenotypes=[
                        MatchedPhenotype(hpo_id=hpo_id, name=self.knowledge.get_phenotype_name(hpo_id))
                        for hpo_id in sorted(query.difference(profile.phenotype_ids))
                    ],
                    associated_genes=sorted(self.knowledge.disease_genes.get(profile.disease_id, set())),
                )
            )

        candidates.sort(key=lambda candidate: candidate.score, reverse=True)
        return candidates[:top_k]

    def get_ic(self, hpo_id: str) -> float:
        return self._ic.get(hpo_id, 0.0)

    def _compute_ic(self) -> dict[str, float]:
        total_diseases = max(len(self.knowledge.disease_profiles), 1)
        return {
            hpo_id: -math.log((len(disease_ids) + 1) / (total_diseases + 1))
            for hpo_id, disease_ids in self.knowledge.hpo_to_diseases.items()
        }

