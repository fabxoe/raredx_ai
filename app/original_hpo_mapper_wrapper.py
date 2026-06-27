import json
import os
import re
import sqlite3
import urllib.error
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException
from numpy.linalg import norm
from pydantic import BaseModel, Field

from app.config import get_settings
from app.llm.phenotype_qc import build_phenotype_llm_selector
from app.retrieval.note_matcher import ExtractedPhenotype


app = FastAPI(
    title="RARE_DX_AI Original HPO-Mapper Wrapper",
    version="0.1.0",
)


@dataclass(frozen=True)
class HPOEmbeddingRow:
    hpo_id: str
    hpo_name: str
    matched_term: str
    embedding: np.ndarray


@dataclass(frozen=True)
class MapperStore:
    embeddings: tuple[HPOEmbeddingRow, ...]
    gene_map: dict[str, list[str]]
    definitions: dict[str, str]


class FindingInput(BaseModel):
    finding: str
    anatomical_region: str = ""


class LLMOptions(BaseModel):
    enabled: bool = False
    provider: str = "off"
    chat_model: str = ""


class OriginalHPOMapperRequest(BaseModel):
    clinical_note: str = Field(default="")
    findings: list[FindingInput] = Field(default_factory=list)
    protocol: str = "p1"
    top_k: int = Field(default=10, ge=1, le=100)
    max_hpo_terms: int = Field(default=30, ge=1, le=100)
    threshold: float = 0.76
    min_sim: float | None = None
    embed_model: str = "nomic-embed-text"
    embedding_model: str | None = None
    max_genes: int | None = None
    llm: LLMOptions = Field(default_factory=LLMOptions)
    return_candidates: bool = True


class MappedRow(BaseModel):
    finding: str
    region: str = ""
    hpo_id: str
    hpo_term: str
    matched_term: str
    genes: list[str] = Field(default_factory=list)
    gene_count: int = 0
    score: float | str = ""
    similarity: float | str = ""
    flag: str = ""
    candidates: list[dict[str, str | float]] = Field(default_factory=list)


class OriginalHPOMapperResponse(BaseModel):
    protocol: str
    mapped_rows: list[MappedRow]


@app.get("/health")
def health() -> dict[str, str | int]:
    store = get_store()
    return {
        "status": "ok",
        "hpo_embeddings": len(store.embeddings),
        "hpo_gene_rows": len(store.gene_map),
        "hpo_definitions": len(store.definitions),
    }


@app.post("/map", response_model=OriginalHPOMapperResponse)
def map_hpo(request: OriginalHPOMapperRequest) -> OriginalHPOMapperResponse:
    protocol = request.protocol.strip().lower() or "p1"
    if protocol not in {"p1", "p2_qc", "p3_llm_selection"}:
        raise HTTPException(status_code=400, detail=f"unsupported protocol: {request.protocol}")

    findings = _request_findings(request)
    if not findings:
        raise HTTPException(status_code=400, detail="clinical_note or findings is required")

    try:
        rows = _map_findings(findings, request)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if request.llm.enabled or protocol in {"p2_qc", "p3_llm_selection"}:
        try:
            rows = _apply_llm_protocol(request, rows, protocol)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    return OriginalHPOMapperResponse(protocol=protocol, mapped_rows=rows[: request.max_hpo_terms])


def _map_findings(request_findings: list[FindingInput], request: OriginalHPOMapperRequest) -> list[MappedRow]:
    store = get_store()
    threshold = request.min_sim if request.min_sim is not None else request.threshold
    embed_model = request.embedding_model or request.embed_model
    mapped_rows: list[MappedRow] = []
    for item in request_findings:
        candidates = _top_matches(
            finding=item.finding,
            region=item.anatomical_region,
            store=store,
            embed_model=embed_model,
            top_k=request.top_k,
        )
        accepted = [candidate for candidate in candidates if candidate["similarity"] >= threshold]
        if not accepted:
            mapped_rows.append(
                MappedRow(
                    finding=item.finding,
                    region=item.anatomical_region,
                    hpo_id="NA",
                    hpo_term="NA",
                    matched_term="NA",
                    genes=[],
                    score="",
                    similarity="",
                    candidates=candidates if request.return_candidates else [],
                )
            )
            continue

        best = accepted[0]
        hpo_id = str(best["hpo_id"])
        genes = store.gene_map.get(hpo_id, [])
        mapped_rows.append(
            MappedRow(
                finding=item.finding,
                region=item.anatomical_region,
                hpo_id=hpo_id,
                hpo_term=str(best["hpo_term"]),
                matched_term=str(best["matched_term"]),
                genes=_limit_genes(genes, request.max_genes),
                gene_count=len(genes),
                score=float(best["similarity"]),
                similarity=float(best["similarity"]),
                candidates=candidates if request.return_candidates else [],
            )
        )
    return mapped_rows


def _top_matches(
    finding: str,
    region: str,
    store: MapperStore,
    embed_model: str,
    top_k: int,
) -> list[dict[str, str | float]]:
    query_text = f"{finding} in {region}".strip()
    query_embedding = _ollama_embedding(embed_model, query_text)
    scored = [
        (
            _cosine_similarity(query_embedding, row.embedding),
            row.hpo_id,
            row.hpo_name,
            row.matched_term,
        )
        for row in store.embeddings
    ]
    scored.sort(reverse=True, key=lambda item: item[0])
    return [
        {
            "hpo_id": hpo_id,
            "hpo_term": hpo_name,
            "matched_term": matched_term,
            "definition": store.definitions.get(hpo_id, ""),
            "similarity": float(similarity),
        }
        for similarity, hpo_id, hpo_name, matched_term in scored[:top_k]
    ]


