"""Training loops for the baseline and GNN disease-gene link predictors."""

from __future__ import annotations

from dataclasses import dataclass, field

import torch
from torch import nn

from app.modeling.loader import GraphPackage
from app.modeling.models import BaselineScorer, GNNLinkPredictor, compute_gene_prior


@dataclass
class TrainingHistory:
    """Per-epoch train/validation loss values."""

    train_loss: list[float] = field(default_factory=list)
    validation_loss: list[float] = field(default_factory=list)


def _pairs_to_index_tensors(
    pairs: list[tuple[str, str]],
    disease_index: dict[str, int],
    gene_index: dict[str, int],
) -> tuple[torch.LongTensor, torch.LongTensor]:
    """Convert (disease_id, gene_id) pairs to parallel LongTensors of positions."""
    disease_idx = torch.tensor(
        [disease_index[disease_id] for disease_id, _gene_id in pairs], dtype=torch.long
    )
    gene_idx = torch.tensor(
        [gene_index[gene_id] for _disease_id, gene_id in pairs], dtype=torch.long
    )
    return disease_idx, gene_idx


def _build_pair_batch(
    package: GraphPackage, split: str
) -> tuple[torch.LongTensor, torch.LongTensor, torch.Tensor]:
    """Build combined (disease_idx, gene_idx, labels) tensors for positives+negatives of a split."""
    disease_index = package.node_indexes["Disease"].index
    gene_index = package.node_indexes["Gene"].index

    positives = package.positives[split]
    negatives = package.negatives[split]

    pos_disease_idx, pos_gene_idx = _pairs_to_index_tensors(positives, disease_index, gene_index)
    neg_disease_idx, neg_gene_idx = _pairs_to_index_tensors(negatives, disease_index, gene_index)

    disease_idx = torch.cat([pos_disease_idx, neg_disease_idx])
    gene_idx = torch.cat([pos_gene_idx, neg_gene_idx])
    labels = torch.cat(
        [torch.ones(len(positives)), torch.zeros(len(negatives))]
    )
    return disease_idx, gene_idx, labels


def train_baseline(
    package: GraphPackage,
    *,
    epochs: int = 50,
    lr: float = 0.01,
    seed: int = 42,
) -> tuple[BaselineScorer, TrainingHistory]:
    """Train `BaselineScorer` on `package`'s train split, tracking validation loss too."""
    torch.manual_seed(seed)

    disease_ids = package.node_indexes["Disease"].ids
    gene_ids = package.node_indexes["Gene"].ids
    gene_prior = compute_gene_prior(package.positives["train"], gene_ids)

    model = BaselineScorer(disease_ids, gene_ids, gene_prior, seed=seed)

    train_disease_idx, train_gene_idx, train_labels = _build_pair_batch(package, "train")
    val_disease_idx, val_gene_idx, val_labels = _build_pair_batch(package, "validation")

    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.BCEWithLogitsLoss()

    history = TrainingHistory()

    for _epoch in range(epochs):
        model.train()
        optimizer.zero_grad()
        train_logits = model(train_disease_idx, train_gene_idx)
        train_loss = loss_fn(train_logits, train_labels)
        train_loss.backward()
        optimizer.step()
        history.train_loss.append(train_loss.item())

        model.eval()
        with torch.no_grad():
            val_logits = model(val_disease_idx, val_gene_idx)
            val_loss = loss_fn(val_logits, val_labels)
        history.validation_loss.append(val_loss.item())

    return model, history


def train_gnn(
    package: GraphPackage,
    *,
    epochs: int = 50,
    lr: float = 0.01,
    hidden_dim: int = 64,
    embedding_dim: int = 64,
    seed: int = 42,
) -> tuple[GNNLinkPredictor, TrainingHistory]:
    """Train `GNNLinkPredictor` on `package`'s train split, tracking validation loss too."""
    torch.manual_seed(seed)

    num_nodes = {
        node_type: len(node_index.ids) for node_type, node_index in package.node_indexes.items()
    }
    model = GNNLinkPredictor(
        package.data.metadata(),
        num_nodes=num_nodes,
        hidden_dim=hidden_dim,
        embedding_dim=embedding_dim,
        seed=seed,
    )

    train_disease_idx, train_gene_idx, train_labels = _build_pair_batch(package, "train")
    val_disease_idx, val_gene_idx, val_labels = _build_pair_batch(package, "validation")

    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.BCEWithLogitsLoss()

    history = TrainingHistory()

    for _epoch in range(epochs):
        model.train()
        optimizer.zero_grad()
        embeddings = model.encode(package.data)
        train_logits = model.decode(
            embeddings["Disease"], embeddings["Gene"], train_disease_idx, train_gene_idx
        )
        train_loss = loss_fn(train_logits, train_labels)
        train_loss.backward()
        optimizer.step()
        history.train_loss.append(train_loss.item())

        model.eval()
        with torch.no_grad():
            val_embeddings = model.encode(package.data)
            val_logits = model.decode(
                val_embeddings["Disease"], val_embeddings["Gene"], val_disease_idx, val_gene_idx
            )
            val_loss = loss_fn(val_logits, val_labels)
        history.validation_loss.append(val_loss.item())

    return model, history
