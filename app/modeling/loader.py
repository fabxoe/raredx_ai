"""CSV loading primitives for disease-gene link prediction."""

from __future__ import annotations

import csv
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
