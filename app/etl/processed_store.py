import json
from pathlib import Path
from typing import Any

from app.etl.models import DiseasePhenotypeAnnotation, GenePhenotypeAnnotation, KnowledgeBase, PhenotypeTerm


PHENOTYPES_FILE = "phenotypes.json"
DISEASE_PHENOTYPES_FILE = "disease_phenotypes.json"
GENE_PHENOTYPES_FILE = "gene_phenotypes.json"


def save_knowledge_base(kb: KnowledgeBase, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        output_dir / PHENOTYPES_FILE,
        [
            {
                "hpo_id": term.hpo_id,
                "name": term.name,
                "definition": term.definition,
                "parents": list(term.parents),
                "synonyms": list(term.synonyms),
            }
            for term in kb.phenotypes.values()
        ],
    )
    _write_json(output_dir / DISEASE_PHENOTYPES_FILE, [annotation.__dict__ for annotation in kb.disease_phenotypes])
    _write_json(output_dir / GENE_PHENOTYPES_FILE, [annotation.__dict__ for annotation in kb.gene_phenotypes])


def load_processed_knowledge_base(processed_dir: Path) -> KnowledgeBase:
    phenotype_rows = _read_json(processed_dir / PHENOTYPES_FILE)
    disease_rows = _read_json(processed_dir / DISEASE_PHENOTYPES_FILE)
    gene_rows = _read_json(processed_dir / GENE_PHENOTYPES_FILE)
    phenotypes = {
        row["hpo_id"]: PhenotypeTerm(
            hpo_id=row["hpo_id"],
            name=row["name"],
            definition=row.get("definition"),
            parents=tuple(row.get("parents", [])),
            synonyms=tuple(row.get("synonyms", [])),
        )
        for row in phenotype_rows
    }
    return KnowledgeBase(
        phenotypes=phenotypes,
        disease_phenotypes=[DiseasePhenotypeAnnotation(**row) for row in disease_rows],
        gene_phenotypes=[GenePhenotypeAnnotation(**row) for row in gene_rows],
    )


def _write_json(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"processed data file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))
