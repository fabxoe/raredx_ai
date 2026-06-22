import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.embedding.biomedical import BiomedicalEmbedder
from app.embedding.faiss_index import DiseaseEmbeddingIndex
from app.etl.processed_store import load_processed_knowledge_base
from app.retrieval.knowledge import KnowledgeIndex


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a FAISS disease embedding index.")
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--model", default="cambridgeltl/SapBERT-from-PubMedBERT-fulltext")
    args = parser.parse_args()

    knowledge = KnowledgeIndex(load_processed_knowledge_base(args.processed_dir))
    index = DiseaseEmbeddingIndex(knowledge, BiomedicalEmbedder(args.model))
    index.build()
    index.save(args.processed_dir / "faiss")
    print(f"FAISS index written to {args.processed_dir / 'faiss'}")


if __name__ == "__main__":
    main()
