import json
import urllib.error
import urllib.request
from dataclasses import replace
from typing import Any, Protocol

from app.config import Settings
from app.retrieval.note_matcher import ExtractedPhenotype


class JSONChatClient(Protocol):
    def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        ...


class OpenAIJSONChatClient:
    def __init__(self, api_key: str, model: str, timeout_seconds: float = 30.0) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
        request = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        data = _post_json(request, self.timeout_seconds)
        content = data["choices"][0]["message"]["content"]
        return _loads_object(content)


class OllamaJSONChatClient:
    def __init__(self, base_url: str, model: str, timeout_seconds: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "format": "json",
            "stream": False,
            "options": {"temperature": 0},
        }
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        data = _post_json(request, self.timeout_seconds)
        content = data.get("message", {}).get("content", "")
        return _loads_object(content)


class PhenotypeLLMSelector:
    def __init__(self, client: JSONChatClient, provider: str, model: str) -> None:
        self.client = client
        self.provider = provider
        self.model = model

    def select(
        self,
        clinical_note: str,
        candidates: list[ExtractedPhenotype],
        protocol: str,
    ) -> list[ExtractedPhenotype]:
        if not candidates:
            return []

        response = self.client.complete_json(
            system_prompt=_system_prompt(protocol),
            user_prompt=_user_prompt(clinical_note, candidates),
        )
        selected_ids = _string_set(response.get("selected_hpo_ids"))
        rejected_ids = _string_set(response.get("rejected_hpo_ids"))
        notes = response.get("notes") if isinstance(response.get("notes"), dict) else {}

        if not selected_ids and protocol == "p2_qc":
            selected_ids = {item.hpo_id for item in candidates} - rejected_ids
        selected_ids = selected_ids & {item.hpo_id for item in candidates}

        output: list[ExtractedPhenotype] = []
        for rank, item in enumerate(candidates, start=1):
            keep = item.hpo_id in selected_ids
            if protocol == "p2_qc" and item.hpo_id not in rejected_ids:
                keep = True
            metadata = {
                **(item.metadata or {}),
                "llm_used": True,
                "llm_provider": self.provider,
                "llm_model": self.model,
                "llm_protocol": protocol,
                "llm_candidate_rank": rank,
                "llm_qc_status": "selected" if keep else "rejected",
                "llm_note": str(notes.get(item.hpo_id, "")) if notes else "",
            }
            if keep:
                output.append(replace(item, metadata=metadata))
        return output


def build_phenotype_llm_selector(
    settings: Settings,
    provider_override: str | None = None,
    model_override: str | None = None,
) -> PhenotypeLLMSelector:
    provider = (provider_override or settings.llm_provider).strip().lower()
    if provider == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("LLM QC requires OPENAI_API_KEY when RAREDX_LLM_PROVIDER=openai.")
        model = model_override or settings.openai_model
        return PhenotypeLLMSelector(
            OpenAIJSONChatClient(settings.openai_api_key, model),
            provider="openai",
            model=model,
        )
    if provider == "ollama":
        model = model_override or settings.ollama_chat_model
        return PhenotypeLLMSelector(
            OllamaJSONChatClient(settings.ollama_url, model),
            provider="ollama",
            model=model,
        )
    raise RuntimeError("LLM QC is disabled. Set RAREDX_LLM_PROVIDER=openai or ollama.")


def _system_prompt(protocol: str) -> str:
    task = "reject clearly unsupported HPO candidates" if protocol == "p2_qc" else "select the best supported HPO candidates"
    return (
        "You are a clinical phenotype mapping quality-control assistant. "
        f"Your task is to {task}. Use only the provided candidate HPO IDs; do not invent new terms. "
        "Return JSON with selected_hpo_ids, rejected_hpo_ids, and notes keyed by HPO ID."
    )


def _user_prompt(clinical_note: str, candidates: list[ExtractedPhenotype]) -> str:
    candidate_rows = [
        {
            "hpo_id": item.hpo_id,
            "name": item.name,
            "matched_text": item.matched_text,
            "confidence": item.confidence,
        }
        for item in candidates
    ]
    return json.dumps(
        {
            "clinical_note": clinical_note,
            "candidate_hpo_terms": candidate_rows,
            "expected_json": {
                "selected_hpo_ids": ["HP:0000000"],
                "rejected_hpo_ids": ["HP:0000001"],
                "notes": {"HP:0000000": "brief reason"},
            },
        },
        ensure_ascii=False,
    )


def _post_json(request: urllib.request.Request, timeout_seconds: float) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"LLM request failed: {exc}") from exc
    except (json.JSONDecodeError, KeyError, IndexError) as exc:
        raise RuntimeError("LLM returned an invalid response") from exc


def _loads_object(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("LLM returned invalid JSON content") from exc
    if not isinstance(data, dict):
        raise RuntimeError("LLM JSON content must be an object")
    return data


def _string_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {item for item in value if isinstance(item, str)}
