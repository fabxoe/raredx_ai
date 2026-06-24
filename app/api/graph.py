from fastapi import APIRouter, HTTPException
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from app.config import get_settings
from app.database.neo4j import Neo4jClient
from app.graph.retrieval import GraphRetrievalService
from app.schemas.retrieval import GraphEvidenceRequest, GraphSubgraphResponse, RetrievalResponse

router = APIRouter()


@router.post("/evidence", response_model=RetrievalResponse)
async def graph_evidence(request: GraphEvidenceRequest) -> RetrievalResponse:
    client = Neo4jClient(get_settings())
    service = GraphRetrievalService(client)
    try:
        candidates = await service.evidence_for_query(
            hpo_terms=request.hpo_terms,
            top_k=request.top_k,
            disease_ids=request.disease_ids,
        )
    except (Neo4jError, ServiceUnavailable) as exc:
        raise HTTPException(status_code=503, detail=f"Neo4j is not available: {exc}") from exc
    finally:
        await client.close()
    return RetrievalResponse(query_hpo_terms=request.hpo_terms, candidates=candidates)


@router.post("/subgraph", response_model=GraphSubgraphResponse)
async def graph_subgraph(request: GraphEvidenceRequest) -> GraphSubgraphResponse:
    client = Neo4jClient(get_settings())
    service = GraphRetrievalService(client)
    try:
        return await service.subgraph_for_query(request.hpo_terms, request.top_k)
    except (Neo4jError, ServiceUnavailable) as exc:
        raise HTTPException(status_code=503, detail=f"Neo4j is not available: {exc}") from exc
    finally:
        await client.close()
