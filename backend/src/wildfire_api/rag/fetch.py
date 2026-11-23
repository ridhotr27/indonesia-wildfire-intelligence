from __future__ import annotations

import hashlib
import io
import re
from collections.abc import Callable
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import BinaryIO
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from pypdf import PdfReader

from wildfire_api.rag.models import FetchedDocument, SourceSpec

NASA_HOSTS = frozenset(
    {
        "earthdata.nasa.gov",
        "www.earthdata.nasa.gov",
        "firms.modaps.eosdis.nasa.gov",
        "landweb.modaps.eosdis.nasa.gov",
    }
)
DEFAULT_MAX_SOURCE_BYTES = 20 * 1024 * 1024


class DocumentFetchError(RuntimeError):
    pass


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self.ignored_depth += 1
        elif tag in {"p", "br", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self.ignored_depth:
            self.ignored_depth -= 1
        elif tag in {"p", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.ignored_depth:
            self.parts.append(data)

    def text(self) -> str:
        value = " ".join("".join(self.parts).split())
        return re.sub(r"\s*\n\s*", "\n", value).strip()


def validate_nasa_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in NASA_HOSTS:
        raise DocumentFetchError("NASA sources must use HTTPS and an approved NASA host")
    if parsed.username or parsed.password or parsed.port not in {None, 443}:
        raise DocumentFetchError("NASA source URL contains disallowed authority fields")


def extract_text(payload: bytes, media_type: str) -> str:
    if media_type == "application/pdf":
        reader = PdfReader(io.BytesIO(payload))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    elif media_type == "text/html":
        parser = _TextExtractor()
        parser.feed(payload.decode("utf-8", errors="replace"))
        text = parser.text()
    elif media_type == "text/plain":
        text = payload.decode("utf-8", errors="replace")
    else:
        raise DocumentFetchError(f"unsupported media type: {media_type}")
    normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if len(normalized) < 20:
        raise DocumentFetchError("NASA source produced insufficient extractable text")
    return normalized


def _read_bounded(handle: BinaryIO, maximum: int) -> bytes:
    payload = handle.read(maximum + 1)
    if len(payload) > maximum:
        raise DocumentFetchError(f"NASA source exceeds the {maximum}-byte limit")
    if not payload:
        raise DocumentFetchError("NASA source returned an empty response")
    return payload


def fetch_source(
    source: SourceSpec,
    *,
    timeout_seconds: float = 20.0,
    max_source_bytes: int = DEFAULT_MAX_SOURCE_BYTES,
    opener: Callable[..., BinaryIO] = urlopen,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> FetchedDocument:
    source_url = str(source.url)
    validate_nasa_url(source_url)
    request = Request(
        source_url,
        headers={"User-Agent": "IndonesiaWildfireIntelligence/1.0 (+research retrieval)"},
    )
    try:
        response = opener(request, timeout=timeout_seconds)
        final_url = getattr(response, "geturl", lambda: source_url)()
        validate_nasa_url(final_url)
        payload = _read_bounded(response, max_source_bytes)
    except DocumentFetchError:
        raise
    except Exception as exc:
        raise DocumentFetchError(f"failed to fetch {source.document_id}: {exc}") from exc
    return FetchedDocument(
        source=source,
        retrieved_at=now().isoformat(timespec="seconds"),
        final_url=final_url,
        content_hash=hashlib.sha256(payload).hexdigest(),
        source_bytes=len(payload),
        text=extract_text(payload, source.media_type),
    )
