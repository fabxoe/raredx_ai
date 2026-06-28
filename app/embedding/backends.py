from __future__ import annotations

import re
from dataclasses import dataclass


DEFAULT_EMBEDDING_BACKEND = "sapbert_faiss"
CUSTOM_EMBEDDING_BACKEND = "custom_sentence_transformer_faiss"
HPO_DEEPWALK_EMBEDDING_BACKEND = "hpo_deepwalk_faiss"
HPO_NODE2VEC_EMBEDDING_BACKEND = "hpo_node2vec_faiss"
HPO_GRAPH_EMBEDDING_BACKEND = "hpo_graph_embedding_faiss"
DEFAULT_EMBEDDING_MODEL = "cambridgeltl/SapBERT-from-PubMedBERT-fulltext"
DEFAULT_HPO_DEEPWALK_MODEL = "deepwalk_hash_dim128"
DEFAULT_HPO_NODE2VEC_MODEL = "node2vec_hash_dim128_p1_q0.5"


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
    HPO_DEEPWALK_EMBEDDING_BACKEND: EmbeddingBackend(
        key=HPO_DEEPWALK_EMBEDDING_BACKEND,
        label="HPO DeepWalk · FAISS",
        model_name=DEFAULT_HPO_DEEPWALK_MODEL,
        description="DeepWalk-style uniform random-walk HPO ontology embedding retrieval.",
    ),
    HPO_NODE2VEC_EMBEDDING_BACKEND: EmbeddingBackend(
        key=HPO_NODE2VEC_EMBEDDING_BACKEND,
        label="HPO Node2Vec · FAISS",
        model_name=DEFAULT_HPO_NODE2VEC_MODEL,
        description="Node2Vec-style biased random-walk HPO ontology embedding retrieval.",
    ),
}


def supported_embedding_backend_keys() -> list[str]:
    return [*EMBEDDING_BACKENDS, HPO_GRAPH_EMBEDDING_BACKEND]


def resolve_embedding_model(backend: str, requested_model: str | None = None) -> str:
    if backend == CUSTOM_EMBEDDING_BACKEND:
        model_name = (requested_model or "").strip()
        if not model_name:
            raise ValueError("embedding_model is required for custom_sentence_transformer_faiss")
        return model_name
    if backend in {HPO_DEEPWALK_EMBEDDING_BACKEND, HPO_GRAPH_EMBEDDING_BACKEND}:
        return DEFAULT_HPO_DEEPWALK_MODEL
    if backend == HPO_NODE2VEC_EMBEDDING_BACKEND:
        return DEFAULT_HPO_NODE2VEC_MODEL

    configured = EMBEDDING_BACKENDS.get(backend)
    if configured is None:
        raise ValueError(f"unsupported disease embedding backend: {backend}")
    return configured.model_name


def index_dir_name(backend: str, model_name: str) -> str:
    if backend == DEFAULT_EMBEDDING_BACKEND and model_name == DEFAULT_EMBEDDING_MODEL:
        return DEFAULT_EMBEDDING_BACKEND
    if backend in {HPO_DEEPWALK_EMBEDDING_BACKEND, HPO_GRAPH_EMBEDDING_BACKEND} and model_name == DEFAULT_HPO_DEEPWALK_MODEL:
        return HPO_DEEPWALK_EMBEDDING_BACKEND
    if backend == HPO_NODE2VEC_EMBEDDING_BACKEND and model_name == DEFAULT_HPO_NODE2VEC_MODEL:
        return HPO_NODE2VEC_EMBEDDING_BACKEND

    slug = re.sub(r"[^a-zA-Z0-9._-]+", "_", model_name).strip("_")
    return f"{backend}__{slug}"[:180]


def is_hpo_graph_embedding_backend(backend: str) -> bool:
    return backend in {
        HPO_DEEPWALK_EMBEDDING_BACKEND,
        HPO_NODE2VEC_EMBEDDING_BACKEND,
        HPO_GRAPH_EMBEDDING_BACKEND,
    }


def hpo_graph_strategy_for_backend(backend: str) -> str:
    if backend == HPO_NODE2VEC_EMBEDDING_BACKEND:
        return "node2vec"
    if backend in {HPO_DEEPWALK_EMBEDDING_BACKEND, HPO_GRAPH_EMBEDDING_BACKEND}:
        return "deepwalk"
    raise ValueError(f"unsupported HPO graph embedding backend: {backend}")
