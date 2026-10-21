"""Tests for modeling CSV loading primitives."""

from __future__ import annotations

from pathlib import Path

import pytest
import torch

from app.modeling.loader import (
    build_hetero_data,
    build_node_index,
    load_message_edge_csv,
    load_negative_pairs_csv,
    load_node_csv,
    load_pair_csv,
    split_negative_pairs,
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


def test_split_negative_pairs_matches_requested_sizes_and_is_disjoint() -> None:
    negatives = load_negative_pairs_csv(FIXTURE_DIR / "negative_pairs.csv")
    result = split_negative_pairs(negatives, split_sizes={"train": 4, "validation": 1, "test": 1})
    assert [len(result[name]) for name in ("train", "validation", "test")] == [4, 1, 1]
    seen = [p for group in result.values() for p in group]
    assert len(seen) == len(set(seen))


def test_split_negative_pairs_is_deterministic_for_fixed_seed() -> None:
    negatives = load_negative_pairs_csv(FIXTURE_DIR / "negative_pairs.csv")
    first = split_negative_pairs(negatives, split_sizes={"train": 4, "validation": 1, "test": 1}, seed=42)
    second = split_negative_pairs(list(reversed(negatives)), split_sizes={"train": 4, "validation": 1, "test": 1}, seed=42)
    assert first == second


def test_split_negative_pairs_rejects_oversized_request() -> None:
    negatives = load_negative_pairs_csv(FIXTURE_DIR / "negative_pairs.csv")
    with pytest.raises(ValueError):
        split_negative_pairs(negatives, split_sizes={"train": 10, "validation": 1, "test": 1})


def test_build_node_index_separates_rankable_ids() -> None:
    nodes = load_node_csv(FIXTURE_DIR / "gene_nodes.csv")
    index = build_node_index(nodes)
    assert "HGNC:5" in index.ids and "HGNC:5" not in index.rankable
    assert "HGNC:1" in index.rankable
    assert index.index["HGNC:1"] == index.ids.index("HGNC:1")


def test_build_hetero_data_has_forward_and_reverse_edge_types() -> None:
    genes = build_node_index(load_node_csv(FIXTURE_DIR / "gene_nodes.csv"))
    diseases = build_node_index(load_node_csv(FIXTURE_DIR / "disease_nodes.csv"))
    phenotypes = build_node_index(load_node_csv(FIXTURE_DIR / "hpo_nodes.csv"))
    edges = load_message_edge_csv(FIXTURE_DIR / "training_message_edges.csv")
    data = build_hetero_data(
        {"Gene": genes, "Disease": diseases, "Phenotype": phenotypes}, edges
    )
    assert ("Disease", "ASSOCIATED_WITH", "Gene") in data.edge_types
    assert ("Gene", "rev_ASSOCIATED_WITH", "Disease") in data.edge_types
    assert ("Phenotype", "rev_IS_A", "Phenotype") in data.edge_types
    assert ("Phenotype", "rev_HAS_PHENOTYPE", "Disease") in data.edge_types
    forward = data["Disease", "ASSOCIATED_WITH", "Gene"].edge_index
    reverse = data["Gene", "rev_ASSOCIATED_WITH", "Disease"].edge_index
    assert forward.shape[1] == reverse.shape[1] == 4
    assert torch.equal(forward[[0, 1]], reverse[[1, 0]])


def test_build_hetero_data_excludes_test_split_pairs() -> None:
    # training_message_edges.csv fixture must not contain the ORPHA:4/HGNC:5 test pair
    edges = load_message_edge_csv(FIXTURE_DIR / "training_message_edges.csv")
    test_pairs = set(load_pair_csv(FIXTURE_DIR / "splits/test.csv"))
    message_pairs = {
        (e["source_id"], e["target_id"]) for e in edges if e["relation"] == "ASSOCIATED_WITH"
    }
    assert not (message_pairs & test_pairs)
