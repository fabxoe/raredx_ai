from fastapi import APIRouter, HTTPException
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from app.config import get_settings
from app.database.neo4j import Neo4jClient
from app.schemas.admin_cypher import CypherPreset, CypherRunRequest, CypherRunResponse
from app.services.cypher_lab_service import CypherLabService, ReadOnlyCypherError

router = APIRouter()


PRESETS = [
    CypherPreset(
        id="schema_labels",
        label="Schema labels",
        description="Neo4j에 적재된 node label 목록을 확인합니다.",
        query="CALL db.labels() YIELD label\nRETURN label\nORDER BY label",
    ),
    CypherPreset(
        id="schema_relationships",
        label="Relationship types",
        description="Neo4j에 적재된 relationship type 목록을 확인합니다.",
        query="CALL db.relationshipTypes() YIELD relationshipType\nRETURN relationshipType\nORDER BY relationshipType",
    ),
    CypherPreset(
        id="node_counts",
        label="Node counts",
        description="Disease, Phenotype, Gene 노드 수를 확인합니다.",
        query=(
            "MATCH (n)\n"
            "RETURN labels(n)[0] AS label, count(*) AS count\n"
            "ORDER BY count DESC"
        ),
    ),
    CypherPreset(
        id="disease_phenotype_sample",
        label="Disease-phenotype sample",
        description="질병과 표현형 연결 샘플을 graph로 조회합니다.",
        query=(
            "MATCH path = (d:Disease)-[:HAS_PHENOTYPE]->(p:Phenotype)\n"
            "RETURN path\n"
            "LIMIT 50"
        ),
    ),
    CypherPreset(
        id="disease_gene_phenotype_sample",
        label="Disease-gene-phenotype sample",
        description="질병, 유전자, 표현형의 2-hop evidence path를 조회합니다.",
        query=(
            "MATCH path = (d:Disease)-[:ASSOCIATED_WITH]->(g:Gene)-[:ASSOCIATED_PHENOTYPE]->(p:Phenotype)\n"
            "RETURN path\n"
            "LIMIT 50"
        ),
    ),
    CypherPreset(
        id="search_disease",
        label="Search disease",
        description="질병명 일부 문자열로 Disease node를 검색합니다.",
        query=(
            "MATCH (d:Disease)\n"
            "WHERE toLower(d.name) CONTAINS toLower($term)\n"
            "RETURN d\n"
            "LIMIT 25"
        ),
        params={"term": "epilepsy"},
    ),
]


@router.get("/cypher/presets", response_model=list[CypherPreset])
async def cypher_presets() -> list[CypherPreset]:
    return PRESETS


@router.post("/cypher/run", response_model=CypherRunResponse)
async def run_cypher(request: CypherRunRequest) -> CypherRunResponse:
    client = Neo4jClient(get_settings())
    service = CypherLabService(client)
    try:
        return await service.run(request)
    except ReadOnlyCypherError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (Neo4jError, ServiceUnavailable) as exc:
        raise HTTPException(status_code=503, detail=f"Neo4j is not available or query failed: {exc}") from exc
    finally:
        await client.close()
