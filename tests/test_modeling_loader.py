"""Tests for modeling CSV loading primitives."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.modeling.loader import (
    load_message_edge_csv,
    load_negative_pairs_csv,
    load_node_csv,
    load_pair_csv,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "modeling"


def test_load_node_csv_indexes_by_node_id_and_parses_rankable() -> None:
    nodes = load_node_csv(FIXTURE_DIR / "gene_nodes.csv")
    assert nodes["HGNC:1"]["node_type"] == "Gene"
    assert nodes["HGNC:5"]["rankable"] is False


def test_load_message_edge_csv_returns_all_relations() -> None:
    edges = load_message_edge_csv(FIXTURE_DIR / "training_message_edges.csv")
    relations = {e["relation"] for e in edges}
    assert relations == {"IS_A", "HAS_PHENOTYPE", "ASSOCIATED_WITH"}


def test_load_pair_csv_rejects_non_associated_with_rows(tmp_path: Path) -> None:
    bad = tmp_path / "bad.csv"
    bad.write_text("source_id,target_id,relation\nORPHA:1,HP:0000001,HAS_PHENOTYPE\n")
    with pytest.raises(ValueError):
        load_pair_csv(bad)


def test_load_negative_pairs_csv_returns_label_zero_pairs() -> None:
    negatives = load_negative_pairs_csv(FIXTURE_DIR / "negative_pairs.csv")
    assert len(negatives) == 6
    assert all(isinstance(p, tuple) and len(p) == 2 for p in negatives)