def _apply_llm_protocol(
    request: OriginalHPOMapperRequest,
    rows: list[MappedRow],
    protocol: str,
) -> list[MappedRow]:
    provider = request.llm.provider.strip().lower()
    if provider == "off":
        return rows

    candidates = [
        ExtractedPhenotype(
            hpo_id=row.hpo_id,
            name=row.hpo_term,
            matched_text=row.matched_term,
            confidence=_score_float(row.similarity),
            source="original_hpo_mapper_wrapper",
            metadata={"finding": row.finding, "region": row.region},
        )
        for row in rows
        if row.hpo_id != "NA"
    ]
    if not candidates:
        return rows

    settings = get_settings()
    selector = build_phenotype_llm_selector(settings, provider_override=provider, model_override=request.llm.chat_model or None)
    selected = selector.select(request.clinical_note, candidates, protocol=protocol)
    selected_ids = {item.hpo_id for item in selected}

    if protocol == "p2_qc":
        return [row.model_copy(update={"flag": "1" if row.hpo_id not in selected_ids and row.hpo_id != "NA" else ""}) for row in rows]
    if protocol == "p3_llm_selection":
        return [row for row in rows if row.hpo_id == "NA" or row.hpo_id in selected_ids]
    return rows


@lru_cache
def get_store() -> MapperStore:
    settings = get_settings()
    db_path = (settings.original_hpo_mapper_db_path or "").strip()
    if not db_path:
        raise RuntimeError("Set RAREDX_ORIGINAL_HPO_MAPPER_DB_PATH to the HPO-Mapper SQLite DB path.")
    if not os.path.exists(db_path):
        raise RuntimeError(f"HPO-Mapper DB not found: {db_path}")
    return MapperStore(
        embeddings=tuple(_load_hpo_embeddings(db_path)),
        gene_map=_load_hpo_gene_map(db_path),
        definitions=_load_hpo_definitions((settings.original_hpo_mapper_hpo_json or "").strip()),
    )


def _load_hpo_embeddings(db_path: str) -> list[HPOEmbeddingRow]:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT hpo_id, hpo_name, term, embedding FROM hpo_synonym_embeddings")
        rows = cursor.fetchall()
    finally:
        conn.close()
    return [
        HPOEmbeddingRow(
            hpo_id=str(hpo_id),
            hpo_name=str(hpo_name),
            matched_term=str(term),
            embedding=np.array(json.loads(str(embedding)), dtype=float),
        )
        for hpo_id, hpo_name, term, embedding in rows
    ]


def _load_hpo_gene_map(db_path: str) -> dict[str, list[str]]:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT hpo_id, genes FROM hpo_gene")
        rows = cursor.fetchall()
    finally:
        conn.close()
    return {str(hpo_id): str(genes).split(", ") if genes else [] for hpo_id, genes in rows}


def _limit_genes(genes: list[str], request_max_genes: int | None) -> list[str]:
    max_genes = request_max_genes
    if max_genes is None:
        max_genes = get_settings().original_hpo_mapper_max_genes
    if max_genes < 0:
        return genes
    return genes[:max_genes]


def _load_hpo_definitions(hpo_json_path: str) -> dict[str, str]:
    if not hpo_json_path:
        return {}
    if not os.path.exists(hpo_json_path):
        raise RuntimeError(f"HPO JSON not found: {hpo_json_path}")
    with open(hpo_json_path, encoding="utf-8") as file:
        hpo_json = json.load(file)
    definitions: dict[str, str] = {}
    for node in hpo_json.get("graphs", [{}])[0].get("nodes", []):
        raw_id = str(node.get("id", ""))
        if "HP_" not in raw_id:
            continue
        hpo_id = raw_id.rsplit("/", 1)[-1].replace("_", ":")
        definition = node.get("meta", {}).get("definition", {}).get("val", "")
        definitions[hpo_id] = str(definition or "")
    return definitions


def _request_findings(request: OriginalHPOMapperRequest) -> list[FindingInput]:
    if request.findings:
        return [item for item in request.findings if item.finding.strip()]
    return [FindingInput(finding=finding) for finding in _split_clinical_note(request.clinical_note)]


def _split_clinical_note(clinical_note: str) -> list[str]:
    cleaned = re.sub(r"\b(the )?patient (has|had|with|shows|presents with)\b", " ", clinical_note, flags=re.I)
    parts = re.split(r"[.;\n]|\band\b|,", cleaned)
    findings = []
    for part in parts:
        finding = re.sub(r"\s+", " ", part).strip(" .,:;-")
        if len(finding) >= 3:
            findings.append(finding)
    return findings


def _ollama_embedding(model: str, prompt: str) -> np.ndarray:
    base_url = os.getenv("RAREDX_OLLAMA_URL", "http://localhost:11434").rstrip("/")
    payload = {"model": model, "prompt": prompt}
    request = urllib.request.Request(
        f"{base_url}/api/embeddings",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Ollama embedding request failed: {exc}") from exc
    embedding = data.get("embedding")
    if not isinstance(embedding, list):
        raise RuntimeError("Ollama embedding response did not include an embedding list.")
    return np.array(embedding, dtype=float)


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denominator = float(norm(a) * norm(b))
    if denominator == 0.0:
        return -1.0
    return float(np.dot(a, b) / denominator)


def _score_float(value: float | str) -> float:
    if isinstance(value, float):
        return value
    try:
        return float(value)
    except ValueError:
        return 0.0
