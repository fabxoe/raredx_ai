from pathlib import Path

from app.etl.hpo_loader import load_knowledge_base
from app.retrieval.knowledge import KnowledgeIndex
from app.retrieval.original_hpo_mapper import OriginalHPOMapperAdapter


FIXTURES = Path(__file__).parent / "fixtures"


def _mapper() -> OriginalHPOMapperAdapter:
    kb = load_knowledge_base(
        hpo_obo_path=FIXTURES / "hp.obo",
        phenotype_hpoa_path=FIXTURES / "phenotype.hpoa",
        genes_to_phenotype_path=FIXTURES / "genes_to_phenotype.txt",
    )
    return OriginalHPOMapperAdapter(
        knowledge=KnowledgeIndex(kb),
        endpoint_url="http://example.test/hpo-mapper",
        timeout_seconds=1,
        source="original_hpo_mapper",
    )


def test_original_hpo_mapper_parses_protocol_two_rows() -> None:
    mapper = _mapper()
    response = {
        "mapped_rows": [
            {
                "finding": "seizure",
                "region": "brain",
                "hpo_id": "HP:0001250",
                "hpo_term": "Seizure",
                "matched_term": "Epileptic seizure",
                "genes": ["GENE1", "GENE2"],
                "score": 0.91,
                "flag": "",
            },
            {
                "finding": "not in fixture",
                "hpo_id": "NA",
                "hpo_term": "NA",
                "score": "",
            },
        ]
    }

    extracted = mapper._parse_response(response, limit=10, options={"protocol": "p2_qc", "threshold": 0.76})

    assert [item.hpo_id for item in extracted] == ["HP:0001250"]
    assert extracted[0].matched_text == "Epileptic seizure"
    assert extracted[0].confidence == 0.91
    assert extracted[0].metadata["protocol"] == "p2_qc"
    assert extracted[0].metadata["genes"] == "GENE1, GENE2"


def test_original_hpo_mapper_parses_protocol_three_nested_results() -> None:
    mapper = _mapper()
    response = {
        "results": [
            {
                "finding": "global developmental delay",
                "region": "development",
                "hpo": {"id": "http://purl.obolibrary.org/obo/HP_0001263", "name": "Global developmental delay"},
                "matched_text": "developmental delay",
                "similarity": "0.84",
            }
        ]
    }

    extracted = mapper._parse_response(
        response,
        limit=10,
        options={"protocol": "p3_llm_selection", "embed_model": "nomic-embed-text"},
    )

    assert [item.hpo_id for item in extracted] == ["HP:0001263"]
    assert extracted[0].confidence == 0.84
    assert extracted[0].metadata["llm_used"] is True
    assert extracted[0].metadata["embedding_model"] == "nomic-embed-text"


def test_original_hpo_mapper_builds_protocol_payload() -> None:
    mapper = _mapper()

    payload = mapper._build_payload(
        "Patient has seizures.",
        limit=30,
        options={
            "protocol": "p3_llm_selection",
            "top_k": 12,
            "threshold": 0.8,
            "embed_model": "nomic-embed-text",
            "max_genes": "all",
            "llm_provider": "openai",
            "chat_model": "gpt-4o-mini",
        },
    )

    assert payload["protocol"] == "p3_llm_selection"
    assert payload["top_k"] == 12
    assert payload["max_hpo_terms"] == 30
    assert payload["min_sim"] == 0.8
    assert payload["max_genes"] == -1
    assert payload["llm"]["enabled"] is True
    assert payload["llm"]["provider"] == "openai"


def test_original_hpo_mapper_does_not_apply_local_llm_qc() -> None:
    mapper = _mapper()

    assert mapper._should_apply_local_llm({"use_llm": True, "llm_provider": "off"}) is False
    assert mapper._should_apply_local_llm({"protocol": "p3_llm_selection"}) is False
