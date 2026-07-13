from typing import Any, Literal

from pydantic import BaseModel, Field


CypherMode = Literal["read", "write"]


class CypherRunRequest(BaseModel):
    query: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)
    mode: CypherMode = "read"
    result_limit: int = Field(default=500, ge=1, le=5000)
    graph_limit: int = Field(default=250, ge=1, le=1000)
    timeout_ms: int = Field(default=10000, ge=500, le=60000)


class CypherGraphNode(BaseModel):
    id: str
    label: str
    type: str
    labels: list[str] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)


class CypherGraphEdge(BaseModel):
    id: str
    source: str
    target: str
    type: str
    properties: dict[str, Any] = Field(default_factory=dict)


class CypherGraphResponse(BaseModel):
    nodes: list[CypherGraphNode] = Field(default_factory=list)
    edges: list[CypherGraphEdge] = Field(default_factory=list)


class CypherRunStats(BaseModel):
    elapsed_ms: int
    row_count: int
    column_count: int
    node_count: int
    edge_count: int
    truncated_rows: bool = False
    truncated_graph: bool = False
    mode: CypherMode


class CypherRunResponse(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    graph: CypherGraphResponse
    stats: CypherRunStats
    warnings: list[str] = Field(default_factory=list)


class CypherPreset(BaseModel):
    id: str
    label: str
    description: str
    query: str
    params: dict[str, Any] = Field(default_factory=dict)
