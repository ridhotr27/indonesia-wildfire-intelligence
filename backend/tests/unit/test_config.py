import pytest
from pydantic import ValidationError

from wildfire_api.core.config import Settings


def test_cors_origins_are_parsed() -> None:
    settings = Settings(cors_origins="https://one.example, https://two.example")

    assert settings.parsed_cors_origins == ["https://one.example", "https://two.example"]


def test_api_prefix_rejects_trailing_slash() -> None:
    with pytest.raises(ValidationError):
        Settings(api_prefix="/api/v1/")


def test_local_grounded_profile_requires_pinned_coherent_dependencies() -> None:
    with pytest.raises(ValidationError, match="local_grounded requires"):
        Settings(assistant_profile="local_grounded")
    settings = Settings(
        assistant_profile="local_grounded",
        rag_backend="local",
        embedding_provider="ollama",
        embedding_model_name="all-minilm",
        agent_model_provider="ollama",
        agent_model_name="qwen2.5:1.5b",
    )
    assert settings.assistant_profile == "local_grounded"


def test_internal_ollama_service_is_opt_in_and_keeps_model_pin() -> None:
    with pytest.raises(ValidationError):
        Settings(ollama_base_url="http://ollama:11434")
    settings = Settings(ollama_internal_service=True, ollama_base_url="http://ollama:11434")
    assert settings.ollama_base_url == "http://ollama:11434"
    with pytest.raises(ValidationError, match="local_grounded requires"):
        Settings(
            ollama_internal_service=True,
            ollama_base_url="http://ollama:11434",
            assistant_profile="local_grounded",
            rag_backend="local",
            embedding_provider="ollama",
            agent_model_provider="ollama",
            agent_model_name="qwen3:0.6b-q4_K_M",
        )


def test_private_hashing_ollama_profile_is_explicit_and_bounded() -> None:
    profile = {
        "assistant_profile": "private_hashing_ollama",
        "rag_backend": "local",
        "embedding_provider": "hashing",
        "agent_model_provider": "ollama",
        "agent_model_name": "qwen2.5:0.5b",
        "ollama_internal_service": True,
        "ollama_base_url": "http://ollama:11434",
        "semantic_routing_mode": "disabled",
        "intent_planning_mode": "disabled",
        "agent_max_model_tokens": 192,
    }
    settings = Settings(**profile)
    assert settings.assistant_profile == "private_hashing_ollama"
    with pytest.raises(ValidationError, match="private_hashing_ollama requires"):
        Settings(**(profile | {"agent_model_name": "qwen2.5:1.5b"}))
