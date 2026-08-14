#!/usr/bin/env python3
"""Add patient HPO graph-based Lin similarity weight columns to a disease-HPO CSV."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from functools import lru_cache
import math
from pathlib import Path


DEFAULT_INPUT = Path("data/processed/HPO_disease_mapping_baseline.csv")
DEFAULT_OBO = Path("data/raw/hp.obo")
DEFAULT_OUTPUT = Path("data/processed/HPO_disease_mapping_with_similarity.csv")
OUTPUT_COLUMN = "hpo_similarity_weight"
BEST_QUERY_COLUMN = "best_matching_query_hpo"


def parse_hpo_graph(obo_path: Path) -> tuple[dict[str, set[str]], dict[str, str]]:
    """Parse HPO term parents and alt_id mappings from hp.obo."""
    parents: dict[str, set[str]] = defaultdict(set)
    alt_to_primary: dict[str, str] = {}

    current_id: str | None = None
    current_alt_ids: list[str] = []
    current_parents: set[str] = set()
    current_obsolete = False

    def flush_term() -> None:
        if not current_id or current_obsolete:
            return
        parents[current_id].update(current_parents)
        for alt_id in current_alt_ids:
            alt_to_primary[alt_id] = current_id

    with obo_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()

            if line == "[Term]":
                flush_term()
                current_id = None
                current_alt_ids = []
                current_parents = set()
                current_obsolete = False
                continue

            if line.startswith("["):
                flush_term()
                current_id = None
                current_alt_ids = []
                current_parents = set()
                current_obsolete = False
                continue

            if current_id is None and not line.startswith("id: "):
                continue

            if line.startswith("id: "):
                current_id = line.removeprefix("id: ").strip()
            elif line.startswith("alt_id: "):
                current_alt_ids.append(line.removeprefix("alt_id: ").strip())
            elif line.startswith("is_a: "):
                parent_id = line.removeprefix("is_a: ").split("!", 1)[0].strip()
                current_parents.add(parent_id)
            elif line.startswith("is_obsolete: "):
                current_obsolete = line.removeprefix("is_obsolete: ").strip().lower() == "true"

    flush_term()
    return dict(parents), alt_to_primary


def canonical_hpo_id(hpo_id: str, alt_to_primary: dict[str, str]) -> str:
    hpo_id = hpo_id.strip()
    return alt_to_primary.get(hpo_id, hpo_id)


def build_ancestor_lookup(parents: dict[str, set[str]]):
    @lru_cache(maxsize=None)
    def ancestors(hpo_id: str) -> frozenset[str]:
        result = {hpo_id}
        for parent_id in parents.get(hpo_id, set()):
            result.update(ancestors(parent_id))
        return frozenset(result)

    return ancestors


def build_information_content(
    csv_path: Path,
    ancestors,
    alt_to_primary: dict[str, str],
) -> tuple[dict[str, float], int]:
    """Compute IC from disease annotations propagated to ancestors."""
    disease_to_hpos: dict[str, set[str]] = defaultdict(set)

    with csv_path.open("r", newline="", encoding="utf-8") as input_file:
        reader = csv.DictReader(input_file)
        for row in reader:
            disease_id = row.get("disease_id", "").strip()
            hpo_id = canonical_hpo_id(row.get("hpo_id", ""), alt_to_primary)
            if disease_id and hpo_id:
                disease_to_hpos[disease_id].add(hpo_id)

    total_diseases = len(disease_to_hpos)
    term_disease_counts: dict[str, int] = defaultdict(int)

    for hpo_ids in disease_to_hpos.values():
        disease_terms: set[str] = set()
        for hpo_id in hpo_ids:
            disease_terms.update(ancestors(hpo_id))
        for term_id in disease_terms:
            term_disease_counts[term_id] += 1

    if total_diseases == 0:
        raise ValueError(f"No disease annotations found in {csv_path}")

    ic: dict[str, float] = {}
    for term_id, disease_count in term_disease_counts.items():
        probability = disease_count / total_diseases
        ic[term_id] = -math.log(probability)

    return ic, total_diseases


def lin_similarity(
    query_hpo_id: str,
    disease_hpo_id: str,
    ancestors,
    ic: dict[str, float],
) -> float:
    query_ancestors = ancestors(query_hpo_id)
    disease_ancestors = ancestors(disease_hpo_id)
    common_ancestors = query_ancestors.intersection(disease_ancestors)

    query_ic = ic.get(query_hpo_id, 0.0)
    disease_ic = ic.get(disease_hpo_id, 0.0)
    denominator = query_ic + disease_ic
    if denominator == 0:
        return 0.0

    mica_ic = max((ic.get(term_id, 0.0) for term_id in common_ancestors), default=0.0)
    similarity = (2 * mica_ic) / denominator
    return min(1.0, max(0.0, similarity))


def add_similarity_column(
    input_csv: Path,
    output_csv: Path,
    obo_path: Path,
    query_hpos: list[str],
    decimals: int,
) -> int:
    parents, alt_to_primary = parse_hpo_graph(obo_path)
    ancestors = build_ancestor_lookup(parents)
    ic, _ = build_information_content(input_csv, ancestors, alt_to_primary)
    query_hpos = [canonical_hpo_id(hpo_id, alt_to_primary) for hpo_id in query_hpos]

    missing_hpos = [hpo_id for hpo_id in query_hpos if hpo_id not in parents]
    if missing_hpos:
        raise ValueError(f"Query HPO ID(s) not found in {obo_path}: {', '.join(missing_hpos)}")

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    row_count = 0

    with input_csv.open("r", newline="", encoding="utf-8") as input_file:
        reader = csv.DictReader(input_file)
        if reader.fieldnames is None:
            raise ValueError(f"Input CSV has no header: {input_csv}")

        fieldnames = list(reader.fieldnames)
        if OUTPUT_COLUMN not in fieldnames:
            fieldnames.append(OUTPUT_COLUMN)
        if BEST_QUERY_COLUMN not in fieldnames:
            fieldnames.append(BEST_QUERY_COLUMN)

        with output_csv.open("w", newline="", encoding="utf-8") as output_file:
            writer = csv.DictWriter(output_file, fieldnames=fieldnames)
            writer.writeheader()

            for row in reader:
                row_hpo = canonical_hpo_id(row.get("hpo_id", ""), alt_to_primary)
                best_query_hpo = ""
                best_similarity = 0.0

                for query_hpo in query_hpos:
                    similarity = lin_similarity(query_hpo, row_hpo, ancestors, ic)
                    if similarity > best_similarity:
                        best_similarity = similarity
                        best_query_hpo = query_hpo

                row[OUTPUT_COLUMN] = f"{best_similarity:.{decimals}f}"
                row[BEST_QUERY_COLUMN] = best_query_hpo
                writer.writerow(row)
                row_count += 1

    return row_count


def parse_query_hpos(values: list[str]) -> list[str]:
    query_hpos: list[str] = []
    seen: set[str] = set()

    for value in values:
        for hpo_id in value.split(","):
            hpo_id = hpo_id.strip()
            if hpo_id and hpo_id not in seen:
                query_hpos.append(hpo_id)
                seen.add(hpo_id)

    if not query_hpos:
        raise ValueError("At least one --query-hpo value is required.")
    return query_hpos


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Add max Lin similarity between patient/query HPO IDs and each row hpo_id."
        )
    )
    parser.add_argument(
        "--query-hpo",
        action="append",
        required=True,
        help=(
            "Patient/query HPO ID(s), e.g. HP:0001250. "
            "Repeat this option or pass comma-separated IDs."
        ),
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--obo", type=Path, default=DEFAULT_OBO)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--decimals", type=int, default=6)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.input.exists():
        raise FileNotFoundError(f"Input CSV not found: {args.input}")
    if not args.obo.exists():
        raise FileNotFoundError(f"HPO OBO file not found: {args.obo}")

    row_count = add_similarity_column(
        input_csv=args.input,
        output_csv=args.output,
        obo_path=args.obo,
        query_hpos=parse_query_hpos(args.query_hpo),
        decimals=args.decimals,
    )
    print(f"Wrote {row_count:,} rows to {args.output}")


if __name__ == "__main__":
    main()
