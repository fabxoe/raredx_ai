from typing import cast

import pytest
from fastapi.testclient import TestClient

from app.database.neo4j import Neo4jClient
from app.main import create_app
from app.services.cypher_lab_service import CypherLabService, ReadOnlyCypherError


def _service() -> CypherLabService:
    return CypherLabService(cast(Neo4jClient, object()))


def test_read_only_allows_match_and_schema_calls() -> None:
    service = _service()

    service._validate_read_only("MATCH (n) RETURN n LIMIT 1")
    service._validate_read_only("CALL db.labels() YIELD label RETURN label")
    service._validate_read_only("CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType")


@pytest.mark.parametrize(
    "query",
    [
        "CREATE (n:Test)",
        "MATCH (n) DELETE n",
        "MATCH (n) DETACH DELETE n",
        "MERGE (n:Test {id: 'x'})",
        "MATCH (n) SET n.name = 'x'",
        "CALL dbms.components() YIELD name RETURN name",
        "CALL apoc.periodic.iterate('MATCH (n) RETURN n', 'DELETE n', {})",
    ],
)
def test_read_only_blocks_write_and_admin_queries(query: str) -> None:
    with pytest.raises(ReadOnlyCypherError):
        _service()._validate_read_only(query)


def test_read_only_ignores_commented_write_keywords() -> None:
    service = _service()

    service._validate_read_only("// CREATE (n)\nMATCH (n) RETURN n LIMIT 1")
    service._validate_read_only("/* DELETE n */\nMATCH (n) RETURN n LIMIT 1")


def test_cypher_presets_endpoint() -> None:
    client = TestClient(create_app())

    response = client.get("/api/admin/cypher/presets")

    assert response.status_code == 200
    preset_ids = {item["id"] for item in response.json()}
    assert {"schema_labels", "disease_phenotype_sample", "search_disease"} <= preset_ids
