"""Tests for the `train_dg_link_model` CLI entry point."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import torch

from scripts.train_dg_link_model import main

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "modeling"


def test_cli_writes_report_with_expected_keys(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    model_dir = tmp_path / "models"
    exit_code = main(
        [
            "--graph-dir",
            str(FIXTURE_DIR),
            "--seed",
            "42",
            "--model-seeds",
            "1,2",
            "--epochs",
            "3",
            "--output",
            str(output),
            "--model-dir",
            str(model_dir),
        ]
    )
    assert exit_code == 0
    report = json.loads(output.read_text())
    assert set(report) == {"config", "training", "baseline", "gnn"}
    assert report["config"]["model_seeds"] == [1, 2]
    assert report["config"]["split_seed"] == 42

    for model in ("baseline", "gnn"):
        assert set(report["training"][model]) == {"1", "2"}
        for split in ("validation", "test"):
            split_report = report[model][split]
            assert set(split_report) == {"summary", "per_seed"}
            assert set(split_report["per_seed"]) == {"1", "2"}
            combined = split_report["summary"]["combined"]
            assert "mean" in combined["mrr"]
            assert "std" in combined["mrr"]
            assert combined["mrr"]["values"] == [
                split_report["per_seed"]["1"]["combined"]["mrr"],
                split_report["per_seed"]["2"]["combined"]["mrr"],
            ]
            for key in ("all_gene_corruption", "all_disease_corruption", "all_combined"):
                assert key in split_report["summary"]
                assert key in split_report["per_seed"]["1"]
            assert split_report["summary"]["all_gene_corruption"]["count"] == (
                split_report["summary"]["gene_corruption"]["count"]
                + split_report["summary"]["cold_start_gene_corruption"]["count"]
            )


def test_cli_single_model_seed_still_reports_summary_with_zero_std(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    model_dir = tmp_path / "models"
    exit_code = main(
        [
            "--graph-dir",
            str(FIXTURE_DIR),
            "--seed",
            "42",
            "--model-seeds",
            "42",
            "--epochs",
            "2",
            "--output",
            str(output),
            "--model-dir",
            str(model_dir),
        ]
    )
    assert exit_code == 0
    report = json.loads(output.read_text())
    assert report["config"]["model_seeds"] == [42]
    combined = report["gnn"]["validation"]["summary"]["combined"]
    assert combined["mrr"]["std"] == 0.0
    assert len(combined["mrr"]["values"]) == 1


def test_cli_creates_output_directory_if_missing(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "dir" / "report.json"
    model_dir = tmp_path / "models"
    exit_code = main(
        [
            "--graph-dir",
            str(FIXTURE_DIR),
            "--seed",
            "42",
            "--epochs",
            "2",
            "--output",
            str(output),
            "--model-dir",
            str(model_dir),
        ]
    )
    assert exit_code == 0
    assert output.is_file()


def test_cli_saves_one_loadable_checkpoint_per_model_seed(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    model_dir = tmp_path / "models"
    exit_code = main(
        [
            "--graph-dir",
            str(FIXTURE_DIR),
            "--seed",
            "42",
            "--model-seeds",
            "1,2",
            "--epochs",
            "2",
            "--output",
            str(output),
            "--model-dir",
            str(model_dir),
        ]
    )
    assert exit_code == 0
    for model_name in ("baseline", "gnn"):
        for seed in (1, 2):
            checkpoint = model_dir / f"{model_name}_state_dict_seed{seed}.pt"
            assert checkpoint.is_file()
    baseline_state = torch.load(model_dir / "baseline_state_dict_seed1.pt", weights_only=True)
    gnn_state = torch.load(model_dir / "gnn_state_dict_seed1.pt", weights_only=True)
    assert "gene_prior" in baseline_state
    assert any(key.startswith("relation_weight") for key in gnn_state)


def test_cli_patience_stops_training_before_the_full_epoch_budget(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    model_dir = tmp_path / "models"
    exit_code = main(
        [
            "--graph-dir",
            str(FIXTURE_DIR),
            "--seed",
            "42",
            "--epochs",
            "200",
            "--patience",
            "3",
            "--output",
            str(output),
            "--model-dir",
            str(model_dir),
        ]
    )
    assert exit_code == 0
    report = json.loads(output.read_text())
    for model in ("baseline", "gnn"):
        training = report["training"][model]["42"]
        assert training["epochs_run"] < 200
        assert training["epochs_run"] == training["best_epoch"] + 3


def test_cli_patience_zero_disables_early_stopping(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    model_dir = tmp_path / "models"
    exit_code = main(
        [
            "--graph-dir",
            str(FIXTURE_DIR),
            "--seed",
            "42",
            "--epochs",
            "4",
            "--patience",
            "0",
            "--output",
            str(output),
            "--model-dir",
            str(model_dir),
        ]
    )
    assert exit_code == 0
    report = json.loads(output.read_text())
    for model in ("baseline", "gnn"):
        assert report["training"][model]["42"]["epochs_run"] == 4


def test_cli_refuses_to_overwrite_existing_outputs_without_flag(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    model_dir = tmp_path / "models"
    args = [
        "--graph-dir",
        str(FIXTURE_DIR),
        "--seed",
        "42",
        "--epochs",
        "2",
        "--output",
        str(output),
        "--model-dir",
        str(model_dir),
    ]
    assert main(args) == 0

    with pytest.raises(FileExistsError):
        main(args)

    assert main([*args, "--overwrite"]) == 0


def test_cli_rejects_empty_model_seeds() -> None:
    with pytest.raises(ValueError, match="no seeds"):
        main(
            [
                "--graph-dir",
                str(FIXTURE_DIR),
                "--model-seeds",
                " , ",
                "--epochs",
                "2",
            ]
        )
