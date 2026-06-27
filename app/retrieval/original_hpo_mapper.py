from typing import Any

from app.retrieval.doc2hpo_mapper import Doc2HPOMapper
from app.retrieval.note_matcher import ExtractedPhenotype


class OriginalHPOMapperAdapter(Doc2HPOMapper):
    def _should_apply_local_llm(self, options: dict[str, str | int | float | bool]) -> bool:
        return False

    def _build_payload(
        self,
        clinical_note: str,
        limit: int,
        options: dict[str, str | int | float | bool],
    ) -> dict[str, Any]:
        protocol = str(options.get("protocol") or "p1").strip() or "p1"
        top_k = _int_option(options, "top_k", limit)
        threshold = _float_option(options, "threshold", 0.76)
        embed_model = str(options.get("embed_model") or "nomic-embed-text").strip()
        max_genes = _max_genes_option(options)
        llm_provider = str(options.get("llm_provider") or "off").strip().lower()
        chat_model = str(options.get("chat_model") or "").strip()
        use_llm = bool(options.get("use_llm")) or protocol == "p3_llm_selection"

        return {
            "clinical_note": clinical_note,
            "protocol": protocol,
            "top_k": top_k,
            "max_hpo_terms": limit,
            "threshold": threshold,
            "min_sim": threshold,
            "embed_model": embed_model,
            "embedding_model": embed_model,
            "max_genes": max_genes,
            "llm": {
                "enabled": use_llm,
                "provider": llm_provider,
                "chat_model": chat_model,
            },
            "return_candidates": True,
            "options": options,
        }

    def _parse_response(
        self,
        data: Any,
        limit: int,
        options: dict[str, str | int | float | bool],
    ) -> list[ExtractedPhenotype]:
        rows = _extract_original_rows(data)
        extracted: list[ExtractedPhenotype] = []
        seen: set[str] = set()
        for rank, row in enumerate(rows, start=1):
            normalized = _normalize_row(row)
            if not normalized:
                continue
            hpo_id = normalized.get("hpo_id")
            if not hpo_id or hpo_id == "NA" or hpo_id in seen or hpo_id not in self.knowledge.phenotypes:
                continue
            term = self.knowledge.phenotypes[hpo_id]
            confidence = max(0.0, min(1.0, _float_value(normalized.get("score"), 0.75)))
            extracted.append(
                ExtractedPhenotype(
                    hpo_id=hpo_id,
                    name=term.name,
                    matched_text=normalized.get("matched_text") or normalized.get("finding") or term.name,
                    confidence=confidence,
                    source=self.source,
                    metadata={
                        "mapper_source": self.source,
                        "candidate_rank": rank,
                        "protocol": str(options.get("protocol", "p1")),
                        "threshold": _metadata_value(options.get("threshold")),
                        "embedding_model": str(options.get("embed_model", "nomic-embed-text")),
                        "llm_used": bool(options.get("use_llm"))
                        or str(options.get("protocol", "")).lower() == "p3_llm_selection",
                        "finding": normalized.get("finding"),
                        "region": normalized.get("region"),
                        "matched_term": normalized.get("matched_term"),
                        "genes": normalized.get("genes"),
                        "gene_count": normalized.get("gene_count"),
                        "qc_flag": normalized.get("qc_flag"),
                    },
                )
            )
            seen.add(hpo_id)
            if len(extracted) >= limit:
                break
        return extracted


def _extract_original_rows(data: Any) -> list[Any]:
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []

    for key in (
        "mapped_terms",
        "mapped_rows",
        "mapped",
        "matches",
        "results",
        "predictions",
        "extracted_phenotypes",
        "hpo_terms",
        "data",
    ):
        value = data.get(key)
        if isinstance(value, list):
            return value

    rows: list[Any] = []
    for value in data.values():
        if isinstance(value, list):
            rows.extend(value)
        elif isinstance(value, dict):
            rows.extend(_extract_original_rows(value))
    return rows


def _normalize_row(row: Any) -> dict[str, Any] | None:
    if isinstance(row, str):
        hpo_id = _extract_hpo_id(row)
        if not hpo_id:
            return None
        return {"hpo_id": hpo_id, "matched_text": row}
    if not isinstance(row, dict):
        return None

    nested_hpo = row.get("hpo")
    hpo_id = _first_string(row, "hpo_id", "HPO_ID", "HPO", "hp_id", "hpoId", "term_id", "id")
    if not hpo_id and isinstance(nested_hpo, dict):
        hpo_id = _first_string(nested_hpo, "hpo_id", "HPO_ID", "id", "term_id")
    hpo_id = _extract_hpo_id(hpo_id or "")
    if not hpo_id:
        return None

    name = _first_string(row, "hpo_term", "hpo_name", "HPO_Name", "name", "label", "term", "hpo_label")
    if not name and isinstance(nested_hpo, dict):
        name = _first_string(nested_hpo, "hpo_term", "name", "label", "term")

    finding = _first_string(row, "finding", "clinical_finding", "input_text", "source_text", "text")
    region = _first_string(row, "region", "anatomical_region", "body_site")
    matched_term = _first_string(row, "matched_term", "matched_text", "synonym", "term_match")
    matched_text = matched_term or finding or name
    score = _first_value(row, "score", "similarity", "confidence", "cosine_similarity", "probability", "rank_score")
    genes = _first_value(row, "genes", "associated_genes", "gene_symbols")
    gene_count = _first_value(row, "gene_count", "genes_total", "total_genes")
    qc_flag = _first_value(row, "flag", "qc_flag", "llm_qc_flag")

    return {
        "hpo_id": hpo_id,
        "name": name,
        "finding": finding,
        "region": region,
        "matched_term": matched_term,
        "matched_text": matched_text,
        "score": score,
        "genes": _format_genes(genes),
        "gene_count": _int_value(gene_count, None),
        "qc_flag": qc_flag,
    }


def _first_string(row: dict[str, Any], *keys: str) -> str | None:
    value = _first_value(row, *keys)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _first_value(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _extract_hpo_id(value: str) -> str | None:
    cleaned = value.strip().replace("_", ":")
    if cleaned.startswith("http://purl.obolibrary.org/obo/HP:"):
        cleaned = cleaned.rsplit("/", 1)[-1]
    if cleaned.startswith("http://purl.obolibrary.org/obo/HP_"):
        cleaned = "HP:" + cleaned.rsplit("HP_", 1)[-1]
    if cleaned.startswith("HP:") and len(cleaned) >= 10:
        return cleaned[:10]
    return None


def _float_value(value: Any, default: float) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def _float_option(options: dict[str, str | int | float | bool], key: str, default: float) -> float:
    return _float_value(options.get(key), default)


def _int_option(options: dict[str, str | int | float | bool], key: str, default: int) -> int:
    value = options.get(key)
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _max_genes_option(options: dict[str, str | int | float | bool]) -> int | None:
    value = options.get("max_genes")
    if isinstance(value, str) and value.strip().lower() == "all":
        return -1
    return _int_option(options, "max_genes", 50)


def _int_value(value: Any, default: int | None) -> int | None:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _format_genes(value: Any) -> str | None:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if str(item).strip())
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _metadata_value(value: str | int | float | bool | None) -> str | int | float | bool | None:
    return value if isinstance(value, str | int | float | bool) else None
