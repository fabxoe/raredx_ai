from pathlib import Path

from app.etl.hpo_loader import load_genes_to_phenotype, load_hpo_obo, load_phenotype_hpoa


FIXTURES = Path(__file__).parent / "fixtures"


def test_load_hpo_obo_parses_terms_and_skips_obsolete() -> None:
    terms = load_hpo_obo(FIXTURES / "hp.obo")

    assert terms["HP:0001250"].name == "Seizure"
    assert terms["HP:0001250"].parents == ("HP:0000707",)
    assert "HP:9999999" not in terms


def test_load_phenotype_hpoa_excludes_negative_annotations() -> None:
    annotations = load_phenotype_hpoa(FIXTURES / "phenotype.hpoa")

    assert len(annotations) == 3
    assert all(annotation.hpo_id != "HP:0001250" or annotation.disease_id != "OMIM:999999" for annotation in annotations)


def test_load_genes_to_phenotype() -> None:
    annotations = load_genes_to_phenotype(FIXTURES / "genes_to_phenotype.txt")

    assert annotations[0].gene_symbol == "MECP2"
    assert annotations[0].disease_id == "OMIM:312750"

