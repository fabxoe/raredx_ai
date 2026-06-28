from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.retrieval import CandidateDisease, ExtractedPhenotypeMatch, HPOMapperMode, RankingMethod


MapperOptionType = Literal["boolean", "number", "select", "text"]


class HPOMapperOption(BaseModel):
    key: str
    label: str
    type: MapperOptionType
    default: str | int | float | bool
    choices: list[str] = Field(default_factory=list)


class HPOMapperCapability(BaseModel):
    id: HPOMapperMode
    label: str
    description: str
    configured: bool
    options: list[HPOMapperOption] = Field(default_factory=list)


class HPOMapperCompareRequest(BaseModel):
    clinical_note: str = Field(min_length=1)
    mappers: list[HPOMapperMode] = Field(default_factory=lambda: ["dictionary", "doc2hpo"])
    top_k: int = Field(default=10, ge=1, le=100)
    max_hpo_terms: int = Field(default=30, ge=1, le=100)
    ranking_method: RankingMethod = "ic"
    mapper_options: dict[str, dict[str, str | int | float | bool]] = Field(default_factory=dict)
    ranking_options: dict[str, str | int | float | bool] = Field(default_factory=dict)


class HPOMapperRunResult(BaseModel):
    mapper: HPOMapperMode
    label: str
    configured: bool
    error: str | None = None
    extracted_phenotypes: list[ExtractedPhenotypeMatch] = Field(default_factory=list)
    query_hpo_terms: list[str] = Field(default_factory=list)
    candidates: list[CandidateDisease] = Field(default_factory=list)


class HPOMapperCompareResponse(BaseModel):
    clinical_note: str
    results: list[HPOMapperRunResult]
