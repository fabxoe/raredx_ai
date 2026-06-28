from functools import lru_cache

from fastapi import APIRouter

from app.config import get_settings
from app.retrieval.mapper_registry import mapper_capabilities, mapper_label
from app.schemas.hpo_mapper import (
    HPOMapperCapability,
    HPOMapperCompareRequest,
    HPOMapperCompareResponse,
    HPOMapperRunResult,
)
from app.schemas.retrieval import ExtractedPhenotypeMatch
from app.services.retrieval_service import RetrievalService

router = APIRouter()


@lru_cache
def get_mapper_service() -> RetrievalService:
    return RetrievalService(get_settings())


@router.get("", response_model=list[HPOMapperCapability])
def list_hpo_mappers() -> list[HPOMapperCapability]:
    return mapper_capabilities(get_settings())


@router.post("/compare", response_model=HPOMapperCompareResponse)
def compare_hpo_mappers(request: HPOMapperCompareRequest) -> HPOMapperCompareResponse:
    service = get_mapper_service()
    settings = get_settings()
    capabilities = {capability.id: capability for capability in mapper_capabilities(settings)}
    results: list[HPOMapperRunResult] = []

    for mapper_id in request.mappers:
        capability = capabilities.get(mapper_id)
        if capability is None:
            results.append(
                HPOMapperRunResult(
                    mapper=mapper_id,
                    label=mapper_id,
                    configured=False,
                    error=f"unknown mapper: {mapper_id}",
                )
            )
            continue

        try:
            extracted = service.extract_hpo_terms(
                request.clinical_note,
                limit=request.max_hpo_terms,
                mapper_mode=mapper_id,
                mapper_options=request.mapper_options.get(mapper_id, {}),
            )
            hpo_terms = [item.hpo_id for item in extracted]
            candidates = []
            if hpo_terms:
                if request.ranking_method == "hybrid":
                    candidates = service.rank_hybrid(hpo_terms, request.top_k, options=request.ranking_options)
                elif request.ranking_method == "graph":
                    candidates = service.rank_graph(hpo_terms, request.top_k, options=request.ranking_options)
                elif request.ranking_method == "embedding":
                    candidates = service.rank_embedding(hpo_terms, request.top_k, options=request.ranking_options)
                else:
                    candidates = service.rank_ic(hpo_terms, request.top_k, options=request.ranking_options)
            results.append(
                HPOMapperRunResult(
                    mapper=mapper_id,
                    label=mapper_label(settings, mapper_id),
                    configured=capability.configured,
                    extracted_phenotypes=[ExtractedPhenotypeMatch(**item.__dict__) for item in extracted],
                    query_hpo_terms=hpo_terms,
                    candidates=candidates,
                )
            )
        except Exception as exc:
            results.append(
                HPOMapperRunResult(
                    mapper=mapper_id,
                    label=mapper_label(settings, mapper_id),
                    configured=capability.configured,
                    error=str(exc),
                )
            )

    return HPOMapperCompareResponse(clinical_note=request.clinical_note, results=results)
