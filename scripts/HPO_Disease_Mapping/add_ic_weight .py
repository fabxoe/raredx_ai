#!/usr/bin/env python3
"""Add an HPO information-content weight column to the disease-HPO baseline CSV."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from functools import lru_cache
import math
from pathlib import Path


DEFAULT_INPUT = Path("data/processed/HPO_disease_mapping_baseline.csv")
DEFAULT_OBO = Path("data/raw/hp.obo")
DEFAULT_OUTPUT = Path("data/processed/HPO_disease_mapping_with_ic_weight.csv")
OUTPUT_COLUMN = "ic_weight"


def parse_hpo_graph(obo_path: Path) -> tuple[dict[str, set[str]], dict[str, str]]:
    """Parse HPO parent relationships and alt_id mappings from hp.obo."""
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
    """Compute IC(t) = -log(P(t)), where P(t) uses diseases with t or descendants."""
    disease_to_hpos: dict[str, set[str]] = defaultdict(set)

    with csv_path.open("r", newline="", encoding="utf-8") as input_file:
        reader = csv.DictReader(input_file)
        for row in reader:
            disease_id = row.get("disease_id", "").strip()
            hpo_id = canonical_hpo_id(row.get("hpo_id", ""), alt_to_primary)
            if disease_id and hpo_id:
                disease_to_hpos[disease_id].add(hpo_id)

    total_diseases = len(disease_to_hpos)
    if total_diseases == 0:
        raise ValueError(f"No disease annotations found in {csv_path}")

    term_disease_counts: dict[str, int] = defaultdict(int)

    for hpo_ids in disease_to_hpos.values():
        disease_terms: set[str] = set()
        for hpo_id in hpo_ids:
            disease_terms.update(ancestors(hpo_id))
        for term_id in disease_terms:
            term_disease_counts[term_id] += 1

    ic: dict[str, float] = {}
    for term_id, disease_count in term_disease_counts.items():
        probability = disease_count / total_diseases
        value = -math.log(probability)
        ic[term_id] = 0.0 if abs(value) < 1e-12 else value

    return ic, total_diseases


def add_ic_weight(input_csv: Path, output_csv: Path, obo_path: Path, decimals: int) -> int:
    parents, alt_to_primary = parse_hpo_graph(obo_path)
    ancestors = build_ancestor_lookup(parents)
    ic, _ = build_information_content(input_csv, ancestors, alt_to_primary)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    row_count = 0

    with input_csv.open("r", newline="", encoding="utf-8") as input_file:
        reader = csv.DictReader(input_file)
        if reader.fieldnames is None:
            raise ValueError(f"Input CSV has no header: {input_csv}")

        fieldnames = list(reader.fieldnames)
        if OUTPUT_COLUMN not in fieldnames:
            fieldnames.append(OUTPUT_COLUMN)

        with output_csv.open("w", newline="", encoding="utf-8") as output_file:
            writer = csv.DictWriter(output_file, fieldnames=fieldnames)
            writer.writeheader()

            for row in reader:
                hpo_id = canonical_hpo_id(row.get("hpo_id", ""), alt_to_primary)
                row[OUTPUT_COLUMN] = f"{ic.get(hpo_id, 0.0):.{decimals}f}"
                writer.writerow(row)
                row_count += 1

    return row_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Add IC(t) = -log(P(t)) weight to Orphanet disease-HPO CSV."
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

    row_count = add_ic_weight(args.input, args.output, args.obo, args.decimals)
    print(f"Wrote {row_count:,} rows to {args.output}")


if __name__ == "__main__":
    main()
