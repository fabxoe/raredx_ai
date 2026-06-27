import json
import sqlite3
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from app.config import get_settings
from app.original_hpo_mapper_wrapper import app, get_store


def test_original_hpo_mapper_wrapper_maps_p1(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "hpo_mapper.db"
    _write_fixture_db(db_path)
    monkeypatch.setenv("RAREDX_ORIGINAL_HPO_MAPPER_DB_PATH", str(db_path))
    monkeypatch.setattr(
        "app.original_hpo_mapper_wrapper._ollama_embedding",
        lambda model, prompt: np.array([1.0, 0.0], dtype=float),
    )
    get_store.cache_clear()
    get_settings.cache_clear()

    client = TestClient(app)
    response = client.post(
        "/map",
        json={
            "clinical_note": "The patient has seizure.",
            "protocol": "p1",
            "top_k": 2,
            "threshold": 0.7,
            "embed_model": "nomic-embed-text",
            "max_genes": 2,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["protocol"] == "p1"
    assert body["mapped_rows"][0]["hpo_id"] == "HP:0001250"
    assert body["mapped_rows"][0]["hpo_term"] == "Seizure"
    assert body["mapped_rows"][0]["genes"] == ["GENE1", "GENE2"]
    assert body["mapped_rows"][0]["gene_count"] == 3


def test_original_hpo_mapper_wrapper_health_reports_store(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "hpo_mapper.db"
    _write_fixture_db(db_path)
    monkeypatch.setenv("RAREDX_ORIGINAL_HPO_MAPPER_DB_PATH", str(db_path))
    get_store.cache_clear()
    get_settings.cache_clear()

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["hpo_embeddings"] == 2


def test_original_hpo_mapper_wrapper_reports_missing_openai_key(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "hpo_mapper.db"
    _write_fixture_db(db_path)
    monkeypatch.setenv("RAREDX_ORIGINAL_HPO_MAPPER_DB_PATH", str(db_path))
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setattr(
        "app.original_hpo_mapper_wrapper._ollama_embedding",
        lambda model, prompt: np.array([1.0, 0.0], dtype=float),
    )
    get_store.cache_clear()
    get_settings.cache_clear()

    client = TestClient(app)
    response = client.post(
        "/map",
        json={
            "clinical_note": "The patient has seizure.",
            "protocol": "p2_qc",
            "top_k": 2,
            "threshold": 0.7,
            "embed_model": "nomic-embed-text",
            "llm": {"enabled": True, "provider": "openai", "chat_model": ""},
        },
    )

    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.json()["detail"]


def _write_fixture_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE hpo_synonym_embeddings(hpo_id TEXT, hpo_name TEXT, term TEXT, embedding TEXT)")
        conn.execute("CREATE TABLE hpo_gene(hpo_id TEXT, genes TEXT)")
        conn.execute(
            "INSERT INTO hpo_synonym_embeddings VALUES (?, ?, ?, ?)",
            ("HP:0001250", "Seizure", "seizure", json.dumps([1.0, 0.0])),
        )
        conn.execute(
            "INSERT INTO hpo_synonym_embeddings VALUES (?, ?, ?, ?)",
            ("HP:0001263", "Global developmental delay", "developmental delay", json.dumps([0.0, 1.0])),
        )
        conn.execute("INSERT INTO hpo_gene VALUES (?, ?)", ("HP:0001250", "GENE1, GENE2, GENE3"))
        conn.commit()
    finally:
        conn.close()
