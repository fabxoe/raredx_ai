"""Query interface for mapping clinical text to candidate HPO terms."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re

import numpy as np
import pandas as pd

from hpo_mapper.embed_index import (
    DEFAULT_EMBEDDINGS_PATH,
    DEFAULT_INDEX_PATH,
    DEFAULT_MODEL_NAME,
    get_embedding_backend,
    l2_normalize,
)


RESULT_COLUMNS = [
    "input_text",
    "rank",
    "hpo_id",
    "hpo_name",
    "matched_text",
    "match_type",
    "cosine_score",
    "threshold",
    "model_name",
    "duplicate_count",
    "other_matched_texts",
]

PHRASE_RESULT_COLUMNS = [
    "input_text",
    "phrase_id",
    "phenotype_phrase",
    "rank",
    "hpo_id",
    "hpo_name",
    "matched_text",
    "match_type",
    "cosine_score",
    "threshold",
    "model_name",
    "accepted",
]

PATIENT_HPO_COLUMNS = [
    "hpo_id",
    "hpo_name",
    "matched_text",
    "match_type",
    "cosine_score",
    "threshold",
    "model_name",
    "source_phrases",
]

MAX_OTHER_MATCHES = 5

_SENTENCE_SPLIT_RE = re.compile(r"[.!?\n]+")
_LIST_SPLIT_RE = re.compile(r"\s*(?:,|;|\band\b)\s+", flags=re.IGNORECASE)
_BOILERPLATE_PATTERNS = [
    re.compile(r"^\s*(?:a|an|the)?\s*\d+\s*[- ]?year[- ]?old\s+(?:male|female|man|woman|boy|girl|patient|child|adult)?\s*", re.IGNORECASE),
    re.compile(r"^\s*(?:male|female|man|woman|boy|girl|patient|child|adult)\s+", re.IGNORECASE),
    re.compile(r"^\s*(?:the\s+)?(?:patient|individual|child|adult)\s+", re.IGNORECASE),
    re.compile(r"^\s*(?:presents?\s+with|presented\s+with|show(?:s|ed)?|has|had|with|history\s+of)\s+", re.IGNORECASE),
    re.compile(r"^\s*(?:laboratory|lab)\s+(?:studies|tests|findings|results)\s+(?:reveal|reveals|revealed|show|shows|showed)\s+", re.IGNORECASE),
    re.compile(r"^\s*(?:reveals?|revealed|demonstrates?|demonstrated|notable\s+for)\s+", re.IGNORECASE),
]
_TRAILING_CONTEXT_RE = re.compile(r"\s+(?:was|were|is|are)\s+(?:noted|observed|seen|present|found)\s*$", re.IGNORECASE)
_NON_PHENOTYPE_RE = re.compile(
    r"^(?:a|an|the)?\s*(?:\d+\s*[- ]?year[- ]?old)?\s*(?:male|female|man|woman|boy|girl|patient|child|adult)?\s*$",
    re.IGNORECASE,
)


@lru_cache(maxsize=4)
def _load_index(index_path: str, embeddings_path: str) -> tuple[pd.DataFrame, np.ndarray]:
    index_df = pd.read_csv(index_path)
    vectors = np.load(embeddings_path)
    if len(index_df) != vectors.shape[0]:
        raise ValueError(
            f"Index row count ({len(index_df)}) does not match embeddings "
            f"row count ({vectors.shape[0]}). Rebuild the index."
        )
    return index_df, vectors


@lru_cache(maxsize=4)
def _load_embedding_backend(backend: str, model_name: str):
    return get_embedding_backend(backend=backend, model_name=model_name)


def map_text_to_hpo(
    text: str,
    top_k: int = 10,
    threshold: float = 0.40,
    *,
    deduplicate_hpo: bool = True,
    index_path: str | Path = DEFAULT_INDEX_PATH,
    embeddings_path: str | Path = DEFAULT_EMBEDDINGS_PATH,
    backend: str = "sentence-transformers",
    model_name: str = DEFAULT_MODEL_NAME,
) -> pd.DataFrame:
    """Return candidate HPO terms ranked by cosine similarity."""

    if not text or not text.strip():
        raise ValueError("text must be a non-empty string.")
    if top_k < 1:
        raise ValueError("top_k must be at least 1.")

    index_path = Path(index_path)
    embeddings_path = Path(embeddings_path)
    if not index_path.exists() or not embeddings_path.exists():
        raise FileNotFoundError(
            "HPO index files are missing. Run: python scripts/build_hpo_index.py"
        )

    index_df, vectors = _load_index(str(index_path), str(embeddings_path))
    embedding_backend = _load_embedding_backend(backend, model_name)
    query_vector = embedding_backend.embed([text])
    query_vector = l2_normalize(query_vector)[0]
    cosine_scores = vectors @ query_vector

    if len(index_df) == 0:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    sorted_indices = np.argsort(-cosine_scores)

    results = index_df.iloc[sorted_indices].copy()
    results.insert(0, "input_text", text)
    results["cosine_score"] = cosine_scores[sorted_indices].round(6)
    results["threshold"] = threshold
    results["model_name"] = getattr(embedding_backend, "model_name", model_name)
    results = results[results["cosine_score"] >= threshold]

    if deduplicate_hpo:
        results = _deduplicate_by_hpo(results)
    else:
        results["duplicate_count"] = 1
        results["other_matched_texts"] = ""

    results = results.head(top_k).copy()
    results.insert(1, "rank", range(1, len(results) + 1))
    return results.loc[:, RESULT_COLUMNS].reset_index(drop=True)


def extract_phenotype_phrases(text: str) -> list[str]:
    """Rule-based first-pass extraction of phenotype-level phrases."""

    if not text or not text.strip():
        return []

    phrases: list[str] = []
    seen: set[str] = set()
    for sentence in _SENTENCE_SPLIT_RE.split(text):
        sentence = sentence.strip()
        if not sentence:
            continue
        for fragment in _LIST_SPLIT_RE.split(sentence):
            phrase = _clean_phenotype_phrase(fragment)
            if not phrase:
                continue
            normalized = phrase.casefold()
            if normalized in seen:
                continue
            seen.add(normalized)
            phrases.append(phrase)
    return phrases


def map_phrases_to_hpo(
    text: str,
    top_k_per_phrase: int = 5,
    threshold: float = 0.40,
    *,
    index_path: str | Path = DEFAULT_INDEX_PATH,
    embeddings_path: str | Path = DEFAULT_EMBEDDINGS_PATH,
    backend: str = "sentence-transformers",
    model_name: str = DEFAULT_MODEL_NAME,
) -> pd.DataFrame:
    """Map each extracted phenotype phrase independently to HPO candidates."""

    if top_k_per_phrase < 1:
        raise ValueError("top_k_per_phrase must be at least 1.")

    phrase_frames: list[pd.DataFrame] = []
    for phrase_id, phrase in enumerate(extract_phenotype_phrases(text), start=1):
        phrase_results = map_text_to_hpo(
            phrase,
            top_k=top_k_per_phrase,
            threshold=threshold,
            deduplicate_hpo=True,
            index_path=index_path,
            embeddings_path=embeddings_path,
            backend=backend,
            model_name=model_name,
        )
        if phrase_results.empty:
            continue
        phrase_results = phrase_results.copy()
        phrase_results["input_text"] = text
        phrase_results.insert(1, "phrase_id", phrase_id)
        phrase_results.insert(2, "phenotype_phrase", phrase)
        phrase_results["accepted"] = phrase_results["cosine_score"] >= threshold
        phrase_frames.append(phrase_results)

    if not phrase_frames:
        return pd.DataFrame(columns=PHRASE_RESULT_COLUMNS)

    results = pd.concat(phrase_frames, ignore_index=True)
    return results.loc[:, PHRASE_RESULT_COLUMNS].reset_index(drop=True)


def aggregate_patient_hpo_set(results_df: pd.DataFrame) -> pd.DataFrame:
    """Deduplicate accepted phrase-level candidates into a patient HPO set."""

    if results_df.empty:
        return pd.DataFrame(columns=PATIENT_HPO_COLUMNS)
    if "accepted" not in results_df.columns:
        raise ValueError("results_df must include an accepted column.")

    accepted = results_df[results_df["accepted"]].copy()
    if accepted.empty:
        return pd.DataFrame(columns=PATIENT_HPO_COLUMNS)

    rows: list[pd.Series] = []
    for _, group in accepted.sort_values("cosine_score", ascending=False).groupby("hpo_id", sort=False):
        best = group.iloc[0].copy()
        best["source_phrases"] = "; ".join(_unique_other_matches(group["phenotype_phrase"].astype(str).tolist()))
        rows.append(best)

    patient_hpo = pd.DataFrame(rows).sort_values("cosine_score", ascending=False)
    return patient_hpo.loc[:, PATIENT_HPO_COLUMNS].reset_index(drop=True)


def _clean_phenotype_phrase(fragment: str) -> str:
    phrase = fragment.strip(" \t\r\n:-")
    phrase = re.sub(r"\s+", " ", phrase)
    if not phrase:
        return ""

    previous = None
    while previous != phrase:
        previous = phrase
        for pattern in _BOILERPLATE_PATTERNS:
            phrase = pattern.sub("", phrase).strip(" \t\r\n:-")
            phrase = re.sub(r"\s+", " ", phrase)

    phrase = _TRAILING_CONTEXT_RE.sub("", phrase).strip(" \t\r\n:-")
    phrase = re.sub(r"^(?:and|or)\s+", "", phrase, flags=re.IGNORECASE).strip()
    phrase = re.sub(r"\s+", " ", phrase)

    if not phrase or _NON_PHENOTYPE_RE.match(phrase):
        return ""
    if re.fullmatch(r"\d+(?:\.\d+)?", phrase):
        return ""
    return phrase


def _deduplicate_by_hpo(results: pd.DataFrame) -> pd.DataFrame:
    rows: list[pd.Series] = []
    for _, group in results.groupby("hpo_id", sort=False):
        best = group.iloc[0].copy()
        other_texts = _unique_other_matches(
            group["matched_text"].iloc[1:].astype(str).tolist(),
            exclude=str(best["matched_text"]),
        )
        best["duplicate_count"] = len(group)
        best["other_matched_texts"] = "; ".join(other_texts[:MAX_OTHER_MATCHES])
        rows.append(best)
    if not rows:
        return results.assign(duplicate_count=[], other_matched_texts=[])
    return pd.DataFrame(rows).sort_values("cosine_score", ascending=False)


def _unique_other_matches(values: list[str], exclude: str = "") -> list[str]:
    seen: set[str] = {exclude.casefold()} if exclude else set()
    unique_values: list[str] = []
    for value in values:
        normalized = value.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        unique_values.append(value)
    return unique_values
