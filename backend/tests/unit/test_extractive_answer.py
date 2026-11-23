import pytest

from wildfire_api.rag.extractive import ExtractiveAnswerGenerator
from wildfire_api.rag.models import RetrievedPassage


@pytest.mark.asyncio
async def test_extractive_answer_uses_only_retrieved_evidence_and_chunk_ids() -> None:
    passage = RetrievedPassage(
        chunk_id="b" * 64,
        document_id="firms-confidence",
        title="NASA FIRMS attributes",
        url="https://www.earthdata.nasa.gov/data/tools/firms",
        section="confidence",
        text=(
            "For VIIRS, confidence values are low, nominal, and high. "
            "The values help users gauge the quality of individual hotspot pixels."
        ),
        content_hash="a" * 64,
        retrieved_at="2026-11-22T00:00:00Z",
        untrusted_content=True,
    )

    generated = await ExtractiveAnswerGenerator()(
        "How should VIIRS confidence be interpreted?", [passage]
    )

    assert generated.cited_chunk_ids == [passage.chunk_id]
    assert "low, nominal, and high" in generated.answer
    assert all(sentence in passage.text for sentence in generated.answer.split(". "))
