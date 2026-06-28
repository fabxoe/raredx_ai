from __future__ import annotations

import re
from dataclasses import dataclass


DEFAULT_EMBEDDING_BACKEND = "sapbert_faiss"
CUSTOM_EMBEDDING_BACKEND = "custom_sentence_transformer_faiss"
DEFAULT_EMBEDDING_MODEL = "cambridgeltl/SapBERT-from-PubMedBERT-fulltext"


@dataclass(frozen=True)
class EmbeddingBackend:
    key: str
    label: str
    model_name: str
    description: str


EMBEDDING_BACKENDS: dict[str, EmbeddingBackend] = {
    DEFAULT_EMBEDDING_BACKEND: EmbeddingBackend(
        key=DEFAULT_EMBEDDING_BACKEND,
        label="SapBERT · FAISS",
        model_name=DEFAULT_EMBEDDING_MODEL,
        description="Biomedical synonym-aware sentence-transformer disease profile retrieval.",
    ),
    CUSTOM_EMBEDDING_BACKEND: EmbeddingBackend(
        key=CUSTOM_EMBEDDING_BACKEND,
        label="Custom sentence-transformer · FAISS",
        model_name=DEFAULT_EMBEDDING_MODEL,
        description="User-selected sentence-transformer disease profile retrieval.",
    ),
}


def supported_embedding_backend_keys() -> list[str]:
    return list(EMBEDDING_BACKENDS)


def resolve_embedding_model(backend: str, requested_model: str | None = None) -> str:
    if backend == CUSTOM_EMBEDDING_BACKEND:
        model_name = (requested_model or "").strip()
        if not model_name:
            raise ValueError("embedding_model is required for custom_sentence_transformer_faiss")
        return model_name

    configured = EMBEDDING_BACKENDS.get(backend)
    if configured is None:
        raise ValueError(f"unsupported disease embedding backend: {backend}")
    return configured.model_name


def index_dir_name(backend: str, model_name: str) -> str:
    if backend == DEFAULT_EMBEDDING_BACKEND and model_name == DEFAULT_EMBEDDING_MODEL:
        return DEFAULT_EMBEDDING_BACKEND

    slug = re.sub(r"[^a-zA-Z0-9._-]+", "_", model_name).strip("_")
    return f"{backend}__{slug}"[:180]
