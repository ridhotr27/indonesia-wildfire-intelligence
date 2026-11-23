from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError, model_validator

from wildfire_api.contracts.data_v1 import PRODUCT_ID, UnsupportedContractVersion
from wildfire_api.core.errors import dependency_unavailable, request_timeout
from wildfire_api.repositories.hotspots import (
    CoverageRecord,
    ObservationRecord,
    ProductRecord,
    ProvinceCountRecord,
    ProvinceRecord,
    RepositoryMetadata,
)


class _QueryRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    contract_version: str


class _ProvinceRow(_QueryRow):
    province_code: str = Field(pattern=r"^[0-9]{2}$")
    province_name: str = Field(min_length=1)
    required_attribution: str = Field(min_length=1)


class _CoverageWindowRow(_QueryRow):
    date_min: date
    date_max: date

    @model_validator(mode="after")
    def dates_are_ordered(self) -> _CoverageWindowRow:
        if self.date_max < self.date_min:
            raise ValueError("invalid coverage window")
        return self


class _GapRow(_QueryRow):
    date_utc: date


class _BatchRow(_QueryRow):
    source_url: HttpUrl
    published_at_utc: datetime


class _MonthlyCountRow(_QueryRow):
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    detection_count: int = Field(ge=0)


class _YearlyCountRow(_QueryRow):
    year: int = Field(ge=2023, le=2025)
    detection_count: int = Field(ge=0)


class _ProvinceCountRow(_QueryRow):
    province_code: str = Field(pattern=r"^[0-9]{2}$")
    province_name: str = Field(min_length=1)
    province_order: int = Field(ge=1, le=38)
    detection_count: int = Field(ge=0)
    not_single_province_count: int = Field(ge=0)


class _CoverageRow(_QueryRow):
    date_utc: date
    coverage_status: str
    observation_count: int | None = Field(default=None, ge=0)
    evidence_url: HttpUrl | None = None
    note: str | None = None

    @model_validator(mode="after")
    def coverage_is_consistent(self) -> _CoverageRow:
        valid = {
            "observations_present",
            "known_satellite_gap",
            "zero_detections_verified",
            "unknown",
        }
        if self.coverage_status not in valid:
            raise ValueError("invalid coverage status")
        if self.coverage_status == "observations_present" and (
            self.observation_count is None or self.observation_count <= 0
        ):
            raise ValueError("present coverage requires a positive count")
        if self.coverage_status in {"known_satellite_gap", "unknown"}:
            if self.observation_count is not None:
                raise ValueError("unavailable coverage cannot have a count")
        if self.coverage_status == "known_satellite_gap" and self.evidence_url is None:
            raise ValueError("known gaps require evidence")
        if self.coverage_status == "zero_detections_verified" and (
            self.observation_count != 0 or self.evidence_url is None
        ):
            raise ValueError("verified zero requires zero and evidence")
        return self


class _ObservationRow(_QueryRow):
    observation_id: str = Field(min_length=1)
    product_id: str
    province_code: str = Field(pattern=r"^[0-9]{2}$")
    acquired_at_utc: datetime
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    confidence_code: str = Field(pattern=r"^[lnh]$")
    frp_mw: float = Field(ge=0)
    daynight_code: str = Field(pattern=r"^[DN]$")

    @model_validator(mode="after")
    def identity_is_supported(self) -> _ObservationRow:
        if self.product_id != PRODUCT_ID:
            raise ValueError("unsupported observation product")
        return self


class QueryName(StrEnum):
    PROVINCES = "provinces"
    COVERAGE_WINDOW = "coverage_window"
    KNOWN_GAPS = "known_gaps"
    LATEST_BATCH = "latest_batch"
    COVERAGE = "coverage"
    MONTHLY_COUNTS = "monthly_counts"
    YEARLY_COUNTS = "yearly_counts"
    PROVINCE_COUNTS = "province_counts"
    OBSERVATIONS = "observations"


@dataclass(frozen=True, slots=True)
class QueryDefinition:
    sql: str
    parameters: frozenset[str]
    max_result_rows: int


