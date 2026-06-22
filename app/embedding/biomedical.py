import numpy as np


class BiomedicalEmbedder:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model: object | None = None

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 0), dtype=np.float32)
        model = self._load_model()
        vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(vectors, dtype=np.float32)

    def _load_model(self) -> object:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model


def phenotype_text(name: str, definition: str | None) -> str:
    if definition:
        return f"{name}. Definition: {definition}"
    return name

