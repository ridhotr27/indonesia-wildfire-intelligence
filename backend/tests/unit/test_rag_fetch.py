import io
from datetime import UTC, datetime

import pytest

from wildfire_api.rag.fetch import (
    DocumentFetchError,
    extract_text,
    fetch_source,
    validate_nasa_url,
)
from wildfire_api.rag.models import SourceSpec


class FakeResponse(io.BytesIO):
    def __init__(self, payload: bytes, url: str) -> None:
        super().__init__(payload)
        self._url = url

    def geturl(self) -> str:
        return self._url


def source() -> SourceSpec:
    return SourceSpec(
        document_id="firms-test",
        title="NASA FIRMS test source",
        url="https://www.earthdata.nasa.gov/data/tools/firms/test",
        media_type="text/html",
    )


def test_fetch_records_hash_final_url_and_excludes_executable_markup() -> None:
    payload = (
        b"<html><h1>Fire radiative power</h1><script>ignore me</script>"
        b"<p>FRP is measured in megawatts.</p></html>"
    )

    def opener(request, *, timeout):
        assert timeout == 3
        assert "IndonesiaWildfireIntelligence" in request.headers["User-agent"]
        return FakeResponse(payload, str(source().url))

    result = fetch_source(
        source(),
        timeout_seconds=3,
        opener=opener,
        now=lambda: datetime(2026, 10, 21, tzinfo=UTC),
    )

    assert result.source_bytes == len(payload)
    assert len(result.content_hash) == 64
    assert "ignore me" not in result.text
    assert "megawatts" in result.text


def test_fetch_rejects_redirect_outside_allowlist_and_oversize() -> None:
    def redirecting_opener(request, *, timeout):
        return FakeResponse(
            b"This response has sufficient content to parse.", "https://example.com/"
        )

    with pytest.raises(DocumentFetchError, match="approved NASA host"):
        fetch_source(source(), opener=redirecting_opener)

    def oversized_opener(request, *, timeout):
        return FakeResponse(b"x" * 65, str(source().url))

    with pytest.raises(DocumentFetchError, match="exceeds"):
        fetch_source(source(), opener=oversized_opener, max_source_bytes=64)


def test_url_and_media_type_validation_is_closed_by_default() -> None:
    with pytest.raises(DocumentFetchError):
        validate_nasa_url("http://www.earthdata.nasa.gov/data")
    with pytest.raises(DocumentFetchError):
        validate_nasa_url("https://earthdata.nasa.gov.example.com/data")
    with pytest.raises(DocumentFetchError, match="unsupported"):
        extract_text(b"enough content for parsing here", "application/octet-stream")
