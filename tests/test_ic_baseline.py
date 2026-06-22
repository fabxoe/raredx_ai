from pathlib import Path

from app.etl.hpo_loader import load_knowledge_base
from app.retrieval.ic_baseline import ICBaselineRanker
from app.retrieval.knowledge import KnowledgeIndex


FIXTURES = Path(__file__).parent / "fixtures"


def test_ic_baseline_ranks_disease_by_weighted_overlap() -> None:
    kb = load_knowledge_base(
        hpo_obo_path=FIXTURES / "hp.obo",
        phenotype_hpoa_path=FIXTURES / "phenotype.hpoa",
        genes_to_phenotype_path=FIXTURES / "genes_to_phenotype.txt",
    )
    ranker = ICBaselineRanker(KnowledgeIndex(kb))

    candidates = ranker.rank(["HP:0001250", "HP:0001263"], top_k=5)

    assert candidates[0].disease_id == "OMIM:312750"
    assert candidates[0].score == 1.0
    assert candidates[0].associated_genes == ["MECP2"]

