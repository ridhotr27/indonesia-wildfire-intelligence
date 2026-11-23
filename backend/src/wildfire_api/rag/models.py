from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class SourceSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,63}$")
    title: str = Field(min_length=3, max_length=200)
    url: HttpUrl
    media_type: str = Field(pattern=r"^(text/html|application/pdf|text/plain)$")
    published_at: str | None = None
    version: str | None = None


class FetchedDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: SourceSpec
    retrieved_at: str
    final_url: HttpUrl
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_bytes: int = Field(gt=0)
    text: str = Field(min_length=20)


class RetrievedPassage(BaseModel):
    model_config = ConfigDict(frozen=True)

    chunk_id: str
    document_id: str
    title: str
    url: HttpUrl
    section: str
    text: str
    content_hash: str
    retrieved_at: str
    version: str | None = None
    published_at: str | None = None
    untrusted_content: bool = True
