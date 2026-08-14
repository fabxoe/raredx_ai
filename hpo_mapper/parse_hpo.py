"""Parse HPO OBO terms into a searchable text table."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


DEFAULT_OBO_PATH = Path("data/raw/hp.obo")
DEFAULT_TERMS_PATH = Path("data/processed/hpo_terms.csv")
CSV_COLUMNS = [
    "hpo_id",
    "hpo_name",
    "matched_text",
    "match_type",
    "definition",
    "is_obsolete",
]

@dataclass
class HPOTerm:
    """Small representation of the OBO fields needed for retrieval."""

    hpo_id: str | None = None
    name: str | None = None
    definition: str = ""
    synonyms: list[str] = field(default_factory=list)
    is_obsolete: bool = False


def _iter_term_blocks(obo_path: Path):
    current: list[str] | None = None
    with obo_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.rstrip("\n")
            if line == "[Term]":
                if current is not None:
                    yield current
                current = []
                continue
            if line.startswith("[") and current is not None:
                yield current
                current = None
                continue
            if current is not None:
                current.append(line)
        if current is not None:
            yield current


def _parse_term_block(lines: list[str]) -> HPOTerm:
    term = HPOTerm()
    for line in lines:
        if not line or line.startswith("!"):
            continue
        if line.startswith("id: "):
            term.hpo_id = line.removeprefix("id: ").strip()
        elif line.startswith("name: "):
            term.name = line.removeprefix("name: ").strip()
        elif line.startswith("def: "):
            term.definition = _extract_quoted_value(line.removeprefix("def: ").strip())
        elif line.startswith("synonym: "):
            synonym = _extract_synonym(line)
            if synonym:
                term.synonyms.append(synonym)
        elif line.startswith("is_obsolete: "):
            term.is_obsolete = line.removeprefix("is_obsolete: ").strip().lower() == "true"
    return term


def _extract_quoted_value(value: str) -> str:
    if not value.startswith('"'):
        return value
    escaped = False
    chars: list[str] = []
    for char in value[1:]:
        if escaped:
            chars.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == '"':
            break
        else:
            chars.append(char)
    return "".join(chars)


def _extract_synonym(line: str) -> str:
    return _extract_quoted_value(line.removeprefix("synonym: ").strip())


def parse_hpo_obo(obo_path: str | Path, include_obsolete: bool = False) -> list[HPOTerm]:
    """Parse non-obsolete HPO terms from an OBO file."""

    obo_path = Path(obo_path)
    if not obo_path.exists():
        raise FileNotFoundError(f"HPO OBO file not found: {obo_path}")

    terms: list[HPOTerm] = []
    for block in _iter_term_blocks(obo_path):
        term = _parse_term_block(block)
        if not term.hpo_id or not term.name:
            continue
        if term.is_obsolete and not include_obsolete:
            continue
        terms.append(term)
    return terms


def terms_to_search_rows(terms: list[HPOTerm]) -> pd.DataFrame:
    """Expand term names and synonyms into separate searchable rows."""

    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    for term in terms:
        candidates = [("name", term.name or "")]
        candidates.extend(("synonym", synonym) for synonym in term.synonyms)
        for match_type, matched_text in candidates:
            matched_text = matched_text.strip()
            if not matched_text:
                continue
            key = (term.hpo_id or "", match_type, matched_text.casefold())
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "hpo_id": term.hpo_id,
                    "hpo_name": term.name,
                    "matched_text": matched_text,
                    "match_type": match_type,
                    "definition": term.definition,
                    "is_obsolete": term.is_obsolete,
                }
            )
    return pd.DataFrame(rows, columns=CSV_COLUMNS)


def build_hpo_terms_csv(
    obo_path: str | Path = DEFAULT_OBO_PATH,
    output_path: str | Path = DEFAULT_TERMS_PATH,
    include_obsolete: bool = False,
) -> pd.DataFrame:
    """Parse HPO OBO and write the expanded retrieval table."""

    terms = parse_hpo_obo(obo_path, include_obsolete=include_obsolete)
    df = terms_to_search_rows(terms)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, quoting=csv.QUOTE_MINIMAL)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse HPO OBO into searchable term rows.")
    parser.add_argument("--obo_path", default=str(DEFAULT_OBO_PATH))
    parser.add_argument("--output_path", default=str(DEFAULT_TERMS_PATH))
    parser.add_argument("--include_obsolete", action="store_true")
    args = parser.parse_args()

    df = build_hpo_terms_csv(
        obo_path=args.obo_path,
        output_path=args.output_path,
        include_obsolete=args.include_obsolete,
    )
    print(f"Wrote {len(df):,} searchable rows to {args.output_path}")


if __name__ == "__main__":
    main()
