"""Filtered, bidirectional Hits@K / MRR evaluation for disease-gene link prediction.

This module is model-agnostic: it consumes a plain scoring callable
``score_pair(pairs) -> scores`` over ``(disease_id, gene_id)`` string pairs.
Adapting ``BaselineScorer`` / ``GNNLinkPredictor`` to that signature is the
caller's job.

Protocol (see docs/superpowers/specs/2026-10-21-dg-link-prediction-modeling-design.md):

* **Filtered ranking.** For each positive pair of the evaluated split, one side is
  corrupted while the other is held fixed. The candidate pool for the corrupted
  side is ``package.node_indexes[<type>].rankable`` (never ``.ids``), minus every
  id that forms a known positive pair with the fixed side in *any* split
  (train, validation, test). The true id is always kept in the pool exactly once,
  even if it is itself non-rankable.
* **Tie policy: mean rank.** The true pair's rank is
  ``1 + #(candidates scored strictly higher) + #(other candidates tied) / 2``,
  i.e. the average of the optimistic and pessimistic ranks. It is deterministic
  and neither rewards nor punishes a degenerate constant scorer.
  ``hits_at_k = mean(rank <= k)`` and ``mrr = mean(1 / rank)``.
* **Cold-start separation.** For gene corruption, a pair is cold-start if its gene
  has zero edges in the message-passing graph ``package.data`` (any edge type,
  either endpoint position, so forward and ``rev_*`` types are both covered).
  Symmetrically, for disease corruption the pair's disease is checked. Cold-start
  pairs go to the ``cold_start_*`` buckets only and are never averaged into
  ``gene_corruption`` / ``disease_corruption`` / ``combined``.
* **Empty buckets** report ``count=0`` and all metrics ``0.0``; consumers should
  treat metrics of a zero-count bucket as undefined.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from app.modeling.loader import GraphPackage

Pair = tuple[str, str]
ScorePairFn = Callable[[list[Pair]], list[float]]

DISEASE_TYPE = "Disease"
GENE_TYPE = "Gene"
HITS_KS: tuple[int, ...] = (1, 10, 50)
CANDIDATE_SUBSET_HITS_KS: tuple[int, ...] = (1, 3, 10)
DEFAULT_CANDIDATE_POOL_SIZE = 10


@dataclass
class RankingMetrics:
    """Hits@K and MRR over ``count`` ranked positive pairs."""

    hits_at_1: float
    hits_at_10: float
    hits_at_50: float
    mrr: float
    count: int


@dataclass
class CandidateSubsetMetrics:
    """Gene-side ranking metrics within a small, disease-specific candidate pool.

    Models the downstream service shape (symptoms -> disease candidates -> a
    small set of candidate genes for that disease -> ranked, top-3 shown)
    instead of ranking against the full rankable gene universe. See
    ``evaluate_candidate_subset_ranking``.
    """

    hits_at_1: float
    hits_at_3: float
    hits_at_10: float
    mrr: float
    count: int
    mean_known_candidates: float


@dataclass
class EvaluationReport:
    """Per-direction, combined, cold-start, and full-set ranking metrics for one split.

    ``gene_corruption`` / ``disease_corruption`` / ``combined`` exclude cold-start
    pairs; ``cold_start_*`` hold only cold-start pairs; ``all_*`` hold every pair.
    """

    gene_corruption: RankingMetrics
    disease_corruption: RankingMetrics
    combined: RankingMetrics
    cold_start_gene_corruption: RankingMetrics
    cold_start_disease_corruption: RankingMetrics
    all_gene_corruption: RankingMetrics
    all_disease_corruption: RankingMetrics
    all_combined: RankingMetrics


def _metrics_from_ranks(ranks: list[float]) -> RankingMetrics:
    """Aggregate 1-indexed (possibly fractional) ranks into ``RankingMetrics``."""
    count = len(ranks)
    if count == 0:
        return RankingMetrics(hits_at_1=0.0, hits_at_10=0.0, hits_at_50=0.0, mrr=0.0, count=0)
    hits = {k: sum(1 for rank in ranks if rank <= k) / count for k in HITS_KS}
    mrr = sum(1.0 / rank for rank in ranks) / count
    return RankingMetrics(
        hits_at_1=hits[1], hits_at_10=hits[10], hits_at_50=hits[50], mrr=mrr, count=count
    )


def _mean_rank_of_first(scores: list[float]) -> float:
    """Rank of ``scores[0]`` (the true pair) under descending order, mean-rank tie policy."""
    true_score = scores[0]
    higher = 0
    tied = 0
    for score in scores[1:]:
        if score > true_score:
            higher += 1
        elif score == true_score:
            tied += 1
    return 1.0 + higher + tied / 2.0


def _nodes_with_edges(package: GraphPackage) -> dict[str, set[int]]:
    """Positions of nodes, per node type, that touch at least one message-passing edge."""
    connected: dict[str, set[int]] = defaultdict(set)
    for edge_type in package.data.edge_types:
        source_type, _relation, target_type = edge_type
        edge_index = package.data[edge_type].edge_index
        connected[source_type].update(edge_index[0].tolist())
        connected[target_type].update(edge_index[1].tolist())
    return connected


def _is_cold_start(
    node_type: str, node_id: str, package: GraphPackage, connected: dict[str, set[int]]
) -> bool:
    position = package.node_indexes[node_type].index.get(node_id)
    return position is None or position not in connected.get(node_type, set())


def _score_rank(
    score_pair: ScorePairFn, pairs: list[Pair], direction: str, true_pair: Pair
) -> float:
    """Score ``pairs`` (true pair first) in one batch and return the true pair's rank.

    Raises:
        ValueError: if ``score_pair`` returns the wrong number of scores, or if any
            score (the true pair's or a candidate's) is non-finite (NaN/inf). A
            non-finite score would otherwise silently collapse to rank 1 via Python's
            comparison semantics (``x > nan`` and ``x == nan`` are both ``False``),
            masking a diverged model as a perfect one.
    """
    scores = [float(score) for score in score_pair(pairs)]
    if len(scores) != len(pairs):
        raise ValueError(
            f"score_pair returned {len(scores)} scores for {len(pairs)} pairs"
        )
    non_finite_count = sum(1 for score in scores if not math.isfinite(score))
    if non_finite_count:
        disease_id, gene_id = true_pair
        raise ValueError(
            f"score_pair returned {non_finite_count} non-finite score(s) "
            f"(NaN/inf) while evaluating {direction} for true pair "
            f"(disease={disease_id!r}, gene={gene_id!r}); cannot compute a "
            "meaningful rank from non-finite scores"
        )
    return _mean_rank_of_first(scores)


def _ordered_pool(rankable: Iterable[str], excluded: set[str], true_id: str) -> list[str]:
    """Deterministically ordered filtered candidates, excluding the true id itself."""
    return sorted(node_id for node_id in rankable if node_id not in excluded and node_id != true_id)


def evaluate_link_prediction(
    score_pair: ScorePairFn, package: GraphPackage, split: str
) -> EvaluationReport:
    """Compute filtered bidirectional Hits@1/10/50 and MRR for ``package.positives[split]``.

    ``score_pair`` receives ``(disease_id, gene_id)`` pairs and must return one score
    per pair, higher meaning more likely a true association. It is called once per
    (positive pair, corruption direction) with the true pair first in the batch.

    Raises:
        KeyError: if ``split`` is not a key of ``package.positives``.
        ValueError: if ``score_pair`` returns the wrong number of scores, or returns
            any non-finite (NaN/inf) score.
    """
    eval_pairs = package.positives[split]

    # Known positives across ALL splits, indexed by the fixed side.
    genes_by_disease: dict[str, set[str]] = defaultdict(set)
    diseases_by_gene: dict[str, set[str]] = defaultdict(set)
    for split_pairs in package.positives.values():
        for disease_id, gene_id in split_pairs:
            genes_by_disease[disease_id].add(gene_id)
            diseases_by_gene[gene_id].add(disease_id)

    rankable_genes = package.node_indexes[GENE_TYPE].rankable
    rankable_diseases = package.node_indexes[DISEASE_TYPE].rankable
    connected = _nodes_with_edges(package)

    gene_ranks: list[float] = []
    disease_ranks: list[float] = []
    cold_gene_ranks: list[float] = []
    cold_disease_ranks: list[float] = []

    for disease_id, gene_id in eval_pairs:
        true_pair = (disease_id, gene_id)

        # Gene corruption: hold disease fixed, rank the true gene.
        gene_pool = _ordered_pool(rankable_genes, genes_by_disease[disease_id], gene_id)
        gene_rank = _score_rank(
            score_pair,
            [true_pair] + [(disease_id, candidate) for candidate in gene_pool],
            "gene_corruption",
            true_pair,
        )
        if _is_cold_start(GENE_TYPE, gene_id, package, connected):
            cold_gene_ranks.append(gene_rank)
        else:
            gene_ranks.append(gene_rank)

        # Disease corruption: hold gene fixed, rank the true disease.
        disease_pool = _ordered_pool(rankable_diseases, diseases_by_gene[gene_id], disease_id)
        disease_rank = _score_rank(
            score_pair,
            [true_pair] + [(candidate, gene_id) for candidate in disease_pool],
            "disease_corruption",
            true_pair,
        )
        if _is_cold_start(DISEASE_TYPE, disease_id, package, connected):
            cold_disease_ranks.append(disease_rank)
        else:
            disease_ranks.append(disease_rank)

    # Every aggregate below is reduced from the same raw per-pair rank lists; the
    # "all_*" views merge the main and cold-start buckets without re-scoring.
    all_gene_ranks = gene_ranks + cold_gene_ranks
    all_disease_ranks = disease_ranks + cold_disease_ranks
    return EvaluationReport(
        gene_corruption=_metrics_from_ranks(gene_ranks),
        disease_corruption=_metrics_from_ranks(disease_ranks),
        combined=_metrics_from_ranks(gene_ranks + disease_ranks),
        cold_start_gene_corruption=_metrics_from_ranks(cold_gene_ranks),
        cold_start_disease_corruption=_metrics_from_ranks(cold_disease_ranks),
        all_gene_corruption=_metrics_from_ranks(all_gene_ranks),
        all_disease_corruption=_metrics_from_ranks(all_disease_ranks),
        all_combined=_metrics_from_ranks(all_gene_ranks + all_disease_ranks),
    )


def _candidate_subset_metrics_from_ranks(
    ranks: list[float], known_counts: list[int]
) -> CandidateSubsetMetrics:
    count = len(ranks)
    if count == 0:
        return CandidateSubsetMetrics(
            hits_at_1=0.0, hits_at_3=0.0, hits_at_10=0.0, mrr=0.0, count=0,
            mean_known_candidates=0.0,
        )
    hits = {k: sum(1 for rank in ranks if rank <= k) / count for k in CANDIDATE_SUBSET_HITS_KS}
    mrr = sum(1.0 / rank for rank in ranks) / count
    return CandidateSubsetMetrics(
        hits_at_1=hits[1],
        hits_at_3=hits[3],
        hits_at_10=hits[10],
        mrr=mrr,
        count=count,
        mean_known_candidates=sum(known_counts) / count,
    )


def evaluate_candidate_subset_ranking(
    score_pair: ScorePairFn,
    package: GraphPackage,
    split: str,
    *,
    pool_size: int = DEFAULT_CANDIDATE_POOL_SIZE,
    seed: int = 42,
) -> CandidateSubsetMetrics:
    """Rank the true gene within a small, disease-specific candidate pool.

    For each positive pair of ``split``, builds a pool of up to ``pool_size``
    genes (the true gene plus up to ``pool_size - 1`` others) instead of the
    full rankable gene universe used by ``evaluate_link_prediction``:

    1. Other genes already known (any split) to be associated with the same
       disease -- real alternative candidates for a multi-gene disease.
    2. If that is not enough to fill the pool, padded with a deterministic
       random sample of other rankable genes (seeded by ``seed``).

    Only the disease -> gene direction is evaluated: this models a service
    that, for one already-identified disease candidate, ranks a handful of
    candidate genes and shows the top few -- not full-universe link
    discovery. ``mean_known_candidates`` reports the average number of
    real (non-padded) alternative candidates per pair, since that mix
    directly affects how meaningful the pool is.

    Raises:
        KeyError: if ``split`` is not a key of ``package.positives``.
        ValueError: if ``pool_size`` is less than 1, or if ``score_pair``
            returns the wrong number of scores or any non-finite score.
    """
    if pool_size < 1:
        raise ValueError(f"pool_size must be >= 1, got {pool_size}")

    eval_pairs = package.positives[split]

    genes_by_disease: dict[str, set[str]] = defaultdict(set)
    for split_pairs in package.positives.values():
        for disease_id, gene_id in split_pairs:
            genes_by_disease[disease_id].add(gene_id)

    rankable_genes = sorted(package.node_indexes[GENE_TYPE].rankable)
    rng = random.Random(seed)

    ranks: list[float] = []
    known_counts: list[int] = []

    for disease_id, gene_id in eval_pairs:
        true_pair = (disease_id, gene_id)
        disease_genes = genes_by_disease[disease_id]

        known = sorted(disease_genes - {gene_id})
        pool = known[: pool_size - 1]
        needed = (pool_size - 1) - len(pool)
        if needed > 0:
            exclude = disease_genes | {gene_id}
            fill_universe = [g for g in rankable_genes if g not in exclude]
            pool += rng.sample(fill_universe, min(needed, len(fill_universe)))

        rank = _score_rank(
            score_pair,
            [true_pair] + [(disease_id, candidate) for candidate in pool],
            "gene_corruption_subset",
            true_pair,
        )
        ranks.append(rank)
        known_counts.append(len(known))

    return _candidate_subset_metrics_from_ranks(ranks, known_counts)
