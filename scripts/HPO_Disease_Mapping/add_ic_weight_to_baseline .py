#!/usr/bin/env python3
"""Add ontology-aware IC weights to an existing disease-HPO baseline CSV."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from functools import lru_cache
import math
from pathlib import Path


DEFAULT_BASELINE = Path("data/processed/HPO_disease_mapping_baseline.csv")
DEFAULT_OBO = Path("data/raw/hp.obo")
DEFAULT_OUTPUT = Path("data/processed/HPO_disease_mapping_baseline_with_ic.csv")

IC_COLUMNS = ["ic_weight", "ic_disease_count", "ic_total_diseases", "ic_frequency"]


def parse_hpo_obo(
    obo_path: Path,
) -> tuple[dict[str, str], dict[str, set[str]], dict[str, set[str]], dict[str, str], set[str]]:
    """Parse HPO names, child-parent edges, parent-child edges, alt IDs, and valid IDs."""
    hpo_name_map: dict[str, str] = {}
    child_to_parents: dict[str, set[str]] = defaultdict(set)
    parent_to_children: dict[str, set[str]] = defaultdict(set)
    alt_id_map: dict[str, str] = {}
    obsolete_ids: set[str] = set()

    current_id: str | None = None
    current_name = ""
    current_alt_ids: list[str] = []
    current_parents: set[str] = set()
    current_obsolete = False

    def flush_term() -> None:
        if not current_id:
            return
        if current_obsolete:
            obsolete_ids.add(current_id)
            return

        hpo_name_map[current_id] = current_name
        child_to_parents[current_id].update(current_parents)
        for parent_id in current_parents:
            parent_to_children[parent_id].add(current_id)
        for alt_id in current_alt_ids:
            alt_id_map[alt_id] = current_id

    with obo_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()

            if line == "[Term]":
                flush_term()
                current_id = None
                current_name = ""
                current_alt_ids = []
                current_parents = set()
                current_obsolete = False
                continue

            if line.startswith("["):
                flush_term()
                current_id = None
                current_name = ""
                current_alt_ids = []
                current_parents = set()
                current_obsolete = False
                continue

            if current_id is None and not line.startswith("id: "):
                continue

            if line.startswith("id: "):
                current_id = line.removeprefix("id: ").strip()
            elif line.startswith("name: "):
                current_name = line.removeprefix("name: ").strip()
            elif line.startswith("alt_id: "):
                current_alt_ids.append(line.removeprefix("alt_id: ").strip())
            elif line.startswith("is_a: "):
                parent_id = line.removeprefix("is_a: ").split("!", 1)[0].strip()
                current_parents.add(parent_id)
            elif line.startswith("is_obsolete: "):
                current_obsolete = line.removeprefix("is_obsolete: ").strip().lower() == "true"

    flush_term()
    valid_hpo_ids = set(hpo_name_map)
    return hpo_name_map, dict(child_to_parents), dict(parent_to_children), alt_id_map, valid_hpo_ids


def read_baseline_csv(baseline_path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with baseline_path.open("r", newline="", encoding="utf-8") as input_file:
        reader = csv.DictReader(input_file)
        if reader.fieldnames is None:
            raise ValueError(f"Input CSV has no header: {baseline_path}")
        rows = [dict(row) for row in reader]
        return rows, list(reader.fieldnames)


def normalize_hpo_ids(
    rows: list[dict[str, str]],
    alt_id_map: dict[str, str],
    valid_hpo_ids: set[str],
) -> tuple[list[dict[str, str]], bool, int]:
    """Normalize hpo_id in-place; preserve hpo_id_original if an alt_id is changed."""
    normalized_rows: list[dict[str, str]] = []
    changed_count = 0
    added_original = False

    for row in rows:
        new_row = dict(row)
        original_hpo_id = new_row.get("hpo_id", "").strip()
        primary_hpo_id = alt_id_map.get(original_hpo_id, original_hpo_id)

        if primary_hpo_id != original_hpo_id:
            new_row["hpo_id_original"] = original_hpo_id
            new_row["hpo_id"] = primary_hpo_id
            changed_count += 1
            added_original = True

        if primary_hpo_id not in valid_hpo_ids:
            new_row["_invalid_hpo_id"] = primary_hpo_id

        normalized_rows.append(new_row)

    return normalized_rows, added_original, changed_count


def build_descendants(parent_to_children: dict[str, set[str]]) -> dict[str, frozenset[str]]:
    """Return descendants_with_self for every term seen as a parent or child."""
    all_terms = set(parent_to_children)
    for children in parent_to_children.values():
        all_terms.update(children)

    @lru_cache(maxsize=None)
    def descendants(term_id: str) -> frozenset[str]:
        result = {term_id}
        for child_id in parent_to_children.get(term_id, set()):
            result.update(descendants(child_id))
        return frozenset(result)

    return {term_id: descendants(term_id) for term_id in all_terms}


def build_ancestors(child_to_parents: dict[str, set[str]]):
    @lru_cache(maxsize=None)
    def ancestors(term_id: str) -> frozenset[str]:
        result = {term_id}
        for parent_id in child_to_parents.get(term_id, set()):
            result.update(ancestors(parent_id))
        return frozenset(result)

    return ancestors


def compute_ic_from_baseline(
    rows: list[dict[str, str]],
    child_to_parents: dict[str, set[str]],
    valid_hpo_ids: set[str],
    hpo_name_map: dict[str, str],
) -> tuple[dict[str, dict[str, object]], int]:
    """Compute IC using unique disease counts propagated to HPO ancestors."""
    disease_to_hpos: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        disease_id = row.get("disease_id", "").strip()
        hpo_id = row.get("hpo_id", "").strip()
        if disease_id and hpo_id in valid_hpo_ids:
            disease_to_hpos[disease_id].add(hpo_id)

    total_diseases = len(disease_to_hpos)
    if total_diseases == 0:
        raise ValueError("No valid disease-HPO annotations found in baseline CSV.")

    ancestors = build_ancestors(child_to_parents)
    term_to_diseases: dict[str, set[str]] = defaultdict(set)

    for disease_id, hpo_ids in disease_to_hpos.items():
        disease_terms: set[str] = set()
        for hpo_id in hpo_ids:
            disease_terms.update(ancestors(hpo_id))
        for term_id in disease_terms:
            term_to_diseases[term_id].add(disease_id)

    ic_by_hpo: dict[str, dict[str, object]] = {}
    for hpo_id, disease_ids in term_to_diseases.items():
        disease_count = len(disease_ids)
        if disease_count == 0:
            continue
        frequency = disease_count / total_diseases
        ic_weight = -math.log(frequency)
        if abs(ic_weight) < 1e-12:
            ic_weight = 0.0
        ic_by_hpo[hpo_id] = {
            "hpo_id": hpo_id,
            "hpo_name": hpo_name_map.get(hpo_id, ""),
            "ic_disease_count": disease_count,
            "ic_total_diseases": total_diseases,
            "ic_frequency": frequency,
            "ic_weight": ic_weight,
        }

    return ic_by_hpo, total_diseases


def merge_ic_to_baseline(
    rows: list[dict[str, str]],
    fieldnames: list[str],
    ic_by_hpo: dict[str, dict[str, object]],
    added_original: bool,
    decimals: int,
) -> tuple[list[dict[str, str]], list[str], int]:
    output_fieldnames = list(fieldnames)
    if added_original and "hpo_id_original" not in output_fieldnames:
        hpo_index = output_fieldnames.index("hpo_id") if "hpo_id" in output_fieldnames else len(output_fieldnames)
        output_fieldnames.insert(hpo_index + 1, "hpo_id_original")
    for column in IC_COLUMNS:
        if column not in output_fieldnames:
            output_fieldnames.append(column)

    output_rows: list[dict[str, str]] = []
    missing_ic_rows = 0

    for row in rows:
        output_row = dict(row)
        output_row.pop("_invalid_hpo_id", None)
        ic_record = ic_by_hpo.get(output_row.get("hpo_id", "").strip())
        if ic_record is None:
            output_row["ic_weight"] = "NaN"
            output_row["ic_disease_count"] = ""
            output_row["ic_total_diseases"] = ""
            output_row["ic_frequency"] = "NaN"
            missing_ic_rows += 1
        else:
            output_row["ic_weight"] = f"{ic_record['ic_weight']:.{decimals}f}"
            output_row["ic_disease_count"] = str(ic_record["ic_disease_count"])
            output_row["ic_total_diseases"] = str(ic_record["ic_total_diseases"])
            output_row["ic_frequency"] = f"{ic_record['ic_frequency']:.{decimals}f}"

        output_rows.append(output_row)

    return output_rows, output_fieldnames, missing_ic_rows


def write_csv(output_path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def print_validation(
    input_rows: list[dict[str, str]],
    output_rows: list[dict[str, str]],
    ic_by_hpo: dict[str, dict[str, object]],
    missing_ic_rows: int,
) -> None:
    unique_diseases = {row.get("disease_id", "").strip() for row in output_rows if row.get("disease_id", "").strip()}
    unique_hpos = {row.get("hpo_id", "").strip() for row in output_rows if row.get("hpo_id", "").strip()}

    print(f"Input rows: {len(input_rows):,}")
    print(f"Output rows: {len(output_rows):,}")
    print(f"Unique diseases: {len(unique_diseases):,}")
    print(f"Unique HPO terms in baseline: {len(unique_hpos):,}")
    print(f"Number of HPO terms with IC: {len(ic_by_hpo):,}")
    print(f"Number of rows with missing IC: {missing_ic_rows:,}")

    ic_records = sorted(ic_by_hpo.values(), key=lambda item: float(item["ic_weight"]))

    print("\nTop 20 highest IC terms:")
    for record in reversed(ic_records[-20:]):
        print(
            f"{record['hpo_id']}\t{record['hpo_name']}\t"
            f"ic={record['ic_weight']:.6f}\tcount={record['ic_disease_count']}"
        )

    print("\nTop 20 lowest IC terms:")
    for record in ic_records[:20]:
        print(
            f"{record['hpo_id']}\t{record['hpo_name']}\t"
            f"ic={record['ic_weight']:.6f}\tcount={record['ic_disease_count']}"
        )

    print("\nExample IC checks:")
    for hpo_id in ["HP:0001250", "HP:0001263", "HP:0000707"]:
        record = ic_by_hpo.get(hpo_id)
        if record is None:
            print(f"{hpo_id}\tIC not available")
            continue
        print(
            f"{record['hpo_id']}\t{record['hpo_name']}\t"
            f"ic={record['ic_weight']:.6f}\t"
            f"frequency={record['ic_frequency']:.6f}\t"
            f"count={record['ic_disease_count']}/{record['ic_total_diseases']}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Add raw HPO IC weights to an existing disease-HPO baseline CSV."
    )
    parser.add_argument("--baseline_path", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--obo_path", type=Path, default=DEFAULT_OBO)
    parser.add_argument("--output_path", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--decimals", type=int, default=6)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.baseline_path.exists():
        raise FileNotFoundError(f"Baseline CSV not found: {args.baseline_path}")
    if not args.obo_path.exists():
        raise FileNotFoundError(f"HPO OBO file not found: {args.obo_path}")

    hpo_name_map, child_to_parents, parent_to_children, alt_id_map, valid_hpo_ids = parse_hpo_obo(
        args.obo_path
    )
    build_descendants(parent_to_children)

    input_rows, input_fieldnames = read_baseline_csv(args.baseline_path)
    if "disease_id" not in input_fieldnames:
        raise ValueError("Baseline CSV must contain a disease_id column.")
    if "hpo_id" not in input_fieldnames:
        raise ValueError("Baseline CSV must contain a hpo_id column.")

    normalized_rows, added_original, changed_count = normalize_hpo_ids(
        input_rows, alt_id_map, valid_hpo_ids
    )
    ic_by_hpo, _ = compute_ic_from_baseline(
        normalized_rows, child_to_parents, valid_hpo_ids, hpo_name_map
    )
    output_rows, output_fieldnames, missing_ic_rows = merge_ic_to_baseline(
        normalized_rows,
        input_fieldnames,
        ic_by_hpo,
        added_original,
        args.decimals,
    )

    assert len(output_rows) == len(input_rows)
    for required_column in IC_COLUMNS:
        assert required_column in output_fieldnames

    write_csv(args.output_path, output_rows, output_fieldnames)

    print(f"Wrote {len(output_rows):,} rows to {args.output_path}")
    print(f"Normalized alt_id HPO rows: {changed_count:,}")
    print_validation(input_rows, output_rows, ic_by_hpo, missing_ic_rows)


if __name__ == "__main__":
    main()
