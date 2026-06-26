from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "raredx_password"
    neo4j_database: str = "neo4j"

    processed_dir: Path = Field(default=Path("data/processed"), alias="RAREDX_PROCESSED_DIR")
    embedding_model: str = Field(
        default="cambridgeltl/SapBERT-from-PubMedBERT-fulltext",
        alias="RAREDX_EMBEDDING_MODEL",
    )
    ic_weight: float = Field(default=0.45, alias="RAREDX_IC_WEIGHT")
    embedding_weight: float = Field(default=0.35, alias="RAREDX_EMBEDDING_WEIGHT")
    graph_weight: float = Field(default=0.20, alias="RAREDX_GRAPH_WEIGHT")
    doc2hpo_url: str | None = Field(default=None, alias="RAREDX_DOC2HPO_URL")
    original_hpo_mapper_url: str | None = Field(default=None, alias="RAREDX_ORIGINAL_HPO_MAPPER_URL")
    doc2hpo_timeout_seconds: float = Field(default=20.0, alias="RAREDX_DOC2HPO_TIMEOUT_SECONDS")
    llm_provider: str = Field(default="off", alias="RAREDX_LLM_PROVIDER")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="RAREDX_OPENAI_MODEL")
    ollama_url: str = Field(default="http://localhost:11434", alias="RAREDX_OLLAMA_URL")
    ollama_chat_model: str = Field(default="phi4-mini", alias="RAREDX_OLLAMA_CHAT_MODEL")


@lru_cache
def get_settings() -> Settings:
    return Settings()
