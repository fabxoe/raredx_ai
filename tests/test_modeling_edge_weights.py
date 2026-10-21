"""Tests for loading ablation edge weights and attaching them to a graph."""

from __future__ import annotations

from pathlib import Path

import pytest
import torch

from app.modeling.edge_weights import (
    DEFAULT_WEIGHT,
    DG_EDGE_TYPE,
    DG_REVERSE_EDGE_TYPE,
    attach_associated_with_weights,
    load_ablation_weights,
)
from app.modeling.loader import load_graph_package

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "modeling"
ABLATIONS_DIR = FIXTURE_DIR / "ablations"


def test_load_ablation_weights_reads_edge_weight_column() -> None:
    weights = load_ablation_weights(ABLATIONS_DIR / "A_train.csv")
    assert weights[("ORPHA:1", "HGNC:1")] == 1.0
    assert weights[("ORPHA:2", "HGNC:2")] == 0.8
    assert weights[("ORPHA:4", "HGNC:4")] == 0.5


def test_load_ablation_weights_defaults_to_one_without_edge_weight_column() -> None:
    weights = load_ablation_weights(ABLATIONS_DIR / "C_train.csv")
    assert weights[("ORPHA:1", "HGNC:1")] == DEFAULT_WEIGHT
    assert weights[("ORPHA:3", "HGNC:3")] == DEFAULT_WEIGHT


def test_attach_associated_with_weights_aligns_with_edge_index_order() -> None:
    package = load_graph_package(FIXTURE_DIR, seed=42)
    weights = load_ablation_weights(ABLATIONS_DIR / "A_train.csv")

    weighted = attach_associated_with_weights(package.data, package.node_indexes, weights)

    disease_ids = package.node_indexes["Disease"].ids
    gene_ids = package.node_indexes["Gene"].ids
    forward_index = weighted[DG_EDGE_TYPE].edge_index
    forward_weight = weighted[DG_EDGE_TYPE].edge_weight
    assert forward_weight.shape[0] == forward_index.shape[1]
    for position in range(forward_index.shape[1]):
        d, g = forward_index[:, position].tolist()
        expected = weights[(disease_ids[d], gene_ids[g])]
        assert forward_weight[position].item() == pytest.approx(expected)

    reverse_index = weighted[DG_REVERSE_EDGE_TYPE].edge_index
    reverse_weight = weighted[DG_REVERSE_EDGE_TYPE].edge_weight
    assert reverse_weight.shape[0] == reverse_index.shape[1]
    for position in range(reverse_index.shape[1]):
        g, d = reverse_index[:, position].tolist()
        expected = weights[(disease_ids[d], gene_ids[g])]
        assert reverse_weight[position].item() == pytest.approx(expected)


def test_attach_associated_with_weights_defaults_missing_pairs_to_one() -> None:
    package = load_graph_package(FIXTURE_DIR, seed=42)
    weighted = attach_associated_with_weights(package.data, package.node_indexes, {})
    assert torch.equal(
        weighted[DG_EDGE_TYPE].edge_weight,
        torch.ones(weighted[DG_EDGE_TYPE].edge_index.shape[1]),
    )


def test_attach_associated_with_weights_does_not_mutate_input() -> None:
    package = load_graph_package(FIXTURE_DIR, seed=42)
    weights = load_ablation_weights(ABLATIONS_DIR / "A_train.csv")
    attach_associated_with_weights(package.data, package.node_indexes, weights)
    assert not hasattr(package.data[DG_EDGE_TYPE], "edge_weight") or (
        package.data[DG_EDGE_TYPE].edge_weight is None
    )
