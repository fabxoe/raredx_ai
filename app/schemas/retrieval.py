from typing import Literal

from pydantic import BaseModel, Field, field_validator


HPOMapperMode = Literal[
    "off",
    "dictionary",
    "doc2hpo",
    "original_hpo_mapper",
    "dictionary_doc2hpo",
]
RankingMethod = Literal["ic", "embedding", "graph", "hybrid"]


class RetrievalRequest(BaseModel):
    hpo_terms: list[str] = Field(min_length=1)
    genes: list[str] | None = None
    top_k: int = Field(default=10, ge=1, le=100)
    ranking_options: dict[str, str | int | float | bool] = Field(default_factory=dict)

    @field_validator("hpo_terms")
    @classmethod
    def normalize_hpo_terms(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if value.strip()]
        if not normalized:
            raise ValueError("at least one HPO term is required")
        return normalized


class ClinicalNoteRetrievalRequest(BaseModel):
    clinical_note: str = Field(min_length=1)
    genes: list[str] | None = None
    top_k: int = Field(default=10, ge=1, le=100)
    max_hpo_terms: int = Field(default=30, ge=1, le=100)
    hpo_mapper: HPOMapperMode = "dictionary"
    hpo_mapper_options: dict[str, str | int | float | bool] = Field(default_factory=dict)
    ranking_options: dict[str, str | int | float | bool] = Field(default_factory=dict)


class GraphEvidenceRequest(RetrievalRequest):
    disease_ids: list[str] | None = None


class ExtractedPhenotypeMatch(BaseModel):
    hpo_id: str
    name: str
    matched_text: str
    confidence: float
    source: str
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class MatchedPhenotype(BaseModel):
    hpo_id: str
    name: str | None = None
    ic: float | None = None
    frequency: str | None = None
    evidence: str | None = None


class ScoreComponents(BaseModel):
    ic_score: float = 0.0
    embedding_score: float = 0.0
    graph_score: float = 0.0


class CandidateDisease(BaseModel):
    disease_id: str
    disease_name: str
    score: float
    score_components: ScoreComponents = Field(default_factory=ScoreComponents)
    matched_phenotypes: list[MatchedPhenotype] = Field(default_factory=list)
    missing_phenotypes: list[MatchedPhenotype] = Field(default_factory=list)
    associated_genes: list[str] = Field(default_factory=list)
    graph_paths: list[str] = Field(default_factory=list)


class RetrievalResponse(BaseModel):
    query_hpo_terms: list[str]
    candidates: list[CandidateDisease]


class ClinicalNoteRetrievalResponse(RetrievalResponse):
    clinical_note: str
    hpo_mapper: HPOMapperMode
    extracted_phenotypes: list[ExtractedPhenotypeMatch]


class PhenotypeSearchItem(BaseModel):
    hpo_id: str
    name: str


class GraphNode(BaseModel):
    id: str
    label: str
    type: str
    properties: dict[str, str | float | int | None] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    type: str
    properties: dict[str, str | float | int | None] = Field(default_factory=dict)


class GraphSubgraphResponse(BaseModel):
    query_hpo_terms: list[str]
    nodes: list[GraphNode]
    edges: list[GraphEdge]
