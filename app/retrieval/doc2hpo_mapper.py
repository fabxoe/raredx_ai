import json
import urllib.error
import urllib.request
from typing import Any

from app.retrieval.knowledge import KnowledgeIndex
from app.retrieval.note_matcher import ExtractedPhenotype


class Doc2HPOMapper:
    def __init__(self, knowledge: KnowledgeIndex, endpoint_url: str | None, timeout_seconds: float) -> None:
        self.knowledge = knowledge
        self.endpoint_url = endpoint_url
        self.timeout_seconds = timeout_seconds

    def extract(self, clinical_note: str, limit: int = 30) -> list[ExtractedPhenotype]:
        if not self.endpoint_url:
            raise RuntimeError("Doc2HPO mapper is not configured. Set RAREDX_DOC2HPO_URL to enable it.")

        payload = json.dumps({"clinical_note": clinical_note, "top_k": limit}).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint_url,
            data=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Doc2HPO mapper request failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError("Doc2HPO mapper returned invalid JSON") from exc

        return self._parse_response(data, limit)

    def _parse_response(self, data: Any, limit: int) -> list[ExtractedPhenotype]:
        rows = _extract_rows(data)
        extracted: list[ExtractedPhenotype] = []
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            hpo_id = _first_string(row, "hpo_id", "id", "HPO_ID", "HPO")
            if not hpo_id or hpo_id in seen or hpo_id not in self.knowledge.phenotypes:
                continue
            term = self.knowledge.phenotypes[hpo_id]
            matched_text = _first_string(row, "matched_text", "matched_term", "finding", "term") or term.name
            confidence = _first_float(row, "confidence", "score", "similarity") or 0.75
            extracted.append(
                ExtractedPhenotype(
                    hpo_id=hpo_id,
                    name=term.name,
                    matched_text=matched_text,
                    confidence=max(0.0, min(1.0, confidence)),
                    source="doc2hpo",
                )
            )
            seen.add(hpo_id)
            if len(extracted) >= limit:
                break
        return extracted


def _extract_rows(data: Any) -> list[Any]:
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in ("extracted_phenotypes", "hpo_terms", "matches", "results", "mapped_terms"):
        value = data.get(key)
        if isinstance(value, list):
            return value
    return []


def _first_string(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _first_float(row: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = row.get(key)
        if isinstance(value, int | float):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                continue
    return None
