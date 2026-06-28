from pathlib import Path

from fastapi.testclient import TestClient

from app.api.retrieval import get_retrieval_service
from app.config import get_settings
from app.etl.hpo_loader import load_knowledge_base
from app.etl.processed_store import save_knowledge_base
from app.main import create_app


FIXTURES = Path(__file__).parent / "fixtures"


def test_ic_retrieval_endpoint(tmp_path: Path, monkeypatch) -> None:
    kb = load_knowledge_base(
        hpo_obo_path=FIXTURES / "hp.obo",
        phenotype_hpoa_path=FIXTURES / "phenotype.hpoa",
        genes_to_phenotype_path=FIXTURES / "genes_to_phenotype.txt",
    )
    save_knowledge_base(kb, tmp_path)
    monkeypatch.setenv("RAREDX_PROCESSED_DIR", str(tmp_path))
    get_settings.cache_clear()
    get_retrieval_service.cache_clear()

    client = TestClient(create_app())
    response = client.post("/api/retrieval/ic", json={"hpo_terms": ["HP:0001250"], "top_k": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["candidates"][0]["disease_id"] == "OMIM:312750"


def test_graph_retrieval_endpoint(tmp_path: Path, monkeypatch) -> None:
    kb = load_knowledge_base(
        hpo_obo_path=FIXTURES / "hp.obo",
        phenotype_hpoa_path=FIXTURES / "phenotype.hpoa",
        genes_to_phenotype_path=FIXTURES / "genes_to_phenotype.txt",
    )
    save_knowledge_base(kb, tmp_path)
    monkeypatch.setenv("RAREDX_PROCESSED_DIR", str(tmp_path))
    get_settings.cache_clear()
    get_retrieval_service.cache_clear()

    client = TestClient(create_app())
    response = client.post("/api/retrieval/graph", json={"hpo_terms": ["HP:0001250"], "top_k": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["candidates"][0]["score_components"]["graph_score"] == 1.0
    assert body["candidates"][0]["graph_paths"]


def test_ic_retrieval_endpoint_rejects_unknown_hpo(tmp_path: Path, monkeypatch) -> None:
    kb = load_knowledge_base(
        hpo_obo_path=FIXTURES / "hp.obo",
        phenotype_hpoa_path=FIXTURES / "phenotype.hpoa",
    )
    save_knowledge_base(kb, tmp_path)
    monkeypatch.setenv("RAREDX_PROCESSED_DIR", str(tmp_path))
    get_settings.cache_clear()
    get_retrieval_service.cache_clear()

    client = TestClient(create_app())
    response = client.post("/api/retrieval/ic", json={"hpo_terms": ["HP:DOES_NOT_EXIST"], "top_k": 1})

    assert response.status_code == 400


def test_frontend_is_served() -> None:
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert "RARE_DX_AI" in response.text


def test_phenotype_search_endpoint(tmp_path: Path, monkeypatch) -> None:
    kb = load_knowledge_base(
        hpo_obo_path=FIXTURES / "hp.obo",
        phenotype_hpoa_path=FIXTURES / "phenotype.hpoa",
    )
    save_knowledge_base(kb, tmp_path)
    monkeypatch.setenv("RAREDX_PROCESSED_DIR", str(tmp_path))
    get_settings.cache_clear()
    get_retrieval_service.cache_clear()

    client = TestClient(create_app())
    response = client.get("/api/retrieval/phenotypes", params={"q": "seizure"})

    assert response.status_code == 200
    assert response.json()[0] == {"hpo_id": "HP:0001250", "name": "Seizure"}


def test_hpo_mapper_capabilities_endpoint() -> None:
    client = TestClient(create_app())

    response = client.get("/api/hpo-mappers")

    assert response.status_code == 200
    body = response.json()
    ids = {item["id"] for item in body}
    assert {"dictionary", "doc2hpo", "original_hpo_mapper", "off"}.issubset(ids)
    original = next(item for item in body if item["id"] == "original_hpo_mapper")
    option_keys = {item["key"] for item in original["options"]}
    assert {"protocol", "use_llm", "top_k", "threshold"}.issubset(option_keys)


def test_ranking_method_capabilities_endpoint() -> None:
    client = TestClient(create_app())

    response = client.get("/api/retrieval/ranking-methods")

    assert response.status_code == 200
    body = response.json()
    ids = {item["id"] for item in body}
    assert ids == {"ic", "embedding", "graph", "hybrid"}
    graph = next(item for item in body if item["id"] == "graph")
    graph_option_keys = {item["key"] for item in graph["options"]}
    assert graph_option_keys == {"graph_evidence_mode"}
    hybrid = next(item for item in body if item["id"] == "hybrid")
    option_keys = {item["key"] for item in hybrid["options"]}
    assert {"embedding_backend", "ic_weight", "embedding_weight", "graph_weight"}.issubset(option_keys)


def test_embedding_retrieval_rejects_unsupported_backend(tmp_path: Path, monkeypatch) -> None:
    kb = load_knowledge_base(
        hpo_obo_path=FIXTURES / "hp.obo",
        phenotype_hpoa_path=FIXTURES / "phenotype.hpoa",
        genes_to_phenotype_path=FIXTURES / "genes_to_phenotype.txt",
    )
    save_knowledge_base(kb, tmp_path)
    monkeypatch.setenv("RAREDX_PROCESSED_DIR", str(tmp_path))
    get_settings.cache_clear()
    get_retrieval_service.cache_clear()

    client = TestClient(create_app())
    response = client.post(
        "/api/retrieval/embedding",
        json={
            "hpo_terms": ["HP:0001250"],
            "top_k": 1,
            "ranking_options": {"embedding_backend": "unknown_backend"},
        },
    )

    assert response.status_code == 400
    assert "unsupported disease embedding backend" in response.json()["detail"]
