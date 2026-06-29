from pathlib import Path

from fastapi.testclient import TestClient

from app.api.retrieval import get_retrieval_service
from app.config import get_settings
from app.etl.hpo_loader import load_knowledge_base
from app.etl.processed_store import save_knowledge_base
from app.main import create_app
from app.retrieval.knowledge import KnowledgeIndex
from app.retrieval.note_matcher import ClinicalNoteMatcher


FIXTURES = Path(__file__).parent / "fixtures"


def test_clinical_note_matcher_extracts_hpo_terms() -> None:
    kb = load_knowledge_base(
        hpo_obo_path=FIXTURES / "hp.obo",
        phenotype_hpoa_path=FIXTURES / "phenotype.hpoa",
    )
    matcher = ClinicalNoteMatcher(KnowledgeIndex(kb))

    extracted = matcher.extract("Patient has epileptic seizure and global developmental delay.")

    hpo_ids = {item.hpo_id for item in extracted}
    assert "HP:0001250" in hpo_ids
    assert "HP:0001263" in hpo_ids


def test_note_ic_endpoint(tmp_path: Path, monkeypatch) -> None:
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
        "/api/retrieval/note/ic",
        json={"clinical_note": "Patient has seizure and global developmental delay.", "top_k": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["hpo_mapper"] == "dictionary"
    assert body["query_hpo_terms"] == ["HP:0001263", "HP:0001250"]
    assert body["candidates"][0]["disease_id"] == "OMIM:312750"


def test_note_ic_endpoint_excludes_negated_hpo_from_ranking(tmp_path: Path, monkeypatch) -> None:
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
        "/api/retrieval/note/ic",
        json={
            "clinical_note": "Patient denies seizure and has microcephaly.",
            "top_k": 1,
            "hpo_mapper_options": {"negation_mode": "negex_lite"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["query_hpo_terms"] == ["HP:0000252"]
    by_id = {item["hpo_id"]: item for item in body["extracted_phenotypes"]}
    assert by_id["HP:0001250"]["metadata"]["context_label"] == "negated"
    assert by_id["HP:0001250"]["metadata"]["final_selected"] is False


def test_note_ic_endpoint_off_negation_keeps_negated_hpo(tmp_path: Path, monkeypatch) -> None:
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
        "/api/retrieval/note/ic",
        json={
            "clinical_note": "No seizure was observed.",
            "top_k": 1,
            "hpo_mapper_options": {"negation_mode": "off"},
        },
    )

    assert response.status_code == 200
    assert response.json()["query_hpo_terms"] == ["HP:0001250"]


def test_note_endpoint_can_disable_mapper(tmp_path: Path, monkeypatch) -> None:
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
        "/api/retrieval/note/ic",
        json={
            "clinical_note": "Patient has seizure.",
            "top_k": 1,
            "hpo_mapper": "off",
        },
    )

    assert response.status_code == 400
    assert "hpo_mapper is off" in response.json()["detail"]


def test_note_endpoint_reports_unconfigured_doc2hpo(tmp_path: Path, monkeypatch) -> None:
    kb = load_knowledge_base(
        hpo_obo_path=FIXTURES / "hp.obo",
        phenotype_hpoa_path=FIXTURES / "phenotype.hpoa",
        genes_to_phenotype_path=FIXTURES / "genes_to_phenotype.txt",
    )
    save_knowledge_base(kb, tmp_path)
    monkeypatch.setenv("RAREDX_PROCESSED_DIR", str(tmp_path))
    monkeypatch.delenv("RAREDX_DOC2HPO_URL", raising=False)
    get_settings.cache_clear()
    get_retrieval_service.cache_clear()

    client = TestClient(create_app())
    response = client.post(
        "/api/retrieval/note/ic",
        json={
            "clinical_note": "Patient has seizure.",
            "top_k": 1,
            "hpo_mapper": "doc2hpo",
        },
    )

    assert response.status_code == 503
    assert "doc2hpo mapper is not configured" in response.json()["detail"]
