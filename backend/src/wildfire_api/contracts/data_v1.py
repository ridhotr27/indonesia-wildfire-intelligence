"""Backend consumer models for the D04 DE-to-BE contract candidate.

These models validate the synthetic handoff fixture. They do not connect the API to
ClickHouse and do not imply approval of D04, A01, or G2.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)

SUPPORTED_CONTRACT_MAJOR = 1
PRODUCT_ID = "VNP14IMG.002_SNPP_FIRMS_SP"
BOUNDARY_SOURCE_ID = "osm-idn-adm1-2026-10-10b"
MAP_DEFAULT_LIMIT = 500
MAP_HARD_LIMIT = 5_000
READ_ONLY_VIEWS = frozenset(
    {
        "analytics_hotspot_observations_v1",
        "analytics_daily_coverage_v1",
        "analytics_provinces_v1",
        "analytics_ingestion_batches_v1",
    }
)

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
ProvinceCode = Annotated[str, Field(pattern=r"^[0-9]{2}$")]


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("contract timestamp must be timezone-aware UTC")
    if value.utcoffset().total_seconds() != 0:
        raise ValueError("contract timestamp must use UTC")
    return value


UtcDateTime = Annotated[datetime, AfterValidator(_require_utc)]


class UnsupportedContractVersion(ValueError):
    """Raised when a producer uses a contract major this backend does not support."""


class ContractModel(BaseModel):
    # Additive optional fields in a future compatible minor release must be ignored.
    model_config = ConfigDict(extra="ignore")

    contract_version: str

    @field_validator("contract_version")
    @classmethod
    def supports_contract_major(cls, value: str) -> str:
        match = re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", value)
        if match is None or int(match.group(1)) != SUPPORTED_CONTRACT_MAJOR:
            raise UnsupportedContractVersion(f"unsupported data contract version: {value}")
        return value


class ObservationContract(ContractModel):
    observation_id: Sha256
    product_id: Literal["VNP14IMG.002_SNPP_FIRMS_SP"]
    source_product: Literal["VNP14IMG"]
    collection_version: Literal["2"]
    processing_stream: Literal["standard"]
    satellite_code: Literal["N"]
    satellite_name: Literal["Suomi NPP"]
    instrument: Literal["VIIRS"]
    acquired_at_utc: UtcDateTime
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    brightness_i4_kelvin: float
    brightness_i5_kelvin: float
    scan_km: float = Field(gt=0)
    track_km: float = Field(gt=0)
    frp_mw: float = Field(ge=0)
    confidence_code: Literal["l", "n", "h"]
    confidence_label: Literal["low", "nominal", "high"]
    daynight_code: Literal["D", "N"]
    hotspot_type_code: int = Field(ge=0, le=3)
    province_code: ProvinceCode | None
    province_name: str | None
    geo_assignment_status: Literal["assigned", "unassigned", "multiple_match"]
    geo_assignment_method: Literal["osm_snapshot_point_intersection", "none"]
    boundary_source_id: str | None
    ingestion_batch_id: str
    source_row_number: int = Field(ge=1)
    source_record_hash: Sha256
    quality_flags: list[
        Literal[
            "zero_frp",
            "source_exact_duplicate",
            "geo_unassigned",
            "geo_multiple_match",
            "known_coverage_gap_context",
            "source_category_unexpected",
        ]
    ]

    @model_validator(mode="after")
    def geography_is_consistent(self) -> ObservationContract:
        geographic_values = (self.province_code, self.province_name, self.boundary_source_id)
        if self.geo_assignment_status == "assigned":
            if any(value is None for value in geographic_values):
                raise ValueError("assigned geography requires province and boundary fields")
            if self.geo_assignment_method != "osm_snapshot_point_intersection":
                raise ValueError("assigned geography requires point intersection")
            if self.boundary_source_id != BOUNDARY_SOURCE_ID:
                raise ValueError("assigned geography uses an unsupported boundary")
        elif any(value is not None for value in geographic_values):
            raise ValueError("non-assigned geography must retain null fields")
        elif self.geo_assignment_method != "none":
            raise ValueError("non-assigned geography must use method none")
        return self


class DailyCoverageContract(ContractModel):
    product_id: Literal["VNP14IMG.002_SNPP_FIRMS_SP"]
    date_utc: date
    coverage_status: Literal[
        "observations_present", "known_satellite_gap", "zero_detections_verified", "unknown"
    ]
    observation_count: int | None = Field(default=None, ge=0)
    evidence_url: HttpUrl | None
    note: str | None
    ingestion_batch_id: str | None

    @model_validator(mode="after")
    def count_matches_coverage(self) -> DailyCoverageContract:
        if self.coverage_status == "observations_present" and (
            self.observation_count is None or self.observation_count <= 0
        ):
            raise ValueError("observations_present requires a positive count")
        if self.coverage_status in {"known_satellite_gap", "unknown"}:
            if self.observation_count is not None:
                raise ValueError("unavailable coverage cannot have a numeric count")
        if self.coverage_status == "known_satellite_gap" and self.evidence_url is None:
            raise ValueError("known gaps require evidence")
        if self.coverage_status == "zero_detections_verified" and (
            self.observation_count != 0 or self.evidence_url is None
        ):
            raise ValueError("verified zero requires count zero and evidence")
        return self


class ProvinceContract(ContractModel):
    province_code: ProvinceCode
    province_name: str
    source_code: Annotated[str, Field(pattern=r"^ID_[A-Z]{2}$")]
    source_name: str
    boundary_source_id: Literal["osm-idn-adm1-2026-10-10b"]
    snapshot: Literal["2026-10-10b"]
    commit: Literal["c4d208a03a71553a1082f960ebdaa88c1d8e9389"]
    crs: Literal["OGC:CRS84"]
    source_sha256: Sha256
    canonical_sha256: Sha256
    license: Literal["ODbL-1.0"]
    license_url: HttpUrl
    required_attribution: Literal["© OpenStreetMap contributors"]
    is_supported: Literal[True]


class IngestionBatchContract(ContractModel):
    ingestion_batch_id: str
    product_id: Literal["VNP14IMG.002_SNPP_FIRMS_SP"]
    source_url: HttpUrl
    source_artifact_sha256: Sha256
    source_bytes: int = Field(ge=0)
    retrieved_at_utc: UtcDateTime
    provider_last_modified_utc: UtcDateTime | None
    coverage_start_utc: UtcDateTime
    coverage_end_utc: UtcDateTime
    source_row_count: int = Field(ge=0)
    canonical_row_count: int = Field(ge=0)
    duplicate_excess_rows: int = Field(ge=0)
    rejected_row_count: int = Field(ge=0)
    transform_version: str
    provenance_manifest_path: str
    publication_status: Literal["published"]
    published_at_utc: UtcDateTime


class CoverageIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date_utc: date
    coverage_status: Literal["known_satellite_gap", "unknown"]


class ReferenceQueryContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_id: str
    date_from: date
    date_to: date
    province_codes: list[ProvinceCode]
    available_detection_total: int | None = Field(default=None, ge=0)
    numeric_total_available: bool
    is_complete: bool
    coverage_issues: list[CoverageIssue]

    @model_validator(mode="after")
    def unavailable_total_is_null(self) -> ReferenceQueryContract:
        if not self.numeric_total_available and self.available_detection_total is not None:
            raise ValueError("an unavailable numeric total must be null")
        if self.coverage_issues and self.is_complete:
            raise ValueError("a result with coverage issues cannot be complete")
        return self


class DataContractFixture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixture_classification: Literal["synthetic_contract_example"]
    contract_version: Literal["1.0.0", "1.1.0"]
    observations: list[ObservationContract]
    daily_coverage: list[DailyCoverageContract]
    provinces: list[ProvinceContract]
    ingestion_batches: list[IngestionBatchContract]
    reference_queries: list[ReferenceQueryContract]


def bounded_map_rows(
    rows: list[ObservationContract], requested_limit: int = MAP_DEFAULT_LIMIT
) -> tuple[list[ObservationContract], bool]:
    """Apply the candidate's deterministic ordering and hard truncation boundary."""

    effective_limit = min(max(requested_limit, 1), MAP_HARD_LIMIT)
    ordered = sorted(rows, key=lambda row: (row.acquired_at_utc, row.observation_id))
    fetched = ordered[: effective_limit + 1]
    return fetched[:effective_limit], len(fetched) > effective_limit
