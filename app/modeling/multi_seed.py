"""Train and evaluate across several model seeds, same graph-package split.

A single seed's Hits@K/MRR can swing well beyond the differences between
hyperparameter choices (see `docs/data/modeling_results_v3.md`'s "Seed 분산
확인" section). This module makes multi-seed mean/std the default way to run
and report results, instead of a one-off diagnostic script.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Callable

from torch import nn

from app.modeling.evaluate import EvaluationReport, RankingMetrics, evaluate_link_prediction
from app.modeling.loader import GraphPackage
from app.modeling.scoring import baseline_score_pair, gnn_score_pair
from app.modeling.train import TrainingHistory, train_baseline, train_gnn

EVALUATION_REPORT_FIELDS: tuple[str, ...] = (
    "gene_corruption",
    "disease_corruption",
    "combined",
    "cold_start_gene_corruption",
    "cold_start_disease_corruption",
    "all_gene_corruption",
    "all_disease_corruption",
    "all_combined",
)


@dataclass
class MetricStats:
    """Mean/std of one metric across seeds, plus the raw per-seed values."""

    mean: float
    std: float
    values: list[float] = field(default_factory=list)


@dataclass
class RankingMetricsStats:
    """Per-metric `MetricStats` mirroring `RankingMetrics`'s fields."""

    hits_at_1: MetricStats
    hits_at_10: MetricStats
    hits_at_50: MetricStats
    mrr: MetricStats
    count: int


@dataclass
class EvaluationReportStats:
    """Per-bucket `RankingMetricsStats` mirroring `EvaluationReport`'s fields."""

    gene_corruption: RankingMetricsStats
    disease_corruption: RankingMetricsStats
    combined: RankingMetricsStats
    cold_start_gene_corruption: RankingMetricsStats
    cold_start_disease_corruption: RankingMetricsStats
    all_gene_corruption: RankingMetricsStats
    all_disease_corruption: RankingMetricsStats
    all_combined: RankingMetricsStats


@dataclass
class MultiSeedRun:
    """Per-seed results and the cross-seed summary, for one model and one split pair."""

    validation_per_seed: dict[int, EvaluationReport]
    test_per_seed: dict[int, EvaluationReport]
    validation_summary: EvaluationReportStats
    test_summary: EvaluationReportStats
    histories: dict[int, TrainingHistory]
    models: dict[int, nn.Module]


def _stats(values: list[float]) -> MetricStats:
    mean = statistics.mean(values)
    std = statistics.stdev(values) if len(values) > 1 else 0.0
    return MetricStats(mean=mean, std=std, values=values)


def aggregate_ranking_metrics(metrics: list[RankingMetrics]) -> RankingMetricsStats:
    """Aggregate the same `RankingMetrics` bucket from several seeds' evaluations.

    `count` (how many pairs fed the bucket) depends only on the fixed graph-package
    split, never on the model seed, so every input must share one `count`; a
    mismatch signals the inputs come from different splits and is rejected.
    """
    if not metrics:
        raise ValueError("aggregate_ranking_metrics requires at least one RankingMetrics")
    counts = {m.count for m in metrics}
    if len(counts) > 1:
        raise ValueError(f"inconsistent counts across seeds (not the same split?): {counts}")
    return RankingMetricsStats(
        hits_at_1=_stats([m.hits_at_1 for m in metrics]),
        hits_at_10=_stats([m.hits_at_10 for m in metrics]),
        hits_at_50=_stats([m.hits_at_50 for m in metrics]),
        mrr=_stats([m.mrr for m in metrics]),
        count=counts.pop(),
    )


def aggregate_evaluation_reports(reports: list[EvaluationReport]) -> EvaluationReportStats:
    """Aggregate several seeds' `EvaluationReport`s (same split) bucket by bucket."""
    if not reports:
        raise ValueError("aggregate_evaluation_reports requires at least one EvaluationReport")
    return EvaluationReportStats(
        **{
            field_name: aggregate_ranking_metrics([getattr(r, field_name) for r in reports])
            for field_name in EVALUATION_REPORT_FIELDS
        }
    )


def _run_seeds(
    package: GraphPackage,
    seeds: list[int],
    train_fn: Callable[[GraphPackage, int], tuple[nn.Module, TrainingHistory]],
    score_pair_fn: Callable[[nn.Module, GraphPackage], Callable],
) -> MultiSeedRun:
    if not seeds:
        raise ValueError("seeds must be a non-empty list")
    validation_per_seed: dict[int, EvaluationReport] = {}
    test_per_seed: dict[int, EvaluationReport] = {}
    histories: dict[int, TrainingHistory] = {}
    models: dict[int, nn.Module] = {}
    for seed in seeds:
        model, history = train_fn(package, seed)
        histories[seed] = history
        models[seed] = model
        scorer = score_pair_fn(model, package)
        validation_per_seed[seed] = evaluate_link_prediction(scorer, package, "validation")
        test_per_seed[seed] = evaluate_link_prediction(scorer, package, "test")
    return MultiSeedRun(
        validation_per_seed=validation_per_seed,
        test_per_seed=test_per_seed,
        validation_summary=aggregate_evaluation_reports(list(validation_per_seed.values())),
        test_summary=aggregate_evaluation_reports(list(test_per_seed.values())),
        histories=histories,
        models=models,
    )


def run_baseline_multi_seed(
    package: GraphPackage,
    seeds: list[int],
    *,
    epochs: int = 400,
    lr: float = 0.01,
    weight_decay: float = 1e-4,
    patience: int | None = 20,
) -> MultiSeedRun:
    """Train+evaluate `BaselineScorer` once per seed in `seeds`, same graph split."""

    def train_fn(pkg: GraphPackage, seed: int) -> tuple[nn.Module, TrainingHistory]:
        return train_baseline(
            pkg, epochs=epochs, lr=lr, weight_decay=weight_decay, seed=seed, patience=patience
        )

    return _run_seeds(package, seeds, train_fn, baseline_score_pair)


def run_gnn_multi_seed(
    package: GraphPackage,
    seeds: list[int],
    *,
    epochs: int = 400,
    lr: float = 0.01,
    weight_decay: float = 1e-4,
    hidden_dim: int = 64,
    embedding_dim: int = 64,
    patience: int | None = 20,
) -> MultiSeedRun:
    """Train+evaluate `GNNLinkPredictor` once per seed in `seeds`, same graph split."""

    def train_fn(pkg: GraphPackage, seed: int) -> tuple[nn.Module, TrainingHistory]:
        return train_gnn(
            pkg,
            epochs=epochs,
            lr=lr,
            weight_decay=weight_decay,
            hidden_dim=hidden_dim,
            embedding_dim=embedding_dim,
            seed=seed,
            patience=patience,
        )

    return _run_seeds(package, seeds, train_fn, gnn_score_pair)
