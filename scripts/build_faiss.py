import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.embedding.backends import DEFAULT_EMBEDDING_BACKEND, HPO_GRAPH_EMBEDDING_BACKEND, index_dir_name, resolve_embedding_model
from app.embedding.biomedical import BiomedicalEmbedder
from app.embedding.faiss_index import DiseaseEmbeddingIndex
from app.embedding.hpo_graph_index import HPOGraphEmbeddingIndex
from app.etl.processed_store import load_processed_knowledge_base
from app.retrieval.knowledge import KnowledgeIndex


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a FAISS disease embedding index.")
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--backend", default=DEFAULT_EMBEDDING_BACKEND)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    model_name = resolve_embedding_model(args.backend, args.model)
    knowledge = KnowledgeIndex(load_processed_knowledge_base(args.processed_dir))
    if args.backend == HPO_GRAPH_EMBEDDING_BACKEND:
        index = HPOGraphEmbeddingIndex(knowledge)
    else:
        index = DiseaseEmbeddingIndex(knowledge, BiomedicalEmbedder(model_name))
    index_dir = args.processed_dir / "faiss" / index_dir_name(args.backend, model_name)
    index.build(cache_dir=index_dir / "hpo_cache")
    index.save(
        index_dir,
        manifest={
            "backend": args.backend,
            "model": model_name,
            "index": "IndexFlatIP",
            "normalized_vectors": True,
            "similarity": "cosine_via_inner_product",
            "embedding_source": "hpo_ontology_graph" if args.backend == HPO_GRAPH_EMBEDDING_BACKEND else "hpo_text",
        },
    )
    print(f"FAISS index written to {index_dir}")


if __name__ == "__main__":
    main()
