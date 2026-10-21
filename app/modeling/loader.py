"""CSV loading primitives for disease-gene link prediction."""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import torch
from torch_geometric.data import HeteroData

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


@dataclass
class NodeIndex:
    """Ordered id list for one node type, plus id->position index and rankable subset."""

    ids: list[str]
    index: dict[str, int]
    rankable: set[str] = field(default_factory=set)


def build_node_index(nodes: dict[str, NodeRecord]) -> NodeIndex:
    """Build a NodeIndex from a dict of node_id -> NodeRecord (as returned by load_node_csv).

    Preserves the insertion order of `nodes` for `ids`, and collects the subset of ids
    whose record has `rankable is True` into `rankable`.
    """
    ids = list(nodes.keys())
    index = {node_id: position for position, node_id in enumerate(ids)}
    rankable = {node_id for node_id, record in nodes.items() if record.get("rankable") is True}
    return NodeIndex(ids=ids, index=index, rankable=rankable)


def _node_type_for_id(node_id: str, node_indexes: dict[str, NodeIndex]) -> str | None:
    """Find which node type's NodeIndex contains this id."""
    for node_type, node_index in node_indexes.items():
        if node_id in node_index.index:
            return node_type
    return None


def build_hetero_data(
    node_indexes: dict[str, NodeIndex], message_edges: list[dict[str, Any]]
) -> HeteroData:
    """Build a PyG HeteroData graph from node indexes and message edges.

    Adds one edge type per relation in `message_edges`, keyed as
    (source_node_type, relation, target_node_type), plus a mirrored reverse edge type
    (target_node_type, f"rev_{relation}", source_node_type) for every relation, so that
    message-passing GNN layers can propagate information in both directions.
    """
    data = HeteroData()

    for node_type, node_index in node_indexes.items():
        data[node_type].num_nodes = len(node_index.ids)

    # Group edges by (relation, source_node_type, target_node_type)
    grouped: dict[tuple[str, str, str], list[tuple[int, int]]] = {}
    for edge in message_edges:
        relation = edge["relation"]
        source_id = edge["source_id"]
        target_id = edge["target_id"]

        source_type = _node_type_for_id(source_id, node_indexes)
        target_type = _node_type_for_id(target_id, node_indexes)
        if source_type is None or target_type is None:
            raise ValueError(
                f"Could not resolve node type for edge {source_id} -{relation}-> {target_id}"
            )

        source_pos = node_indexes[source_type].index[source_id]
        target_pos = node_indexes[target_type].index[target_id]

        key = (relation, source_type, target_type)
        grouped.setdefault(key, []).append((source_pos, target_pos))

    for (relation, source_type, target_type), pairs in grouped.items():
        source_positions = [pair[0] for pair in pairs]
        target_positions = [pair[1] for pair in pairs]
        edge_index = torch.tensor([source_positions, target_positions], dtype=torch.long)
        reverse_edge_index = torch.tensor(
            [target_positions, source_positions], dtype=torch.long
        )

        data[source_type, relation, target_type].edge_index = edge_index
        data[target_type, f"rev_{relation}", source_type].edge_index = reverse_edge_index

    return data