QUERY_CATALOG: dict[QueryName, QueryDefinition] = {
    QueryName.PROVINCES: QueryDefinition(
        """SELECT contract_version, province_code, province_name, required_attribution
FROM analytics_provinces_v1
WHERE is_supported = true
ORDER BY province_code
FORMAT JSON""",
        frozenset(),
        38,
    ),
    QueryName.COVERAGE_WINDOW: QueryDefinition(
        """SELECT contract_version, min(date_utc) AS date_min, max(date_utc) AS date_max
FROM analytics_daily_coverage_v1
WHERE product_id = {product_id:String}
GROUP BY contract_version
FORMAT JSON""",
        frozenset({"product_id"}),
        2,
    ),
    QueryName.KNOWN_GAPS: QueryDefinition(
        """SELECT contract_version, date_utc
FROM analytics_daily_coverage_v1
WHERE product_id = {product_id:String} AND coverage_status = 'known_satellite_gap'
ORDER BY date_utc
FORMAT JSON""",
        frozenset({"product_id"}),
        366,
    ),
    QueryName.LATEST_BATCH: QueryDefinition(
        """SELECT contract_version, source_url, published_at_utc
FROM analytics_ingestion_batches_v1
WHERE product_id = {product_id:String} AND publication_status = 'published'
ORDER BY published_at_utc DESC
LIMIT 1
FORMAT JSON""",
        frozenset({"product_id"}),
        1,
    ),
    QueryName.COVERAGE: QueryDefinition(
        """SELECT contract_version, date_utc, coverage_status, observation_count,
       evidence_url, note
FROM analytics_daily_coverage_v1
WHERE product_id = {product_id:String}
  AND date_utc BETWEEN {date_from:Date} AND {date_to:Date}
ORDER BY date_utc
FORMAT JSON""",
        frozenset({"product_id", "date_from", "date_to"}),
        1_096,
    ),
    QueryName.MONTHLY_COUNTS: QueryDefinition(
        """SELECT contract_version,
       formatDateTime(toStartOfMonth(acquired_at_utc), '%Y-%m') AS period,
       count() AS detection_count
FROM analytics_hotspot_observations_v1
WHERE product_id = {product_id:String}
  AND has({province_codes:Array(String)}, province_code)
  AND acquired_at_utc >= toDateTime({date_from:Date}, 'UTC')
  AND acquired_at_utc < toDateTime(addDays({date_to:Date}, 1), 'UTC')
GROUP BY contract_version, period
ORDER BY period
FORMAT JSON""",
        frozenset({"product_id", "province_codes", "date_from", "date_to"}),
        12,
    ),
    QueryName.YEARLY_COUNTS: QueryDefinition(
        """SELECT contract_version, toYear(acquired_at_utc) AS year,
       count() AS detection_count
FROM analytics_hotspot_observations_v1
WHERE product_id = {product_id:String}
  AND province_code = {province_code:String}
  AND geo_assignment_status = 'assigned'
  AND has({years:Array(UInt16)}, toYear(acquired_at_utc))
GROUP BY contract_version, year
ORDER BY year
FORMAT JSON""",
        frozenset({"product_id", "province_code", "years"}),
        3,
    ),
    QueryName.PROVINCE_COUNTS: QueryDefinition(
        """SELECT p.contract_version, p.province_code, p.province_name, p.province_order,
       coalesce(c.detection_count, 0) AS detection_count,
       (SELECT count()
        FROM analytics_hotspot_observations_v1
        WHERE product_id = {product_id:String}
          AND acquired_at_utc >= toDateTime({date_from:Date}, 'UTC')
          AND acquired_at_utc < toDateTime(addDays({date_to:Date}, 1), 'UTC')
          AND geo_assignment_status != 'assigned') AS not_single_province_count
FROM (
  SELECT contract_version, province_code, province_name, is_supported,
         row_number() OVER (ORDER BY province_code) AS province_order
  FROM analytics_provinces_v1
) AS p
LEFT JOIN (
  SELECT province_code, count() AS detection_count
  FROM analytics_hotspot_observations_v1
  WHERE product_id = {product_id:String}
    AND acquired_at_utc >= toDateTime({date_from:Date}, 'UTC')
    AND acquired_at_utc < toDateTime(addDays({date_to:Date}, 1), 'UTC')
    AND geo_assignment_status = 'assigned'
  GROUP BY province_code
) AS c ON c.province_code = p.province_code
WHERE p.is_supported = true
  AND (empty({province_codes:Array(String)})
       OR has({province_codes:Array(String)}, p.province_code))
ORDER BY p.province_code
FORMAT JSON""",
        frozenset({"product_id", "province_codes", "date_from", "date_to"}),
        38,
    ),
    QueryName.OBSERVATIONS: QueryDefinition(
        """SELECT contract_version, observation_id, product_id, province_code,
       acquired_at_utc, latitude, longitude, confidence_code, frp_mw, daynight_code
FROM analytics_hotspot_observations_v1
WHERE product_id = {product_id:String}
  AND province_code = {province_code:String}
  AND geo_assignment_status = 'assigned'
  AND acquired_at_utc >= toDateTime({date_from:Date}, 'UTC')
  AND acquired_at_utc < toDateTime(addDays({date_to:Date}, 1), 'UTC')
ORDER BY acquired_at_utc, observation_id
LIMIT {fetch_limit:UInt16}
FORMAT JSON""",
        frozenset({"product_id", "province_code", "date_from", "date_to", "fetch_limit"}),
        5_001,
    ),
}


