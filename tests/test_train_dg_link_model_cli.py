"""Tests for the `train_dg_link_model` CLI entry point."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.train_dg_link_model import main

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "modeling"


def test_cli_writes_report_with_expected_keys(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    exit_code = main(
        [
            "--graph-dir",
            str(FIXTURE_DIR),
            "--seed",
            "42",
            "--epochs",
            "3",
            "--output",
            str(output),
        ]
    )
    assert exit_code == 0
    report = json.loads(output.read_text())
    assert set(report) == {"baseline", "gnn"}
    assert set(report["baseline"]) == {"validation", "test"}
    assert set(report["gnn"]) == {"validation", "test"}
    assert "hits_at_1" in report["baseline"]["test"]["combined"]
    assert "hits_at_1" in report["gnn"]["test"]["combined"]


def test_cli_creates_output_directory_if_missing(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "dir" / "report.json"
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
        ]
    )
    assert exit_code == 0
    assert output.is_file()
