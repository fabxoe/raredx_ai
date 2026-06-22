from app.graph.schema import CONSTRAINTS


def test_neo4j_constraints_cover_core_nodes() -> None:
    joined = "\n".join(CONSTRAINTS)

    assert "Disease" in joined
    assert "Phenotype" in joined
    assert "Gene" in joined

