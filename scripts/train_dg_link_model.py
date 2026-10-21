"""CLI: train baseline and GNN disease-gene link predictors, write a JSON report.

Trains `BaselineScorer` and `GNNLinkPredictor` (see `app/modeling/train.py`) on a
graph package (see `app/modeling/loader.py`), evaluates each on the validation and
test splits via `evaluate_link_prediction` (see `app/modeling/evaluate.py`), and
writes a single JSON report with top-level keys `"baseline"` and `"gnn"`, each
holding `{"validation": ..., "test": ...}` serialized `EvaluationReport`s.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path
from typing import Callable

sys.path.append(str(Path(__file__).resolve().parents[1]))

import torch

from app.modeling.evaluate import EvaluationReport, evaluate_link_prediction
from app.modeling.loader import GraphPackage, load_graph_package
from app.modeling.models import BaselineScorer, GNNLinkPredictor
from app.modeling.train import train_baseline, train_gnn

Pair = tuple[str, str]
ScorePairFn = Callable[[list[Pair]], list[float]]


def _baseline_score_pair(model: BaselineScorer, package: GraphPackage) -> ScorePairFn:
    """Adapt `BaselineScorer` to the `score_pair` callable contract."""
    disease_index = package.node_indexes["Disease"].index
    gene_index = package.node_indexes["Gene"].index

    model.eval()

    def score_pair(pairs: list[Pair]) -> list[float]:
        disease_idx = torch.tensor(
            [disease_index[disease_id] for disease_id, _gene_id in pairs], dtype=torch.long
        )
        gene_idx = torch.tensor(
            [gene_index[gene_id] for _disease_id, gene_id in pairs], dtype=torch.long
        )
        with torch.no_grad():
            logits = model(disease_idx, gene_idx)
        return logits.tolist()

    return score_pair


def _gnn_score_pair(model: GNNLinkPredictor, package: GraphPackage) -> ScorePairFn:
    """Adapt `GNNLinkPredictor` to the `score_pair` callable contract.

    Encodes the graph once up front (eval mode, no grad) and caches the resulting
    Disease/Gene embeddings, so repeated `score_pair` calls during evaluation only
    run the cheap bilinear decode, not the full GNN forward pass.
    """
    disease_index = package.node_indexes["Disease"].index
    gene_index = package.node_indexes["Gene"].index

    model.eval()
    with torch.no_grad():
        embeddings = model.encode(package.data)
    disease_emb = embeddings["Disease"]
    gene_emb = embeddings["Gene"]

    def score_pair(pairs: list[Pair]) -> list[float]:
        disease_idx = torch.tensor(
            [disease_index[disease_id] for disease_id, _gene_id in pairs], dtype=torch.long
        )
        gene_idx = torch.tensor(
            [gene_index[gene_id] for _disease_id, gene_id in pairs], dtype=torch.long
        )
        with torch.no_grad():
            logits = model.decode(disease_emb, gene_emb, disease_idx, gene_idx)
        return logits.tolist()

    return score_pair


def _report_to_dict(report: EvaluationReport) -> dict:
    return dataclasses.asdict(report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Train baseline and GNN disease-gene link prediction models and write "
            "a filtered, bidirectional Hits@K/MRR evaluation report."
        )
    )
    parser.add_argument("--graph-dir", type=Path, default=Path("data/processed/graph"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument(
        "--output", type=Path, default=Path("reports/dg_link_prediction_report.json")
    )
    args = parser.parse_args(argv)

    package = load_graph_package(args.graph_dir, seed=args.seed)

    baseline_model, _baseline_history = train_baseline(
        package, epochs=args.epochs, seed=args.seed
    )
    gnn_model, _gnn_history = train_gnn(package, epochs=args.epochs, seed=args.seed)

    baseline_score_pair = _baseline_score_pair(baseline_model, package)
    gnn_score_pair = _gnn_score_pair(gnn_model, package)

    report = {
        "baseline": {
            "validation": _report_to_dict(
                evaluate_link_prediction(baseline_score_pair, package, "validation")
            ),
            "test": _report_to_dict(
                evaluate_link_prediction(baseline_score_pair, package, "test")
            ),
        },
        "gnn": {
            "validation": _report_to_dict(
                evaluate_link_prediction(gnn_score_pair, package, "validation")
            ),
            "test": _report_to_dict(evaluate_link_prediction(gnn_score_pair, package, "test")),
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
