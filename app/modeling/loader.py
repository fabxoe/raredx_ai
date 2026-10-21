"""CSV loading primitives for disease-gene link prediction."""

from __future__ import annotations

import csv
import random
from pathlib import Path
from typing import Any

NodeRecord = dict[str, Any]


def _parse_rankable(value: str | None) -> bool:
    """Parse rankable column to bool, defaulting to True if missing or empty."""
    if not value or value.strip() == "":
        return True
    return value.strip().lower() == "true"


def load_node_csv(path: Path) -> dict[str, NodeRecord]:
    """Load node CSV, indexed by node_id, include node_type, rankable, canonical_status."""
    result: dict[str, NodeRecord] = {}
    with path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row is None:
                continue
            node_id = row.get("node_id")
            if not node_id:
                continue
            # Parse rankable with default True if column missing or empty
            rankable_str = row.get("rankable")
            rankable = _parse_rankable(rankable_str)
            # Create record with parsed rankable value
            record: NodeRecord = {
                **row,
                "rankable": rankable,
            }
            result[node_id] = record
    return result


def load_message_edge_csv(path: Path) -> list[dict[str, Any]]:
    """Load message edge CSV, return all rows as dict."""
    result: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row is None:
                continue
            result.append(row)
    return result


def load_pair_csv(path: Path) -> list[tuple[str, str]]:
    """Load pair CSV, return (source_id, target_id) for rows where relation == 'ASSOCIATED_WITH'.

    Raises ValueError if any other relation is present.
    """
    result: list[tuple[str, str]] = []
    with path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        relations_seen: set[str] = set()
        for row in reader:
            if row is None:
                continue
            relation = row.get("relation")
            if relation:
                relations_seen.add(relation)
            if relation == "ASSOCIATED_WITH":
                source_id = row.get("source_id")
                target_id = row.get("target_id")
                if source_id and target_id:
                    result.append((source_id, target_id))
        # Check if any non-ASSOCIATED_WITH relations present
        if relations_seen and relations_seen != {"ASSOCIATED_WITH"}:
            raise ValueError(
                f"load_pair_csv expects only ASSOCIATED_WITH relation, found: {relations_seen}"
            )
    return result


def load_negative_pairs_csv(path: Path) -> list[tuple[str, str]]:
    """Load negative pairs CSV, return (source_id, target_id) for rows where label == '0'."""
    result: list[tuple[str, str]] = []
    with path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row is None:
                continue
            label = row.get("label")
            if label == "0":
                source_id = row.get("source_id")
                target_id = row.get("target_id")
                if source_id and target_id:
                    result.append((source_id, target_id))
    return result


def split_negative_pairs(
    negatives: list[tuple[str, str]],
    *,
    split_sizes: dict[str, int],
    seed: int = 42,
) -> dict[str, list[tuple[str, str]]]:
    """Split negative pairs deterministically into train/validation/test groups.

    Args:
        negatives: List of (source_id, target_id) tuples.
        split_sizes: Dictionary with keys "train", "validation", "test" specifying sizes.
        seed: Random seed for reproducibility (default 42).

    Returns:
        Dictionary with keys "train", "validation", "test" containing the split pairs.

    Raises:
        ValueError: If sum of split sizes exceeds number of negatives.
    """
    total_requested = sum(split_sizes.values())
    if total_requested > len(negatives):
        raise ValueError(
            f"split_sizes sum ({total_requested}) exceeds number of negatives ({len(negatives)})"
        )

    # Sort for stable base order, then shuffle with local RNG
    sorted_pairs = sorted(negatives)
    shuffled_pairs = sorted_pairs[:]
    random.Random(seed).shuffle(shuffled_pairs)

    # Slice sequentially in order: train, validation, test
    train_size = split_sizes.get("train", 0)
    val_size = split_sizes.get("validation", 0)

    result = {
        "train": shuffled_pairs[:train_size],
        "validation": shuffled_pairs[train_size : train_size + val_size],
        "test": shuffled_pairs[train_size + val_size : train_size + val_size + split_sizes.get("test", 0)],
    }

    return result
