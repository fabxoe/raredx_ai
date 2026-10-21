"""Load the handed-off ablation edge-weight files and attach them to a graph.

`data/processed/graph/ablations/{A,B,C}_train.csv` give three alternative
per-train-pair weights for the `ASSOCIATED_WITH` relation (see
`docs/data/modeling_handoff.md`): A = raw evidence score, B = train-only
IDF-penalized evidence score, C = no `edge_weight` column at all (equivalent to
uniform 1.0 -- i.e. today's default, unweighted behavior). These only reweight
edges that already exist; a node with zero edges stays at zero regardless of
which ablation is used (see the cold-start discussion in
`docs/data/modeling_results_v3.md` and issue #19) -- this module is purely a
message-passing *strength* experiment, not a cold-start mitigation.
"""

from __future__ import annotations

import csv
from pathlib import Path

import torch
from torch_geometric.data import HeteroData

from app.modeling.loader import NodeIndex

DG_EDGE_TYPE: tuple[str, str, str] = ("Disease", "ASSOCIATED_WITH", "Gene")
DG_REVERSE_EDGE_TYPE: tuple[str, str, str] = ("Gene", "rev_ASSOCIATED_WITH", "Disease")
DEFAULT_WEIGHT: float = 1.0


def load_ablation_weights(path: Path) -> dict[tuple[str, str], float]:
    """Read one ablation CSV, returning `{(disease_id, gene_id): edge_weight}`.

    Ablation C has no `edge_weight` column; every pair gets `DEFAULT_WEIGHT`
    (1.0), matching today's unweighted behavior.
    """
    weights: dict[tuple[str, str], float] = {}
    with path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        has_weight_column = reader.fieldnames is not None and "edge_weight" in reader.fieldnames
        for row in reader:
            pair = (row["source_id"], row["target_id"])
            raw = row.get("edge_weight") if has_weight_column else None
            weights[pair] = float(raw) if raw not in (None, "") else DEFAULT_WEIGHT
    return weights


def attach_associated_with_weights(
    data: HeteroData,
    node_indexes: dict[str, NodeIndex],
    weights: dict[tuple[str, str], float],
) -> HeteroData:
    """Return a copy of `data` with an `edge_weight` tensor on the ASSOCIATED_WITH
    and rev_ASSOCIATED_WITH edge types, aligned index-for-index with their
    existing `edge_index`. A pair with no entry in `weights` gets `DEFAULT_WEIGHT`.

    `data` itself is not modified. If `DG_EDGE_TYPE` is absent (e.g. a graph with
    no message-passing ASSOCIATED_WITH edges left), `data` is returned unchanged.
    """
    result = data.clone()
    if DG_EDGE_TYPE not in data.edge_types:
        return result

    disease_ids = node_indexes["Disease"].ids
    gene_ids = node_indexes["Gene"].ids

    forward = data[DG_EDGE_TYPE].edge_index
    forward_weights = torch.tensor(
        [
            weights.get((disease_ids[d], gene_ids[g]), DEFAULT_WEIGHT)
            for d, g in forward.t().tolist()
        ],
        dtype=torch.float32,
    )
    result[DG_EDGE_TYPE].edge_weight = forward_weights

    if DG_REVERSE_EDGE_TYPE in data.edge_types:
        reverse = data[DG_REVERSE_EDGE_TYPE].edge_index
        reverse_weights = torch.tensor(
            [
                weights.get((disease_ids[d], gene_ids[g]), DEFAULT_WEIGHT)
                for g, d in reverse.t().tolist()
            ],
            dtype=torch.float32,
        )
        result[DG_REVERSE_EDGE_TYPE].edge_weight = reverse_weights

    return result
