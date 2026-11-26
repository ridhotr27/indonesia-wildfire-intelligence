from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import (
    AnyHttpUrl,
    Field,
    SecretStr,
    TypeAdapter,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from wildfire_api.llm.ollama import validate_loopback_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None,
        env_prefix="WILDFIRE_",
        extra="ignore",
    )

    app_name: str = "Indonesia Wildfire Intelligence API"
    environment: str = "development"
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"
    max_geojson_features: int = Field(default=500, ge=1, le=5_000)
    max_date_range_days: int = Field(default=366, ge=1, le=3_653)
    cors_origins: str = ""
    max_request_body_bytes: int = Field(default=65_536, ge=1_024, le=1_048_576)
    request_timeout_seconds: float = Field(default=15.0, gt=0, le=120)
    per_client_requests_per_minute: int = Field(default=30, ge=1, le=10_000)
    global_requests_per_minute: int = Field(default=300, ge=1, le=100_000)
    max_concurrent_requests: int = Field(default=20, ge=1, le=1_000)
    client_id_salt: SecretStr = SecretStr("")
    analytics_backend: Literal["mock", "clickhouse"] = "mock"
    clickhouse_url: str = "http://127.0.0.1:8123"
    clickhouse_database: str = "wildfire"
    clickhouse_username: str = "wildfire_reader"
    clickhouse_password: SecretStr = SecretStr("")
    clickhouse_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    agent_planner_backend: Literal["deterministic"] = "deterministic"
    intent_planning_mode: Literal["disabled", "shadow", "guarded"] = "disabled"
    intent_planner_model_name: Literal["qwen2.5:1.5b"] = "qwen2.5:1.5b"
    intent_planner_timeout_seconds: float = Field(default=8.0, gt=0, le=30)
    intent_planner_max_tokens: int = Field(default=512, ge=128, le=1_024)
    assistant_profile: Literal["degraded", "local_grounded", "private_hashing_ollama"] = "degraded"
    agent_model_provider: Literal["disabled", "extractive", "ollama"] = "disabled"
    agent_model_name: str = "qwen2.5:1.5b"
    ollama_internal_service: bool = False
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_timeout_seconds: float = Field(default=60.0, gt=0, le=120)
    agent_max_graph_steps: int = Field(default=6, ge=3, le=12)
    agent_max_tool_calls: int = Field(default=2, ge=1, le=4)
    agent_timeout_seconds: float = Field(default=8.0, gt=0, le=120)
    agent_combined_stage_budgeting: bool = True
    agent_max_retrieved_characters: int = Field(default=6_000, ge=500, le=20_000)
    agent_max_model_tokens: int = Field(default=1_200, ge=128, le=4_096)
    rag_backend: Literal["disabled", "local"] = "disabled"
    qdrant_path: Path = Path("data/qdrant-lir08")
    qdrant_collection: str = Field(default="nasa_firms_documents_v1", min_length=1, max_length=128)
    rag_retrieval_profile: Literal["dense", "dense_guarded", "hybrid_rrf"] = "hybrid_rrf"
    rag_chunking_profile: Literal[
        "recursive-character-1400-200-v1", "structure-title-1400-200-v1"
    ] = "structure-title-1400-200-v1"
    embedding_provider: Literal["hashing", "ollama"] = "hashing"
    embedding_model_name: str = "all-minilm"
    semantic_routing_mode: Literal["disabled", "shadow", "guarded"] = "guarded"
    semantic_intent_path: Path = Path("data/semantic-intents")
    semantic_intent_collection: str = Field(
        default="analytics_intent_examples_v1", min_length=1, max_length=128
    )

    @field_validator("api_prefix")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        if not value.startswith("/") or value.endswith("/"):
            raise ValueError("api_prefix must start with '/' and not end with '/'")
        return value

    @field_validator("ollama_base_url")
    @classmethod
    def validate_ollama_base_url(cls, value: str, info: ValidationInfo) -> str:
        return validate_loopback_url(
            value, allow_internal_service=bool(info.data.get("ollama_internal_service"))
        )

    @model_validator(mode="after")
    def clickhouse_credentials_are_explicit(self) -> "Settings":
        password_is_empty = not self.clickhouse_password.get_secret_value()
        if self.analytics_backend == "clickhouse" and password_is_empty:
            raise ValueError("clickhouse_password is required for the clickhouse analytics backend")
        if (
            self.environment.casefold() == "production"
            and not self.client_id_salt.get_secret_value()
        ):
            raise ValueError("client_id_salt is required in production")
        if self.global_requests_per_minute < self.per_client_requests_per_minute:
            raise ValueError(
                "global_requests_per_minute must be at least per_client_requests_per_minute"
            )
        if self.rag_backend == "local" and str(self.qdrant_path).strip() in {"", "."}:
            raise ValueError("qdrant_path must identify a dedicated directory")
        if self.semantic_routing_mode != "disabled":
            if self.embedding_model_name != "all-minilm":
                raise ValueError("semantic routing requires the approved ollama:all-minilm model")
            if str(self.semantic_intent_path).strip() in {"", "."}:
                raise ValueError("semantic_intent_path must identify a dedicated directory")
            if self.semantic_intent_path.resolve() == self.qdrant_path.resolve():
                raise ValueError("semantic intent and NASA document indexes must be separate")
        if self.assistant_profile == "local_grounded" and (
            self.rag_backend != "local"
            or self.embedding_provider != "ollama"
            or self.embedding_model_name != "all-minilm"
            or self.agent_model_provider != "ollama"
            or self.agent_model_name != "qwen2.5:1.5b"
        ):
            raise ValueError(
                "local_grounded requires local RAG, ollama:all-minilm embeddings, "
                "and ollama:qwen2.5:1.5b generation"
            )
        if self.assistant_profile == "private_hashing_ollama" and (
            self.rag_backend != "local"
            or self.embedding_provider != "hashing"
            or self.agent_model_provider != "ollama"
            or self.agent_model_name != "qwen2.5:0.5b"
            or not self.ollama_internal_service
            or self.ollama_base_url != "http://ollama:11434"
            or self.semantic_routing_mode != "disabled"
            or self.intent_planning_mode != "disabled"
            or self.agent_max_model_tokens > 192
        ):
            raise ValueError(
                "private_hashing_ollama requires hashing RAG, internal qwen2.5:0.5b, "
                "deterministic routing, and at most 192 output tokens"
            )
        return self

    @property
    def parsed_cors_origins(self) -> list[str]:
        origins = [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
        if "*" in origins:
            raise ValueError("wildcard CORS origins are prohibited")
        adapter = TypeAdapter(AnyHttpUrl)
        for origin in origins:
            parsed = adapter.validate_python(origin)
            if parsed.path not in {None, "/"} or parsed.query or parsed.fragment:
                raise ValueError("CORS origins must not include paths, queries, or fragments")
        return origins


@lru_cache
def get_settings() -> Settings:
    # Runtime configuration is loaded here, at the application boundary. Direct
    # Settings(...) construction remains isolated from a developer's .env so unit
    # tests and offline tools cannot silently inherit local service configuration.
    return Settings(_env_file=".env")
