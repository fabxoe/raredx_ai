import csv
import re
from pathlib import Path

from app.etl.models import DiseasePhenotypeAnnotation, GenePhenotypeAnnotation, KnowledgeBase, PhenotypeTerm


_DEF_RE = re.compile(r'^"(?P<definition>.*)"(?: \[.*\])?$')
_SYNONYM_RE = re.compile(r'^"(?P<synonym>.*)"\s+(?:EXACT|RELATED|BROAD|NARROW)\s+\[.*\]$')


def load_hpo_obo(path: Path) -> dict[str, PhenotypeTerm]:
    terms: dict[str, PhenotypeTerm] = {}
    current: dict[str, object] | None = None

    with path.open("r", encoding="utf-8") as file:
        for raw_line in file:
            line = raw_line.strip()
            if line == "[Term]":
                _commit_term(current, terms)
                current = {"parents": [], "synonyms": []}
                continue
            if line.startswith("["):
                _commit_term(current, terms)
                current = None
                continue
            if not current or not line:
                continue

            if line.startswith("id: "):
                current["id"] = line.removeprefix("id: ").strip()
            elif line.startswith("name: "):
                current["name"] = line.removeprefix("name: ").strip()
            elif line.startswith("def: "):
                match = _DEF_RE.match(line.removeprefix("def: ").strip())
                current["definition"] = match.group("definition") if match else line.removeprefix("def: ").strip()
            elif line.startswith("is_a: "):
                parent = line.removeprefix("is_a: ").split(" ! ", maxsplit=1)[0].strip()
                current.setdefault("parents", []).append(parent)
            elif line.startswith("synonym: "):
                match = _SYNONYM_RE.match(line.removeprefix("synonym: ").strip())
                if match:
                    current.setdefault("synonyms", []).append(match.group("synonym"))
            elif line == "is_obsolete: true":
                current["obsolete"] = True

    _commit_term(current, terms)
    return terms


def _commit_term(current: dict[str, object] | None, terms: dict[str, PhenotypeTerm]) -> None:
    if not current or current.get("obsolete"):
        return
    hpo_id = current.get("id")
    name = current.get("name")
    if not isinstance(hpo_id, str) or not isinstance(name, str):
        return
    parents = tuple(parent for parent in current.get("parents", []) if isinstance(parent, str))
    synonyms = tuple(synonym for synonym in current.get("synonyms", []) if isinstance(synonym, str))
    definition = current.get("definition")
    terms[hpo_id] = PhenotypeTerm(
        hpo_id=hpo_id,
        name=name,
        definition=definition if isinstance(definition, str) else None,
        parents=parents,
        synonyms=synonyms,
    )


def load_phenotype_hpoa(path: Path, include_negative: bool = False) -> list[DiseasePhenotypeAnnotation]:
    rows: list[DiseasePhenotypeAnnotation] = []
    with path.open("r", encoding="utf-8") as file:
        reader = csv.DictReader((line for line in file if not line.startswith("#")), delimiter="\t")
        for row in reader:
            normalized = {_normalize_key(key): value for key, value in row.items() if key is not None}
            qualifier = _first(normalized, "qualifier")
            if qualifier == "NOT" and not include_negative:
                continue
            disease_id = _first(normalized, "database_id", "databaseid", "database_id", "db_object_id")
            disease_name = _first(normalized, "disease_name", "diseasename", "db_name", "db_object_name")
            hpo_id = _first(normalized, "hpo_id")
            if not disease_id or not disease_name or not hpo_id:
                continue
            rows.append(
                DiseasePhenotypeAnnotation(
                    disease_id=disease_id,
                    disease_name=disease_name,
                    hpo_id=hpo_id,
                    frequency=_none_if_empty(_first(normalized, "frequency")),
                    evidence=_none_if_empty(_first(normalized, "evidence")),
                    source=_none_if_empty(_first(normalized, "reference", "db_reference")),
                )
            )
    return rows


def load_genes_to_phenotype(path: Path) -> list[GenePhenotypeAnnotation]:
    rows: list[GenePhenotypeAnnotation] = []
    with path.open("r", encoding="utf-8") as file:
        reader = csv.DictReader((line for line in file if not line.startswith("#")), delimiter="\t")
        for row in reader:
            normalized = {_normalize_key(key): value for key, value in row.items() if key is not None}
            gene_id = _first(normalized, "ncbi_gene_id", "gene_id", "entrez_gene_id")
            gene_symbol = _first(normalized, "gene_symbol", "entrez_gene_symbol", "gene")
            hpo_id = _first(normalized, "hpo_id", "hpo_term_id")
            if not gene_id or not gene_symbol or not hpo_id:
                continue
            rows.append(
                GenePhenotypeAnnotation(
                    gene_id=gene_id,
                    gene_symbol=gene_symbol,
                    hpo_id=hpo_id,
                    hpo_name=_none_if_empty(_first(normalized, "hpo_name", "hpo_term_name")),
                    disease_id=_none_if_empty(_first(normalized, "disease_id", "disease_id_for_link")),
                    disease_name=_none_if_empty(_first(normalized, "disease_name")),
                    source="genes_to_phenotype",
                )
            )
    return rows


def load_knowledge_base(
    hpo_obo_path: Path,
    phenotype_hpoa_path: Path,
    genes_to_phenotype_path: Path | None = None,
) -> KnowledgeBase:
    return KnowledgeBase(
        phenotypes=load_hpo_obo(hpo_obo_path),
        disease_phenotypes=load_phenotype_hpoa(phenotype_hpoa_path),
        gene_phenotypes=load_genes_to_phenotype(genes_to_phenotype_path) if genes_to_phenotype_path else [],
    )


def _get(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None:
            return value.strip()
    return ""


def _normalize_key(key: str) -> str:
    return key.strip().lower().replace("-", "_").replace(" ", "_")


def _first(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None:
            return value.strip()
    return ""


def _none_if_empty(value: str) -> str | None:
    value = value.strip()
    return None if value in {"", "-"} else value
