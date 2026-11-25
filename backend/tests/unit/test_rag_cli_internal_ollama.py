import pytest

from wildfire_api.llm.ollama import OllamaHttpClient
from wildfire_api.rag.cli import parse_args


def test_rag_cli_internal_ollama_requires_explicit_flag() -> None:
    args = parse_args(["--embedding-provider", "ollama", "--ollama-url", "http://ollama:11434"])
    assert args.allow_internal_ollama is False
    with pytest.raises(ValueError):
        OllamaHttpClient(args.ollama_url, allow_internal_service=args.allow_internal_ollama)

    approved = parse_args(
        [
            "--embedding-provider", "ollama",
            "--ollama-url", "http://ollama:11434",
            "--allow-internal-ollama",
        ]
    )
    assert approved.allow_internal_ollama is True
    client = OllamaHttpClient(
        approved.ollama_url, allow_internal_service=approved.allow_internal_ollama
    )
    assert client.base_url == "http://ollama:11434"

    disabled = parse_args(["--no-internal-ollama"])
    assert disabled.allow_internal_ollama is False
