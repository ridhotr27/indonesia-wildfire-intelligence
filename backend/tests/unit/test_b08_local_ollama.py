import json

import pytest

from wildfire_api.agent.runtime import BoundedLangGraphRuntime
from wildfire_api.agent.state import RetrievalToolInput
from wildfire_api.llm.ollama import (
    LocalModelError,
    OllamaAnswerGenerator,
    OllamaHttpClient,
    validate_loopback_url,
)
from wildfire_api.rag.models import RetrievedPassage


def passage(chunk: str = "b" * 64) -> RetrievedPassage:
    return RetrievedPassage(
        chunk_id=chunk,
        document_id="nasa-frp",
        title="NASA FIRMS attributes",
        url="https://www.earthdata.nasa.gov/data/tools/firms",
        section="frp",
        text="FRP is fire radiative power and is reported in megawatts.",
        content_hash="a" * 64,
        retrieved_at="2026-11-06T00:00:00Z",
        untrusted_content=True,
    )


def unrelated_passage(chunk: str = "c" * 64) -> RetrievedPassage:
    return RetrievedPassage(
        chunk_id=chunk,
        document_id="nasa-archive",
        title="NASA archive access",
        url="https://www.earthdata.nasa.gov/data/tools/firms",
        section="archive",
        text="Archive files can be downloaded in several supported formats.",
        content_hash="d" * 64,
        retrieved_at="2026-11-06T00:00:00Z",
        untrusted_content=True,
    )


def generator(payload: dict[str, object]) -> OllamaAnswerGenerator:
    return OllamaAnswerGenerator(
        client=OllamaHttpClient("http://127.0.0.1:11434"),
        model="test-model",
        max_tokens=200,
        transport=lambda path, body: payload,
    )


@pytest.mark.asyncio
async def test_grounded_generation_returns_specific_answer_and_validated_citation() -> None:
    item = passage()

    async def retrieve(_: RetrievalToolInput) -> list[RetrievedPassage]:
        return [item]

    response_payload = {
        "message": {
            "content": json.dumps(
                {
                    "answer": "Fire radiative power (FRP) is reported in megawatts.",
                    "cited_passage_numbers": [1],
                }
            )
        }
    }
    runtime = BoundedLangGraphRuntime(
        analytics_tool=lambda *_: None,  # type: ignore[arg-type]
        retrieval_tool=retrieve,
        answer_generator=generator(response_payload),
    )
    result = await runtime.invoke(
        {"request_id": "r1", "message": "What does FRP mean?", "product_id": "MOCK_ONLY"}
    )
    response = result["response"]
    assert "reported in megawatts" in response.answer
    assert response.citations[0].chunk_id == item.chunk_id
    assert response.usage.llm_calls == 1


@pytest.mark.asyncio
async def test_generator_rejects_invented_citation() -> None:
    item = passage()
    bad = generator(
        {"message": {"content": json.dumps({"answer": "Invented", "cited_passage_numbers": [2]})}}
    )
    with pytest.raises(LocalModelError, match="unknown citation"):
        await bad("What is FRP?", [item])


@pytest.mark.asyncio
async def test_generator_rejects_supplied_but_unrelated_citation() -> None:
    bad = generator(
        {
            "message": {
                "content": json.dumps(
                    {
                        "answer": "Fire radiative power (FRP) is reported in megawatts by NASA.",
                        "cited_passage_numbers": [2],
                    }
                )
            }
        }
    )
    with pytest.raises(LocalModelError, match="unrelated"):
        await bad("What is FRP?", [passage(), unrelated_passage()])


@pytest.mark.asyncio
async def test_empty_retrieval_abstains_without_generation() -> None:
    async def retrieve(_: RetrievalToolInput) -> list[RetrievedPassage]:
        return []

    runtime = BoundedLangGraphRuntime(
        analytics_tool=lambda *_: None,  # type: ignore[arg-type]
        retrieval_tool=retrieve,
        answer_generator=generator({}),
    )
    result = await runtime.invoke(
        {"request_id": "r-empty", "message": "What does FRP mean?", "product_id": "MOCK_ONLY"}
    )

    assert result["response"].citations == []
    assert result["response"].usage.llm_calls == 0
    assert "required evidence is unavailable" in result["response"].answer


@pytest.mark.asyncio
async def test_generator_rejects_incomplete_answer() -> None:
    bad = generator(
        {
            "message": {
                "content": json.dumps(
                    {"answer": "fire radiative power", "cited_passage_numbers": [1]}
                )
            }
        }
    )
    with pytest.raises(LocalModelError, match="incomplete answer"):
        await bad("What is FRP?", [passage()])


@pytest.mark.parametrize(
    "url",
    ["https://example.com", "http://192.168.1.2:11434", "http://user@localhost:11434"],
)
def test_ollama_url_must_be_loopback(url: str) -> None:
    with pytest.raises(ValueError):
        validate_loopback_url(url)


def test_internal_ollama_service_requires_explicit_opt_in() -> None:
    url = "http://ollama:11434"
    with pytest.raises(ValueError):
        OllamaHttpClient(url)
    client = OllamaHttpClient(url, allow_internal_service=True)
    assert client.base_url == url
    for unsafe in ("http://ollama:8080", "http://ollama:11434/path", "http://other:11434"):
        with pytest.raises(ValueError):
            OllamaHttpClient(unsafe, allow_internal_service=True)
