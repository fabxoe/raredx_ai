from __future__ import annotations

import json
import urllib.error
import urllib.request

from app.config import Settings


def available_chat_models(settings: Settings, provider: str) -> list[str]:
    provider_name = provider.strip().lower()
    if provider_name == "openai":
        return _openai_models(settings)
    if provider_name == "ollama":
        return [settings.ollama_chat_model]
    return []


def _openai_models(settings: Settings) -> list[str]:
    fallback = [settings.openai_model]
    if not settings.openai_api_key:
        return fallback

    request = urllib.request.Request(
        "https://api.openai.com/v1/models",
        headers={"Authorization": f"Bearer {settings.openai_api_key}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=10.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError):
        return fallback

    ids = [
        item.get("id")
        for item in payload.get("data", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    ]
    chat_like = sorted(
        {
            model_id
            for model_id in ids
            if model_id.startswith("gpt-")
            and "embedding" not in model_id
            and "audio" not in model_id
            and "image" not in model_id
            and "transcribe" not in model_id
            and "tts" not in model_id
        }
    )
    return _dedupe([settings.openai_model, *chat_like]) or fallback


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value and value not in seen:
            output.append(value)
            seen.add(value)
    return output
