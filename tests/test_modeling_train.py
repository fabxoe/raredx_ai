"""Tests for the training loops for the baseline and GNN link predictors."""

from __future__ import annotations

from pathlib import Path

from app.modeling.loader import load_graph_package
from app.modeling.train import train_baseline, train_gnn

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "modeling"


def test_train_baseline_reduces_loss_on_fixture_graph() -> None:
    package = load_graph_package(FIXTURE_DIR, seed=42)
    _, history = train_baseline(package, epochs=20, seed=42)
    assert history.train_loss[-1] < history.train_loss[0]


def test_train_baseline_is_deterministic_for_fixed_seed() -> None:
    package = load_graph_package(FIXTURE_DIR, seed=42)
    _, history_a = train_baseline(package, epochs=5, seed=42)
    _, history_b = train_baseline(package, epochs=5, seed=42)
    assert history_a.train_loss == history_b.train_loss


def test_train_baseline_records_validation_loss_without_backprop() -> None:
    package = load_graph_package(FIXTURE_DIR, seed=42)
    _, history = train_baseline(package, epochs=5, seed=42)
    assert len(history.validation_loss) == 5
    assert len(history.train_loss) == 5


def test_train_gnn_reduces_loss_on_fixture_graph() -> None:
    package = load_graph_package(FIXTURE_DIR, seed=42)
    _, history = train_gnn(package, epochs=20, hidden_dim=8, embedding_dim=8, seed=42)
    assert history.train_loss[-1] < history.train_loss[0]


def test_train_gnn_is_deterministic_for_fixed_seed() -> None:
    package = load_graph_package(FIXTURE_DIR, seed=42)
    _, history_a = train_gnn(package, epochs=5, hidden_dim=8, embedding_dim=8, seed=42)
    _, history_b = train_gnn(package, epochs=5, hidden_dim=8, embedding_dim=8, seed=42)
    assert history_a.train_loss == history_b.train_loss


def test_train_gnn_records_validation_loss_without_backprop() -> None:
    package = load_graph_package(FIXTURE_DIR, seed=42)
    _, history = train_gnn(package, epochs=5, hidden_dim=8, embedding_dim=8, seed=42)
    assert len(history.validation_loss) == 5
    assert len(history.train_loss) == 5
