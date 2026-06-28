from app.config import Settings
from app.schemas.ranking import RankingMethodCapability, RankingOption
from app.schemas.retrieval import RankingMethod


def ranking_method_capabilities(settings: Settings) -> list[RankingMethodCapability]:
    embedding_backend = _embedding_backend_label(settings.embedding_model)
    return [
        RankingMethodCapability(
            id="ic",
            label="IC",
            description="Weighted HPO overlap using information content.",
            configured=True,
            options=[
                RankingOption(key="ic_mode", label="IC mode", type="select", default="direct", choices=["direct"]),
                RankingOption(key="use_ancestor_terms", label="Use ancestors", type="boolean", default=False),
            ],
        ),
        RankingMethodCapability(
            id="embedding",
            label="Embedding",
            description="Disease profile vector retrieval using the selected disease embedding backend.",
            configured=True,
            options=[
                RankingOption(
                    key="embedding_backend",
                    label="Disease embedding backend",
                    type="select",
                    default="sapbert_faiss",
                    choices=["sapbert_faiss"],
                ),
                RankingOption(key="embedding_model", label="Model", type="text", default=embedding_backend),
            ],
        ),
        RankingMethodCapability(
            id="graph",
            label="Graph",
            description="Knowledge graph evidence ranking from explicit disease-phenotype overlap.",
            configured=True,
            options=[
                RankingOption(
                    key="graph_evidence_mode",
                    label="Graph evidence",
                    type="select",
                    default="local_overlap",
                    choices=["local_overlap", "frequency_weighted_graph", "gene_path", "source_confidence_graph"],
                ),
            ],
        ),
        RankingMethodCapability(
            id="hybrid",
            label="Hybrid",
            description="Linear re-ranking over IC, disease embedding, and graph evidence scores.",
            configured=True,
            options=[
                RankingOption(
                    key="embedding_backend",
                    label="Disease embedding backend",
                    type="select",
                    default="sapbert_faiss",
                    choices=["sapbert_faiss"],
                ),
                RankingOption(key="ic_weight", label="IC weight", type="number", default=settings.ic_weight),
                RankingOption(key="embedding_weight", label="Embedding weight", type="number", default=settings.embedding_weight),
                RankingOption(key="graph_weight", label="Graph weight", type="number", default=settings.graph_weight),
                RankingOption(
                    key="graph_evidence_mode",
                    label="Graph evidence",
                    type="select",
                    default="local_overlap",
                    choices=["local_overlap", "frequency_weighted_graph", "gene_path", "source_confidence_graph"],
                ),
            ],
        ),
    ]


def ranking_method_label(settings: Settings, method: RankingMethod) -> str:
    for capability in ranking_method_capabilities(settings):
        if capability.id == method:
            return capability.label
    return method


def _embedding_backend_label(model: str) -> str:
    if model == "cambridgeltl/SapBERT-from-PubMedBERT-fulltext":
        return "SapBERT PubMedBERT"
    return model
