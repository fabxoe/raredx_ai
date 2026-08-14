#!/usr/bin/env python3
"""Extract Orphanet disease-HPO associations from XML to CSV."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
import xml.etree.ElementTree as ET


DEFAULT_INPUT = Path("Orphanet/Clinical_signs_and_symptoms_in_rare_disease.xml")
DEFAULT_OUTPUT = Path("data/orphanet_clinical_signs_hpo.csv")

CSV_COLUMNS = [
    "disease_id",
    "disease_name",
    "hpo_id",
    "hpo_name",
    "frequency_label",
]


def child_text(element: ET.Element, path: str) -> str:
    child = element.find(path)
    if child is None or child.text is None:
        return ""
    return child.text.strip()


def iter_rows(xml_path: Path):
    """Yield one CSV row per HPODisorderAssociation."""
    for event, element in ET.iterparse(xml_path, events=("end",)):
        if element.tag != "Disorder":
            continue

        disease_id = child_text(element, "OrphaCode")
        disease_name = child_text(element, "Name")

        for association in element.findall("./HPODisorderAssociationList/HPODisorderAssociation"):
            yield {
                "disease_id": disease_id,
                "disease_name": disease_name,
                "hpo_id": child_text(association, "./HPO/HPOId"),
                "hpo_name": child_text(association, "./HPO/HPOTerm"),
                "frequency_label": child_text(association, "./HPOFrequency/Name"),
            }

        element.clear()


def write_csv(xml_path: Path, csv_path: Path) -> int:
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    row_count = 0
    with csv_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=CSV_COLUMNS)
        writer.writeheader()

        for row in iter_rows(xml_path):
            writer.writerow(row)
            row_count += 1

    return row_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert Orphanet clinical signs XML into a disease-HPO CSV."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Input XML path. Default: {DEFAULT_INPUT}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output CSV path. Default: {DEFAULT_OUTPUT}",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"Input XML not found: {args.input}")

    row_count = write_csv(args.input, args.output)
    print(f"Wrote {row_count:,} rows to {args.output}")


if __name__ == "__main__":
    main()
