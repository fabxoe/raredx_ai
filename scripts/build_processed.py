import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.etl.hpo_loader import load_knowledge_base
from app.etl.processed_store import save_knowledge_base


def main() -> None:
    parser = argparse.ArgumentParser(description="Build processed RARE_DX_AI knowledge files from raw HPO data.")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed"))
    args = parser.parse_args()

    kb = load_knowledge_base(
        hpo_obo_path=args.raw_dir / "hp.obo",
        phenotype_hpoa_path=args.raw_dir / "phenotype.hpoa",
        genes_to_phenotype_path=args.raw_dir / "genes_to_phenotype.txt",
    )
    save_knowledge_base(kb, args.output_dir)
    print(
        "Processed knowledge base written: "
        f"{len(kb.phenotypes)} phenotypes, "
        f"{len(kb.disease_phenotypes)} disease-phenotype annotations, "
        f"{len(kb.gene_phenotypes)} gene-phenotype annotations"
    )


if __name__ == "__main__":
    main()
