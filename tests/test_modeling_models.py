"""Tests for the no-graph baseline model (gene prior + bilinear scorer)."""

from __future__ import annotations

import torch

from app.modeling.models import BaselineScorer, compute_gene_prior


def test_compute_gene_prior_normalizes_and_defaults_to_zero() -> None:
    prior = compute_gene_prior(
        [("ORPHA:1", "HGNC:1"), ("ORPHA:2", "HGNC:1")], ["HGNC:1", "HGNC:2"]
    )
    assert prior["HGNC:1"] == 1.0
    assert prior["HGNC:2"] == 0.0


def test_compute_gene_prior_normalizes_by_max_count() -> None:
    prior = compute_gene_prior(
        [
            ("ORPHA:1", "HGNC:1"),
            ("ORPHA:2", "HGNC:1"),
            ("ORPHA:3", "HGNC:2"),
        ],
        ["HGNC:1", "HGNC:2", "HGNC:3"],
    )
    assert prior["HGNC:1"] == 1.0
    assert prior["HGNC:2"] == 0.5
    assert prior["HGNC:3"] == 0.0


def test_compute_gene_prior_handles_empty_positives() -> None:
    prior = compute_gene_prior([], ["HGNC:1", "HGNC:2"])
    assert prior["HGNC:1"] == 0.0
    assert prior["HGNC:2"] == 0.0


def test_baseline_scorer_forward_returns_one_logit_per_pair() -> None:
    torch.manual_seed(0)
    model = BaselineScorer(
        ["ORPHA:1", "ORPHA:2"], ["HGNC:1", "HGNC:2"], {"HGNC:1": 1.0, "HGNC:2": 0.0}
    )
    scores = model(torch.tensor([0, 1]), torch.tensor([1, 0]))
    assert scores.shape == (2,)
    assert torch.isfinite(scores).all()


def test_baseline_scorer_is_deterministic_for_fixed_seed() -> None:
    model_a = BaselineScorer(["ORPHA:1"], ["HGNC:1"], {"HGNC:1": 0.5}, seed=42)
    model_b = BaselineScorer(["ORPHA:1"], ["HGNC:1"], {"HGNC:1": 0.5}, seed=42)
    assert torch.equal(model_a.disease_embedding.weight, model_b.disease_embedding.weight)


def test_baseline_scorer_different_seeds_differ() -> None:
    model_a = BaselineScorer(["ORPHA:1"], ["HGNC:1"], {"HGNC:1": 0.5}, seed=1)
    model_b = BaselineScorer(["ORPHA:1"], ["HGNC:1"], {"HGNC:1": 0.5}, seed=2)
    assert not torch.equal(model_a.disease_embedding.weight, model_b.disease_embedding.weight)


def test_baseline_scorer_does_not_touch_global_rng_state() -> None:
    torch.manual_seed(123)
    before = torch.rand(3)

    torch.manual_seed(123)
    BaselineScorer(["ORPHA:1"], ["HGNC:1"], {"HGNC:1": 0.5}, seed=999)
    after = torch.rand(3)

    assert torch.equal(before, after)


def test_baseline_scorer_gene_prior_logit_contributes_to_unseen_gene() -> None:
    torch.manual_seed(0)
    model = BaselineScorer(
        ["ORPHA:1"], ["HGNC:1", "HGNC:2"], {"HGNC:1": 1.0, "HGNC:2": 0.0}
    )
    # unseen gene (HGNC:2, prior 0.0) should not get an automatic prior boost
    assert model.gene_prior[1].item() == 0.0
    assert model.gene_prior[0].item() == 1.0


def test_baseline_scorer_embedding_dim_default() -> None:
    model = BaselineScorer(["ORPHA:1"], ["HGNC:1"], {"HGNC:1": 0.5})
    assert model.disease_embedding.embedding_dim == 32
    assert model.gene_embedding.embedding_dim == 32