class QueryClient(Protocol):
    async def query(
        self, name: QueryName, parameters: Mapping[str, str | int | list[str] | list[int]]
    ) -> list[dict[str, Any]]: ...


class ClickHouseHttpQueryClient:
    """Executes only the static SELECT catalog through ClickHouse HTTP parameters."""

    def __init__(
        self,
        *,
        url: str,
        database: str,
        username: str,
        password: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._url = url
        self._database = database
        self._username = username
        self._password = password
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def query(
        self, name: QueryName, parameters: Mapping[str, str | int | list[str] | list[int]]
    ) -> list[dict[str, Any]]:
        definition = QUERY_CATALOG[name]
        if set(parameters) != definition.parameters:
            raise ValueError(f"invalid parameter set for query {name}")
        request_parameters: dict[str, str | int | list[str]] = {
            "database": self._database,
            "readonly": 2,
            "max_execution_time": max(1, int(self._timeout_seconds)),
            "max_result_rows": definition.max_result_rows,
            "result_overflow_mode": "throw",
        }
        request_parameters.update(
            {
                f"param_{key}": self._encode_array(value)
                if isinstance(value, list)
                else value
                for key, value in parameters.items()
            }
        )
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds, transport=self._transport
            ) as client:
                response = await client.post(
                    self._url,
                    params=request_parameters,
                    content=definition.sql,
                    auth=(self._username, self._password),
                    headers={"Content-Type": "text/plain; charset=utf-8"},
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException as exc:
            raise request_timeout("Analytics query timed out.") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise dependency_unavailable("Analytics database is unavailable.") from exc
        if not isinstance(payload, Mapping):
            raise dependency_unavailable("Analytics database returned an invalid response.")
        rows = payload.get("data")
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise dependency_unavailable("Analytics database returned an invalid response.")
        return rows

    @staticmethod
    def _encode_array(values: list[str] | list[int]) -> str:
        """Encode allowlisted ClickHouse array parameters (not JSON array syntax)."""
        encoded = [
            str(value)
            if isinstance(value, int)
            else "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"
            for value in values
        ]
        return "[" + ",".join(encoded) + "]"


class ClickHouseHotspotRepository:
    def __init__(self, client: QueryClient) -> None:
        self._client = client

    async def metadata(self) -> RepositoryMetadata:
        raw_provinces = await self._client.query(QueryName.PROVINCES, {})
        raw_window = await self._client.query(QueryName.COVERAGE_WINDOW, {"product_id": PRODUCT_ID})
        raw_gaps = await self._client.query(QueryName.KNOWN_GAPS, {"product_id": PRODUCT_ID})
        raw_batches = await self._client.query(QueryName.LATEST_BATCH, {"product_id": PRODUCT_ID})
        provinces = self._validate_rows(_ProvinceRow, raw_provinces)
        window = self._validate_rows(_CoverageWindowRow, raw_window)
        gaps = self._validate_rows(_GapRow, raw_gaps)
        batches = self._validate_rows(_BatchRow, raw_batches)
        if len(window) != 1 or len(batches) != 1 or not provinces:
            raise dependency_unavailable("Published analytics metadata is incomplete.")
        attribution = provinces[0].required_attribution
        batch = batches[0]
        return RepositoryMetadata(
            products=(ProductRecord(PRODUCT_ID, "VIIRS S-NPP VNP14IMG.002 (FIRMS SP)"),),
            provinces=tuple(
                ProvinceRecord(row.province_code, row.province_name) for row in provinces
            ),
            date_min=window[0].date_min,
            date_max=window[0].date_max,
            known_unavailable_dates=tuple(row.date_utc for row in gaps),
            source_attribution=f"NASA FIRMS; province boundaries: {attribution}",
            source_url=str(batch.source_url),
            dataset_version=f"hotspot-data-contract-v{window[0].contract_version}",
            data_freshness=self._utc_datetime(batch.published_at_utc),
            data_status="verified",
        )

    async def count_by_month(
        self,
        *,
        product_id: str,
        province_codes: tuple[str, ...],
        date_from: date,
        date_to: date,
    ) -> dict[str, int]:
        rows = await self._client.query(
            QueryName.MONTHLY_COUNTS,
            {
                "product_id": product_id,
                "province_codes": list(province_codes),
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
            },
        )
        validated = self._validate_rows(_MonthlyCountRow, rows)
        return {row.period: row.detection_count for row in validated}

    async def count_by_year(
        self, *, product_id: str, province_code: str, years: tuple[int, ...]
    ) -> dict[int, int]:
        rows = await self._client.query(
            QueryName.YEARLY_COUNTS,
            {
                "product_id": product_id,
                "province_code": province_code,
                "years": list(years),
            },
        )
        validated = self._validate_rows(_YearlyCountRow, rows)
        return {row.year: row.detection_count for row in validated}

    async def coverage(
        self,
        *,
        product_id: str,
        date_from: date,
        date_to: date,
    ) -> tuple[CoverageRecord, ...]:
        rows = await self._client.query(
            QueryName.COVERAGE,
            {
                "product_id": product_id,
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
            },
        )
        validated = self._validate_rows(_CoverageRow, rows)
        return tuple(
            CoverageRecord(
                date_utc=row.date_utc,
                coverage_status=row.coverage_status,
                observation_count=row.observation_count,
                evidence_url=None if row.evidence_url is None else str(row.evidence_url),
                note=row.note,
            )
            for row in validated
        )

    async def count_by_province(
        self, *, product_id: str, province_codes: tuple[str, ...], date_from: date, date_to: date
    ) -> tuple[tuple[ProvinceCountRecord, ...], int]:
        rows = await self._client.query(
            QueryName.PROVINCE_COUNTS,
            {
                "product_id": product_id,
                "province_codes": list(province_codes),
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
            },
        )
        validated = self._validate_rows(_ProvinceCountRow, rows)
        return (
            tuple(
                ProvinceCountRecord(
                    row.province_code, row.province_name, row.province_order, row.detection_count
                )
                for row in validated
            ),
            validated[0].not_single_province_count if validated else 0,
        )

    async def observations(
        self,
        *,
        product_id: str,
        province_code: str,
        date_from: date,
        date_to: date,
        limit: int,
    ) -> tuple[list[ObservationRecord], bool]:
        fetch_limit = min(limit, 5_000) + 1
        rows = await self._client.query(
            QueryName.OBSERVATIONS,
            {
                "product_id": product_id,
                "province_code": province_code,
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
                "fetch_limit": fetch_limit,
            },
        )
        validated = self._validate_rows(_ObservationRow, rows)
        observations = [
            ObservationRecord(
                observation_id=row.observation_id,
                product_id=row.product_id,
                province_code=row.province_code,
                acquired_at_utc=self._utc_datetime(row.acquired_at_utc),
                latitude=row.latitude,
                longitude=row.longitude,
                confidence_code=row.confidence_code,
                frp_mw=row.frp_mw,
                daynight_code=row.daynight_code,
            )
            for row in validated[:limit]
        ]
        return observations, len(validated) > limit

    @staticmethod
    def _validate_rows[Row: _QueryRow](model: type[Row], rows: list[dict[str, Any]]) -> list[Row]:
        try:
            validated = [model.model_validate(row) for row in rows]
        except ValidationError as exc:
            error = dependency_unavailable("Analytics database returned invalid contract data.")
            raise error from exc
        for row in validated:
            version = row.contract_version
            try:
                major = int(version.split(".", maxsplit=1)[0])
            except (TypeError, ValueError) as exc:
                raise dependency_unavailable("Analytics data contract version is invalid.") from exc
            if major != 1:
                raise dependency_unavailable(
                    f"Unsupported analytics data contract major version: {version}"
                ) from UnsupportedContractVersion(version)
        return validated

    @staticmethod
    def _utc_datetime(value: object) -> datetime:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        # ClickHouse DateTime64('UTC') JSON output omits the zone suffix; the view type
        # provides the UTC guarantee in that case.
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed
