"""Embedding backends and local vector index construction for HPO terms."""

from __future__ import annotations

import argparse
from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_TERMS_PATH = Path("data/processed/hpo_terms.csv")
DEFAULT_EMBEDDINGS_PATH = Path("data/processed/hpo_embeddings.npy")
DEFAULT_INDEX_PATH = Path("data/processed/hpo_terms_index.csv")


class EmbeddingBackend(ABC):
    """Interface for replaceable embedding providers."""

    model_name: str

    @abstractmethod
    def embed(self, texts: list[str]) -> np.ndarray:
        """Return a 2D numpy array of embeddings for the provided texts."""


class SentenceTransformerBackend(EmbeddingBackend):
    """Local sentence-transformers embedding backend."""

    def __init__(self, model_name: str = DEFAULT_MODEL_NAME):
        self.model_name = model_name
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers is required for the default embedding backend. "
                "Install dependencies with: pip install -r requirements.txt"
            ) from exc
        try:
            self.model = SentenceTransformer(model_name, local_files_only=True)
        except Exception:
            self.model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = self.model.encode(
            texts,
            batch_size=64,
            convert_to_numpy=True,
            show_progress_bar=len(texts) > 1,
        )
        return np.asarray(vectors, dtype=np.float32)


def get_embedding_backend(
    backend: str = "sentence-transformers",
    model_name: str = DEFAULT_MODEL_NAME,
) -> EmbeddingBackend:
    """Factory for embedding backends.

    The backend switch keeps the index builder ready for future providers such
    as Ollama's nomic-embed-text without changing mapper code.
    """

    if backend == "sentence-transformers":
        return SentenceTransformerBackend(model_name=model_name)
    if backend == "ollama":
        raise NotImplementedError(
            "Ollama embeddings are not implemented yet. Add an EmbeddingBackend "
            "that calls nomic-embed-text and returns numpy arrays."
        )
    raise ValueError(f"Unknown embedding backend: {backend}")


def l2_normalize(vectors: np.ndarray) -> np.ndarray:
    """L2-normalize embeddings row-wise."""

    vectors = np.asarray(vectors, dtype=np.float32)
    if vectors.ndim == 1:
        vectors = vectors.reshape(1, -1)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-12)
    return vectors / norms


def build_hpo_embedding_index(
    terms_path: str | Path = DEFAULT_TERMS_PATH,
    embeddings_path: str | Path = DEFAULT_EMBEDDINGS_PATH,
    index_path: str | Path = DEFAULT_INDEX_PATH,
    backend: str = "sentence-transformers",
    model_name: str = DEFAULT_MODEL_NAME,
) -> tuple[pd.DataFrame, np.ndarray]:
    """Embed searchable HPO rows, normalize vectors, and save index artifacts."""

    terms_path = Path(terms_path)
    if not terms_path.exists():
        raise FileNotFoundError(
            f"Terms CSV not found: {terms_path}. Run scripts/build_hpo_index.py first."
        )

    terms_df = pd.read_csv(terms_path)
    if "matched_text" not in terms_df.columns:
        raise ValueError(f"{terms_path} must contain a matched_text column.")
    texts = terms_df["matched_text"].fillna("").astype(str).tolist()

    embedding_backend = get_embedding_backend(backend=backend, model_name=model_name)
    vectors = embedding_backend.embed(texts)
    vectors = l2_normalize(vectors)

    embeddings_path = Path(embeddings_path)
    index_path = Path(index_path)
    embeddings_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(embeddings_path, vectors)

    index_df = terms_df.copy()
    index_df["model_name"] = embedding_backend.model_name
    index_df.to_csv(index_path, index=False)
    return index_df, vectors


def main() -> None:
    parser = argparse.ArgumentParser(description="Build normalized HPO embeddings.")
    parser.add_argument("--terms_path", default=str(DEFAULT_TERMS_PATH))
    parser.add_argument("--embeddings_path", default=str(DEFAULT_EMBEDDINGS_PATH))
    parser.add_argument("--index_path", default=str(DEFAULT_INDEX_PATH))
    parser.add_argument("--backend", default="sentence-transformers")
    parser.add_argument("--model_name", default=DEFAULT_MODEL_NAME)
    args = parser.parse_args()

    index_df, vectors = build_hpo_embedding_index(
        terms_path=args.terms_path,
        embeddings_path=args.embeddings_path,
        index_path=args.index_path,
        backend=args.backend,
        model_name=args.model_name,
    )
    print(
        f"Wrote {len(index_df):,} rows and embeddings with shape {vectors.shape} "
        f"to {args.index_path} and {args.embeddings_path}"
    )


if __name__ == "__main__":
    main()
