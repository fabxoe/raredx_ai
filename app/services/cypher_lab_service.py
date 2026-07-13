from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Mapping
from typing import Any

from neo4j.exceptions import Neo4jError
from neo4j.graph import Node, Path, Relationship

from app.database.neo4j import Neo4jClient
from app.schemas.admin_cypher import (
    CypherGraphEdge,
    CypherGraphNode,
    CypherGraphResponse,
    CypherMode,
    CypherRunRequest,
    CypherRunResponse,
    CypherRunStats,
)


WRITE_KEYWORDS = re.compile(
    r"\b(CREATE|MERGE|SET|DELETE|DETACH\s+DELETE|REMOVE|DROP|LOAD\s+CSV|FOREACH|CALL\s+dbms\.|CALL\s+apoc\.periodic)\b",
    re.IGNORECASE,
)
COMMENT_LINE = re.compile(r"//.*?$", re.MULTILINE)
COMMENT_BLOCK = re.compile(r"/\*.*?\*/", re.DOTALL)


class ReadOnlyCypherError(ValueError):
    pass


class CypherLabService:
    def __init__(self, client: Neo4jClient) -> None:
        self.client = client

    async def run(self, request: CypherRunRequest) -> CypherRunResponse:
        query = request.query.strip()
        if request.mode == "read":
            self._validate_read_only(query)

        started = time.perf_counter()
        try:
            columns, rows, graph, truncated_rows, truncated_graph = await asyncio.wait_for(
                self._execute(query=query, request=request),
                timeout=request.timeout_ms / 1000,
            )
        except TimeoutError as exc:
            raise Neo4jError(f"Cypher query timed out after {request.timeout_ms} ms") from exc

        elapsed_ms = round((time.perf_counter() - started) * 1000)
        warnings = []
        if truncated_rows:
            warnings.append(f"Rows were truncated to result_limit={request.result_limit}.")
        if truncated_graph:
            warnings.append(f"Graph was truncated to graph_limit={request.graph_limit}.")

        return CypherRunResponse(
            columns=columns,
            rows=rows,
            graph=CypherGraphResponse(nodes=list(graph["nodes"].values()), edges=list(graph["edges"].values())),
            stats=CypherRunStats(
                elapsed_ms=elapsed_ms,
                row_count=len(rows),
                column_count=len(columns),
                node_count=len(graph["nodes"]),
                edge_count=len(graph["edges"]),
                truncated_rows=truncated_rows,
                truncated_graph=truncated_graph,
                mode=request.mode,
            ),
            warnings=warnings,
        )

    async def _execute(
        self,
        *,
        query: str,
        request: CypherRunRequest,
    ) -> tuple[list[str], list[dict[str, Any]], dict[str, dict[str, Any]], bool, bool]:
        rows: list[dict[str, Any]] = []
        columns: list[str] = []
        graph: dict[str, dict[str, CypherGraphNode | CypherGraphEdge]] = {"nodes": {}, "edges": {}}
        truncated_rows = False
        truncated_graph = False

        async with self.client.session() as session:
            result = await session.run(query, request.params)
            columns = list(result.keys())
            async for record in result:
                if len(rows) >= request.result_limit:
                    truncated_rows = True
                    break
                row = {key: self._json_value(record[key]) for key in record.keys()}
                rows.append(row)
                for value in record.values():
                    if self._collect_graph(value, graph, request.graph_limit):
                        truncated_graph = True
            await result.consume()

        return columns, rows, graph, truncated_rows, truncated_graph

    def _validate_read_only(self, query: str) -> None:
        normalized = COMMENT_BLOCK.sub("", COMMENT_LINE.sub("", query))
        if WRITE_KEYWORDS.search(normalized):
            raise ReadOnlyCypherError("Read-only mode blocks write/admin Cypher. Unlock write mode to run this query.")

    def _collect_graph(
        self,
        value: Any,
        graph: dict[str, dict[str, CypherGraphNode | CypherGraphEdge]],
        graph_limit: int,
    ) -> bool:
        before = (len(graph["nodes"]), len(graph["edges"]))
        self._collect_graph_value(value, graph, graph_limit)
        return len(graph["nodes"]) >= graph_limit and before[0] < graph_limit

    def _collect_graph_value(
        self,
        value: Any,
        graph: dict[str, dict[str, CypherGraphNode | CypherGraphEdge]],
        graph_limit: int,
    ) -> None:
        if isinstance(value, Node):
            self._add_node(value, graph, graph_limit)
        elif isinstance(value, Relationship):
            self._add_relationship(value, graph, graph_limit)
        elif isinstance(value, Path):
            for node in value.nodes:
                self._add_node(node, graph, graph_limit)
            for relationship in value.relationships:
                self._add_relationship(relationship, graph, graph_limit)
        elif isinstance(value, Mapping):
            for nested in value.values():
                self._collect_graph_value(nested, graph, graph_limit)
        elif isinstance(value, list | tuple):
            for nested in value:
                self._collect_graph_value(nested, graph, graph_limit)

    def _add_node(
        self,
        node: Node,
        graph: dict[str, dict[str, CypherGraphNode | CypherGraphEdge]],
        graph_limit: int,
    ) -> None:
        node_id = self._node_id(node)
        if node_id in graph["nodes"] or len(graph["nodes"]) >= graph_limit:
            return
        properties = dict(node.items())
        labels = sorted(node.labels)
        node_type = self._node_type(labels)
        graph["nodes"][node_id] = CypherGraphNode(
            id=node_id,
            label=self._node_label(properties, labels, node_id),
            type=node_type,
            labels=labels,
            properties=self._json_value(properties),
        )

    def _add_relationship(
        self,
        relationship: Relationship,
        graph: dict[str, dict[str, CypherGraphNode | CypherGraphEdge]],
        graph_limit: int,
    ) -> None:
        rel_id = str(relationship.element_id)
        if rel_id in graph["edges"] or len(graph["edges"]) >= graph_limit * 2:
            return
        self._add_node(relationship.start_node, graph, graph_limit)
        self._add_node(relationship.end_node, graph, graph_limit)
        graph["edges"][rel_id] = CypherGraphEdge(
            id=rel_id,
            source=self._node_id(relationship.start_node),
            target=self._node_id(relationship.end_node),
            type=relationship.type,
            properties=self._json_value(dict(relationship.items())),
        )

    def _json_value(self, value: Any) -> Any:
        if isinstance(value, Node):
            labels = sorted(value.labels)
            properties = dict(value.items())
            node_id = self._node_id(value)
            return {
                "_type": "node",
                "id": node_id,
                "label": self._node_label(properties, labels, node_id),
                "labels": labels,
                "properties": self._json_value(properties),
            }
        if isinstance(value, Relationship):
            return {
                "_type": "relationship",
                "id": str(value.element_id),
                "source": self._node_id(value.start_node),
                "target": self._node_id(value.end_node),
                "type": value.type,
                "properties": self._json_value(dict(value.items())),
            }
        if isinstance(value, Path):
            return {
                "_type": "path",
                "nodes": [self._json_value(node) for node in value.nodes],
                "relationships": [self._json_value(relationship) for relationship in value.relationships],
            }
        if isinstance(value, Mapping):
            return {str(key): self._json_value(nested) for key, nested in value.items()}
        if isinstance(value, list | tuple):
            return [self._json_value(nested) for nested in value]
        if isinstance(value, set):
            return [self._json_value(nested) for nested in sorted(value, key=str)]
        return value

    def _node_id(self, node: Node) -> str:
        return str(dict(node.items()).get("id") or node.element_id)

    def _node_type(self, labels: list[str]) -> str:
        for label in ["Patient", "Disease", "Phenotype", "Gene"]:
            if label in labels:
                return label
        return labels[0] if labels else "Node"

    def _node_label(self, properties: dict[str, Any], labels: list[str], node_id: str) -> str:
        for key in ["name", "symbol", "id", "label"]:
            value = properties.get(key)
            if value:
                return str(value)
        return labels[0] if labels else node_id
