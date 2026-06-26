from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.retrieval import RankingMethod


RankingOptionType = Literal["boolean", "number", "select", "text"]


class RankingOption(BaseModel):
    key: str
    label: str
    type: RankingOptionType
    default: str | int | float | bool
    choices: list[str] = Field(default_factory=list)


class RankingMethodCapability(BaseModel):
    id: RankingMethod
    label: str
    description: str
    configured: bool
    options: list[RankingOption] = Field(default_factory=list)
