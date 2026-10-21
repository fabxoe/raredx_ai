"""CLI: train baseline and GNN disease-gene link predictors, write a JSON report.

Trains `BaselineScorer` and `GNNLinkPredictor` (see `app/modeling/train.py`) on a
graph package (see `app/modeling/loader.py`) once per seed in `--model-seeds`
(same fixed graph split throughout), evaluates each run on the validation and
test splits via `app/modeling/multi_seed.py`, and writes a JSON report with
top-level keys `"config"`, `"training"`, `"baseline"`, `"gnn"` -- the latter two
each holding `{"validation": {...}, "test": {...}}` with a `"summary"` (mean/std
across seeds) and a `"per_seed"` breakdown.

A single seed's Hits@K/MRR can swing well beyond the differences between
hyperparameter choices (see `docs/data/modeling_results_v3.md`), so this script
always reports multi-seed statistics -- `--model-seeds 42` (the default) just
makes that a one-seed summary with std 0.0, not a different code path.

Also saves each (model, seed) pair's `state_dict` under `--model-dir` so any run
can be shared and reloaded without retraining. Refuses to overwrite an existing
checkpoint or report file unless `--overwrite` is passed.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import torch

from app.modeling.evaluate import EvaluationReport
from app.modeling.loader import load_graph_package
from app.modeling.multi_seed import (
    EvaluationReportStats,
    MultiSeedRun,
    run_baseline_multi_seed,
    run_gnn_multi_seed,
)
from app.modeling.train import TrainingHistory


def _parse_seeds(raw: str) -> list[int]:
    seeds = [int(piece.strip()) for piece in raw.split(",") if piece.strip()]
    if not seeds:
        raise ValueError(f"--model-seeds produced no seeds from {raw!r}")
    return seeds


def _report_to_dict(report: EvaluationReport) -> dict:
    return dataclasses.asdict(report)


def _stats_to_dict(stats: EvaluationReportStats) -> dict:
    return dataclasses.asdict(stats)


def _run_to_dict(run: MultiSeedRun) -> dict[str, dict]:
    return {
        "validation": {
            "summary": _stats_to_dict(run.validation_summary),
            "per_seed": {
                str(seed): _report_to_dict(report)
                for seed, report in run.validation_per_seed.items()
            },
        },
        "test": {
            "summary": _stats_to_dict(run.test_summary),
            "per_seed": {
                str(seed): _report_to_dict(report) for seed, report in run.test_per_seed.items()
            },
        },
    }


def _training_to_dict(histories: dict[int, TrainingHistory]) -> dict[str, dict]:
    return {
        str(seed): {
            "epochs_run": len(history.train_loss),
            "best_epoch": history.best_epoch,
            "best_validation_loss": min(history.validation_loss),
        }
        for seed, history in histories.items()
    }


def _check_no_clobber(paths: list[Path], *, overwrite: bool) -> None:
    if overwrite:
        return
    existing = [str(path) for path in paths if path.exists()]
    if existing:
        raise FileExistsError(
            "refusing to overwrite existing output file(s) without --overwrite: "
            + ", ".join(existing)
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Train baseline and GNN disease-gene link prediction models across one "
            "or more model seeds and write a filtered, bidirectional Hits@K/MRR "
            "evaluation report with per-seed and mean/std summary statistics."
        )
    )
    parser.add_argument("--graph-dir", type=Path, default=Path("data/processed/graph"))
    parser.add_argument(
        "--seed", type=int, default=42, help="seed for the graph package's train/val/test split"
    )
    parser.add_argument(
        "--model-seeds",
        type=str,
        default="42",
        help=(
            "comma-separated model seeds to train+evaluate, e.g. '1,2,3,4,5'; the graph "
            "split (--seed) stays fixed across all of them. Report always includes "
            "per-seed results plus a mean/std summary, even for a single seed."
        ),
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=400,
        help="epoch budget; with --patience set (the default), training usually stops earlier",
    )
    parser.add_argument(
        "--patience",
        type=int,
        default=20,
        help=(
            "stop training after this many epochs with no new best validation loss, and "
            "restore the best epoch's weights; pass 0 to disable early stopping and always "
            "train for the full --epochs, returning the final epoch's weights"
        ),
    )
    parser.add_argument(
        "--weight-decay",
        type=float,
        default=1e-4,
        help="Adam L2 penalty for both models; pass 0 to disable",
    )
    parser.add_argument(
        "--output", type=Path, default=Path("reports/dg_link_prediction_report.json")
    )
    parser.add_argument("--model-dir", type=Path, default=Path("reports/models"))
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="allow overwriting an existing report or checkpoint at the output paths",
    )
    args = parser.parse_args(argv)
    patience = None if args.patience <= 0 else args.patience
    model_seeds = _parse_seeds(args.model_seeds)

    checkpoint_paths = [
        args.model_dir / f"{model_name}_state_dict_seed{seed}.pt"
        for model_name in ("baseline", "gnn")
        for seed in model_seeds
    ]
    _check_no_clobber([args.output, *checkpoint_paths], overwrite=args.overwrite)

    package = load_graph_package(args.graph_dir, seed=args.seed)

    baseline_run = run_baseline_multi_seed(
        package,
        model_seeds,
        epochs=args.epochs,
        weight_decay=args.weight_decay,
        patience=patience,
    )
    gnn_run = run_gnn_multi_seed(
        package,
        model_seeds,
        epochs=args.epochs,
        weight_decay=args.weight_decay,
        patience=patience,
    )

    report = {
        "config": {
            "graph_dir": str(args.graph_dir),
            "split_seed": args.seed,
            "model_seeds": model_seeds,
            "epochs": args.epochs,
            "patience": patience,
            "weight_decay": args.weight_decay,
        },
        "training": {
            "baseline": _training_to_dict(baseline_run.histories),
            "gnn": _training_to_dict(gnn_run.histories),
        },
        "baseline": _run_to_dict(baseline_run),
        "gnn": _run_to_dict(gnn_run),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    args.model_dir.mkdir(parents=True, exist_ok=True)
    for model_name, run in (("baseline", baseline_run), ("gnn", gnn_run)):
        for seed, model in run.models.items():
            checkpoint = args.model_dir / f"{model_name}_state_dict_seed{seed}.pt"
            torch.save(model.state_dict(), checkpoint)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
