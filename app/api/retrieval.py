from functools import lru_cache

from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.schemas.retrieval import (
    ClinicalNoteRetrievalRequest,
    ClinicalNoteRetrievalResponse,
    ExtractedPhenotypeMatch,
    RetrievalRequest,
    RetrievalResponse,
)
from app.services.retrieval_service import RetrievalService

router = APIRouter()


@lru_cache
def get_retrieval_service() -> RetrievalService:
    return RetrievalService(get_settings())


@router.post("/ic", response_model=RetrievalResponse)
def retrieve_ic(request: RetrievalRequest) -> RetrievalResponse:
    return _retrieve(request, mode="ic")


@router.post("/embedding", response_model=RetrievalResponse)
def retrieve_embedding(request: RetrievalRequest) -> RetrievalResponse:
    return _retrieve(request, mode="embedding")


@router.post("/hybrid", response_model=RetrievalResponse)
def retrieve_hybrid(request: RetrievalRequest) -> RetrievalResponse:
    return _retrieve(request, mode="hybrid")


@router.post("/note/ic", response_model=ClinicalNoteRetrievalResponse)
def retrieve_note_ic(request: ClinicalNoteRetrievalRequest) -> ClinicalNoteRetrievalResponse:
    return _retrieve_note(request, mode="ic")


@router.post("/note/hybrid", response_model=ClinicalNoteRetrievalResponse)
def retrieve_note_hybrid(request: ClinicalNoteRetrievalRequest) -> ClinicalNoteRetrievalResponse:
    return _retrieve_note(request, mode="hybrid")


def _retrieve(request: RetrievalRequest, mode: str) -> RetrievalResponse:
    service = get_retrieval_service()
    try:
        if mode == "ic":
            candidates = service.rank_ic(request.hpo_terms, request.top_k)
        elif mode == "embedding":
            candidates = service.rank_embedding(request.hpo_terms, request.top_k)
        else:
            candidates = service.rank_hybrid(request.hpo_terms, request.top_k)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=f"processed data is not available: {exc}") from exc
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"embedding dependency is not available: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RetrievalResponse(query_hpo_terms=request.hpo_terms, candidates=candidates)


def _retrieve_note(request: ClinicalNoteRetrievalRequest, mode: str) -> ClinicalNoteRetrievalResponse:
    service = get_retrieval_service()
    try:
        extracted = service.extract_hpo_terms(request.clinical_note, limit=request.max_hpo_terms)
        hpo_terms = [item.hpo_id for item in extracted]
        if not hpo_terms:
            raise ValueError("no HPO terms could be extracted from clinical_note")
        candidates = service.rank_ic(hpo_terms, request.top_k) if mode == "ic" else service.rank_hybrid(hpo_terms, request.top_k)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=f"processed data is not available: {exc}") from exc
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"embedding dependency is not available: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ClinicalNoteRetrievalResponse(
        clinical_note=request.clinical_note,
        query_hpo_terms=hpo_terms,
        extracted_phenotypes=[ExtractedPhenotypeMatch(**item.__dict__) for item in extracted],
        candidates=candidates,
    )
