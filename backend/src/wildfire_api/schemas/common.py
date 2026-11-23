from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, HttpUrl, model_validator


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware UTC")
    if value.utcoffset().total_seconds() != 0:
        raise ValueError("timestamp must use UTC")
    return value


UtcDateTime = Annotated[datetime, AfterValidator(_require_utc)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceInfo(StrictModel):
    provider: str
    dataset_version: str
    data_status: Literal["mock", "verified"]
    url: HttpUrl
    attribution: str


class Filters(StrictModel):
    province_codes: list[str]
    date_from: date
    date_to: date

    @model_validator(mode="after")
    def dates_are_ordered(self) -> "Filters":
        if self.date_to < self.date_from:
            raise ValueError("date_to must be on or after date_from")
        return self


class CoverageIssue(StrictModel):
    date_utc: date
    coverage_status: Literal["known_satellite_gap", "unknown"]
    evidence_url: HttpUrl | None = None
    note: str | None = None

    @model_validator(mode="after")
    def known_gap_has_evidence(self) -> "CoverageIssue":
        if self.coverage_status == "known_satellite_gap" and self.evidence_url is None:
            raise ValueError("known satellite gaps require evidence_url")
        return self


class ErrorDetail(StrictModel):
    code: Literal[
        "INVALID_FILTER",
        "VALIDATION_ERROR",
        "RATE_LIMITED",
        "DEPENDENCY_UNAVAILABLE",
        "REQUEST_TIMEOUT",
        "NOT_FOUND",
        "INTERNAL_ERROR",
        "HTTP_ERROR",
    ]
    message: str
    retry_after_seconds: int | None = None


class ErrorResponse(StrictModel):
    request_id: str
    error: ErrorDetail


class Citation(StrictModel):
    title: str
    url: HttpUrl
    chunk_id: str


class Usage(StrictModel):
    llm_calls: int = Field(ge=0)
