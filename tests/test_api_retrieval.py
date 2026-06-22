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

