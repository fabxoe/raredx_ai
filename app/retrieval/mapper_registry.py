from app.config import Settings
from app.schemas.hpo_mapper import HPOMapperCapability, HPOMapperOption
from app.schemas.retrieval import HPOMapperMode


def mapper_capabilities(settings: Settings) -> list[HPOMapperCapability]:
    return [
        HPOMapperCapability(
            id="dictionary",
            label="Dictionary",
            description="HPO name/synonym phrase matcher. No external service required.",
            configured=True,
            options=_negation_options(settings),
        ),
        HPOMapperCapability(
            id="doc2hpo",
            label="Lightweight",
            description="RARE_DX_AI-compatible Doc2HPO endpoint for embedding-based HPO mapping.",
            configured=bool(settings.doc2hpo_url),
            options=[
                *_negation_options(settings),
                HPOMapperOption(key="threshold", label="Threshold", type="number", default=0.70),
                HPOMapperOption(key="candidate_limit", label="Candidates", type="number", default=30),
            ],
        ),
        HPOMapperCapability(
            id="original_hpo_mapper",
            label="Original",
            description="Adapter for the original UoS-HGIG/HPO-Mapper service.",
            configured=bool(settings.original_hpo_mapper_url),
            options=[
                *_negation_options(settings),
                HPOMapperOption(
                    key="protocol",
                    label="Protocol",
                    type="select",
                    default="p1",
                    choices=["p1", "p2_qc", "p3_llm_selection"],
                ),
                HPOMapperOption(key="use_llm", label="Use LLM", type="boolean", default=False),
                *_extraction_llm_options(settings),
                HPOMapperOption(key="top_k", label="Top K", type="number", default=10),
                HPOMapperOption(key="threshold", label="Threshold", type="number", default=0.76),
                HPOMapperOption(key="embed_model", label="Embed model", type="text", default="nomic-embed-text"),
                HPOMapperOption(
                    key="max_genes",
                    label="Gene preview",
                    type="select",
                    default="50",
                    choices=["50", "100", "1000", "all"],
                ),
            ],
        ),
        HPOMapperCapability(
            id="dictionary_doc2hpo",
            label="Dictionary + Lightweight",
            description="Merge dictionary and lightweight Doc2HPO-compatible mapper results.",
            configured=bool(settings.doc2hpo_url),
            options=_negation_options(settings),
        ),
        HPOMapperCapability(
            id="off",
            label="Off",
            description="Disable note-to-HPO mapping. Use direct HPO term input instead.",
            configured=True,
        ),
    ]


def _negation_option() -> HPOMapperOption:
    return HPOMapperOption(
        key="negation_mode",
        label="Negation",
        type="select",
        default="off",
        choices=[
            "off",
            "simple_trigger",
            "negex_lite",
            "medspacy_context",
            "status_weight",
            "llm_qc",
        ],
    )


def _negation_options(settings: Settings) -> list[HPOMapperOption]:
    return [
        _negation_option(),
        HPOMapperOption(
            key="negation_llm_provider",
            label="Negation LLM",
            type="select",
            default="off",
            choices=["off", "openai", "ollama"],
        ),
        HPOMapperOption(
            key="negation_chat_model",
            label="Negation model",
            type="select",
            default=settings.openai_model,
            choices=[settings.openai_model],
        ),
    ]


def _extraction_llm_options(settings: Settings) -> list[HPOMapperOption]:
    return [
        HPOMapperOption(
            key="llm_provider",
            label="Extraction LLM",
            type="select",
            default=settings.llm_provider,
            choices=["off", "openai", "ollama"],
        ),
        HPOMapperOption(
            key="chat_model",
            label="Extraction model",
            type="select",
            default=settings.openai_model,
            choices=[settings.openai_model],
        ),
    ]


def mapper_label(settings: Settings, mapper_id: HPOMapperMode) -> str:
    for capability in mapper_capabilities(settings):
        if capability.id == mapper_id:
            return capability.label
    return mapper_id
