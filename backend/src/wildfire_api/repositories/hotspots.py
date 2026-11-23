from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, Protocol


@dataclass(frozen=True, slots=True)
class ProductRecord:
    product_id: str
    display_name: str


@dataclass(frozen=True, slots=True)
class ProvinceRecord:
    province_code: str
    display_name: str


@dataclass(frozen=True, slots=True)
class ObservationRecord:
    observation_id: str
    product_id: str
    province_code: str
    acquired_at_utc: datetime
    latitude: float
    longitude: float
    confidence_code: Literal["l", "n", "h"]
    frp_mw: float
    daynight_code: Literal["D", "N"]


@dataclass(frozen=True, slots=True)
class CoverageRecord:
    date_utc: date
    coverage_status: Literal[
        "observations_present", "known_satellite_gap", "zero_detections_verified", "unknown"
    ]
    observation_count: int | None
    evidence_url: str | None
    note: str | None


@dataclass(frozen=True, slots=True)
class ProvinceCountRecord:
    province_code: str
    province_name: str
    province_order: int
    detection_count: int


@dataclass(frozen=True, slots=True)
class RepositoryMetadata:
    products: tuple[ProductRecord, ...]
    provinces: tuple[ProvinceRecord, ...]
    date_min: date
    date_max: date
    known_unavailable_dates: tuple[date, ...]
    source_attribution: str
    source_url: str
    dataset_version: str
    data_freshness: datetime | None
    data_status: Literal["mock", "verified"]


class HotspotRepository(Protocol):
    """Read-only boundary implemented later by parameterized ClickHouse queries."""

    async def metadata(self) -> RepositoryMetadata: ...

    async def count_by_month(
        self,
        *,
        product_id: str,
        province_codes: tuple[str, ...],
        date_from: date,
        date_to: date,
    ) -> dict[str, int]: ...

    async def count_by_year(
        self,
        *,
        product_id: str,
        province_code: str,
        years: tuple[int, ...],
    ) -> dict[int, int]: ...

    async def coverage(
        self,
        *,
        product_id: str,
        date_from: date,
        date_to: date,
    ) -> tuple[CoverageRecord, ...]: ...

    async def count_by_province(
        self,
        *,
        product_id: str,
        province_codes: tuple[str, ...],
        date_from: date,
        date_to: date,
    ) -> tuple[tuple[ProvinceCountRecord, ...], int]: ...

    async def observations(
        self,
        *,
        product_id: str,
        province_code: str,
        date_from: date,
        date_to: date,
        limit: int,
    ) -> tuple[list[ObservationRecord], bool]: ...
