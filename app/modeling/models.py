"""No-graph baseline model: gene prior + bilinear disease/gene scorer."""

from __future__ import annotations

import torch
from torch import nn


def compute_gene_prior(
    train_positives: list[tuple[str, str]], gene_ids: list[str]
) -> dict[str, float]:
    """Compute normalized train-positive frequency per gene id.

    Each gene's train-positive count is divided by the maximum count across
    all genes, so the most-associated gene gets a prior of 1.0. Genes with no
    train-positive occurrences (including genes unseen in `train_positives`)
    default to 0.0.
    """
    counts: dict[str, int] = {gene_id: 0 for gene_id in gene_ids}
    for _disease_id, gene_id in train_positives:
        if gene_id in counts:
            counts[gene_id] += 1

    max_count = max(counts.values(), default=0)
    if max_count == 0:
        return {gene_id: 0.0 for gene_id in gene_ids}

    return {gene_id: counts[gene_id] / max_count for gene_id in gene_ids}


class BaselineScorer(nn.Module):
    """No-graph baseline: gene prior logit plus a learned bilinear term.

    Combines a fixed, precomputed gene prior (how often a gene appears as a
    positive label in the train split) with a learned bilinear scorer over
    small disease/gene embeddings:

        logit = gene_prior_logit[gene] + disease_emb @ W @ gene_emb
    """

    def __init__(
        self,
        disease_ids: list[str],
        gene_ids: list[str],
        gene_prior: dict[str, float],
        *,
        embedding_dim: int = 32,
        seed: int = 42,
    ) -> None:
        super().__init__()

        self.disease_ids = list(disease_ids)
        self.gene_ids = list(gene_ids)
        self.embedding_dim = embedding_dim

        num_diseases = len(self.disease_ids)
        num_genes = len(self.gene_ids)

        # Build weight tensors uninitialized (torch.empty draws no RNG), then
        # fill them using a local generator so construction never touches
        # global torch RNG state. Passing `_weight` to nn.Embedding skips its
        # own (global-RNG-based) reset_parameters call.
        generator = torch.Generator().manual_seed(seed)

        disease_weight = torch.empty(num_diseases, embedding_dim)
        nn.init.normal_(disease_weight, generator=generator)
        self.disease_embedding = nn.Embedding(
            num_diseases, embedding_dim, _weight=disease_weight
        )

        gene_weight = torch.empty(num_genes, embedding_dim)
        nn.init.normal_(gene_weight, generator=generator)
        self.gene_embedding = nn.Embedding(
            num_genes, embedding_dim, _weight=gene_weight
        )

        bilinear_weight = torch.empty(embedding_dim, embedding_dim)
        nn.init.xavier_uniform_(bilinear_weight, generator=generator)
        self.bilinear_weight = nn.Parameter(bilinear_weight)

        gene_prior_values = torch.tensor(
            [gene_prior.get(gene_id, 0.0) for gene_id in self.gene_ids],
            dtype=torch.float32,
        )
        self.register_buffer("gene_prior", gene_prior_values)

    def forward(
        self, disease_idx: torch.LongTensor, gene_idx: torch.LongTensor
    ) -> torch.Tensor:
        """Return a 1-D logit tensor, one per (disease, gene) input pair."""
        disease_emb = self.disease_embedding(disease_idx)
        gene_emb = self.gene_embedding(gene_idx)

        bilinear_term = torch.einsum(
            "bi,ij,bj->b", disease_emb, self.bilinear_weight, gene_emb
        )
        gene_prior_logit = self.gene_prior[gene_idx]

        return gene_prior_logit + bilinear_term
