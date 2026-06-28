import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.embedding.backends import (
    BIOSENTVEC_EMBEDDING_BACKEND,
    DEFAULT_EMBEDDING_BACKEND,
    hpo_graph_strategy_for_backend,
    index_dir_name,
    is_hpo_graph_embedding_backend,
    resolve_embedding_model,
)
from app.config import get_settings
from app.embedding.biomedical import BiomedicalEmbedder, BioSentVecEmbedder
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
    if is_hpo_graph_embedding_backend(args.backend):
        index = HPOGraphEmbeddingIndex(knowledge, walk_strategy=hpo_graph_strategy_for_backend(args.backend))
    elif args.backend == BIOSENTVEC_EMBEDDING_BACKEND:
        settings = get_settings()
        index = DiseaseEmbeddingIndex(knowledge, BioSentVecEmbedder(args.model or settings.biosentvec_model_path))
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
            "embedding_source": "hpo_ontology_graph" if is_hpo_graph_embedding_backend(args.backend) else "hpo_text",
            "walk_strategy": hpo_graph_strategy_for_backend(args.backend) if is_hpo_graph_embedding_backend(args.backend) else None,
        },
    )
    print(f"FAISS index written to {index_dir}")


if __name__ == "__main__":
    main()
