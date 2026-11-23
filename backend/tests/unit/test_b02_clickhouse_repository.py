from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any

import httpx
import pytest

from wildfire_api.contracts.data_v1 import PRODUCT_ID
from wildfire_api.core.errors import AppError
from wildfire_api.repositories.clickhouse import (
    QUERY_CATALOG,
    ClickHouseHotspotRepository,
    ClickHouseHttpQueryClient,
    QueryName,
)
from wildfire_api.schemas.hotspots import GeoJsonQuery, SummaryRequest
from wildfire_api.services.hotspots import HotspotService


class FixtureQueryClient:
    def __init__(self) -> None:
        self.calls: list[tuple[QueryName, Mapping[str, str | int | list[str]]]] = []

    async def query(
        self, name: QueryName, parameters: Mapping[str, str | int | list[str]]
    ) -> list[dict[str, Any]]:
        self.calls.append((name, parameters))
        if name == QueryName.PROVINCES:
            return [
                {
                    "contract_version": "1.0.0",
                    "province_code": "14",
                    "province_name": "Riau",
                    "required_attribution": "© OpenStreetMap contributors",
                }
            ]
        if name == QueryName.COVERAGE_WINDOW:
            return [
                {
                    "contract_version": "1.0.0",
                    "date_min": "2023-01-01",
                    "date_max": "2023-12-31",
                }
            ]
        if name == QueryName.KNOWN_GAPS:
            return [
                {"contract_version": "1.0.0", "date_utc": "2023-07-26"},
                {"contract_version": "1.0.0", "date_utc": "2023-07-27"},
            ]
        if name == QueryName.LATEST_BATCH:
            return [
                {
                    "contract_version": "1.0.0",
                    "source_url": "https://firms.modaps.eosdis.nasa.gov/data/country/",
                    "published_at_utc": "2026-10-23T00:00:00Z",
                }
            ]
        if name == QueryName.COVERAGE:
            rows = [
                {
                    "contract_version": "1.0.0",
                    "date_utc": "2023-07-25",
                    "coverage_status": "observations_present",
                    "observation_count": 2,
                    "evidence_url": None,
                    "note": None,
                },
                *[
                    {
                        "contract_version": "1.0.0",
                        "date_utc": gap,
                        "coverage_status": "known_satellite_gap",
                        "observation_count": None,
                        "evidence_url": (
                            "https://landweb.modaps.eosdis.nasa.gov/displayissue?id=480"
                        ),
                        "note": "Unavailable, never zero.",
                    }
                    for gap in ("2023-07-26", "2023-07-27")
                ],
            ]
            return [
                row
                for row in rows
                if str(parameters["date_from"]) <= row["date_utc"] <= str(parameters["date_to"])
            ]
        if name == QueryName.MONTHLY_COUNTS:
            return [{"contract_version": "1.0.0", "period": "2023-07", "detection_count": 1}]
        if name == QueryName.YEARLY_COUNTS:
            return [
                {
                    "contract_version": "1.1.0",
                    "year": year,
                    "detection_count": year - 2000,
                }
                for year in parameters["years"]
            ]
        if name == QueryName.OBSERVATIONS:
            limit = int(parameters["fetch_limit"])
            return [
                {
                    "contract_version": "1.0.0",
                    "observation_id": f"observation-{index:04d}",
                    "product_id": PRODUCT_ID,
                    "province_code": "14",
                    "acquired_at_utc": f"2023-07-25T03:{index:02d}:00Z",
                    "latitude": 0.5,
                    "longitude": 101.5,
                    "confidence_code": "n",
                    "frp_mw": 5.25,
                    "daynight_code": "D",
                }
                for index in range(min(limit, 3))
            ]
        raise AssertionError(name)


@pytest.fixture
def fixture_client() -> FixtureQueryClient:
    return FixtureQueryClient()


@pytest.fixture
def service(fixture_client: FixtureQueryClient) -> HotspotService:
    return HotspotService(
        ClickHouseHotspotRepository(fixture_client),
        max_date_range_days=366,
        max_features=5_000,
    )


@pytest.mark.asyncio
async def test_v11_year_comparison_uses_one_fixed_grouped_query(
    fixture_client: FixtureQueryClient,
) -> None:
    repository = ClickHouseHotspotRepository(fixture_client)
    result = await repository.count_by_year(
        product_id=PRODUCT_ID,
        province_code="14",
        years=(2023, 2024, 2025),
    )

    assert result == {2023: 23, 2024: 24, 2025: 25}
    assert fixture_client.calls[-1] == (
        QueryName.YEARLY_COUNTS,
        {"product_id": PRODUCT_ID, "province_code": "14", "years": [2023, 2024, 2025]},
    )


@pytest.mark.asyncio
async def test_d04_reference_queries_preserve_partial_and_unavailable_totals(
    service: HotspotService,
) -> None:
    partial = await service.summary(
        SummaryRequest(
            product_id=PRODUCT_ID,
            province_codes=["14"],
            date_from=date(2023, 7, 25),
            date_to=date(2023, 7, 27),
            group_by="month",
        ),
        "partial",
    )
    assert partial.total == 1
    assert partial.is_complete is False
    assert [issue.date_utc.isoformat() for issue in partial.coverage_issues] == [
        "2023-07-26",
        "2023-07-27",
    ]

    unavailable = await service.summary(
        SummaryRequest(
            product_id=PRODUCT_ID,
            province_codes=["14"],
            date_from=date(2023, 7, 26),
            date_to=date(2023, 7, 27),
            group_by="month",
        ),
        "unavailable",
    )
    assert unavailable.total is None
    assert unavailable.series[0].count is None
    assert unavailable.is_complete is False


@pytest.mark.asyncio
async def test_map_uses_limit_plus_one_and_drops_sentinel(
    service: HotspotService, fixture_client: FixtureQueryClient
) -> None:
    response = await service.geojson(
        GeoJsonQuery(
            product_id=PRODUCT_ID,
            province_code="14",
            date_from=date(2023, 7, 25),
            date_to=date(2023, 7, 25),
            limit=2,
        ),
        "map",
    )
    assert len(response.features) == 2
    assert response.metadata.truncated is True
    observation_call = next(
        call for call in fixture_client.calls if call[0] == QueryName.OBSERVATIONS
    )
    assert observation_call[1]["fetch_limit"] == 3


@pytest.mark.asyncio
async def test_missing_daily_coverage_fails_closed_as_unknown(
    service: HotspotService, fixture_client: FixtureQueryClient
) -> None:
    original = fixture_client.query

    async def omit_last_day(
        name: QueryName, parameters: Mapping[str, str | int | list[str]]
    ) -> list[dict[str, Any]]:
        rows = await original(name, parameters)
        if name == QueryName.COVERAGE:
            return [row for row in rows if row["date_utc"] != "2023-07-27"]
        return rows

    fixture_client.query = omit_last_day  # type: ignore[method-assign]
    response = await service.summary(
        SummaryRequest(
            product_id=PRODUCT_ID,
            province_codes=["14"],
            date_from=date(2023, 7, 26),
            date_to=date(2023, 7, 27),
            group_by="month",
        ),
        "missing-coverage",
    )
    assert response.total is None
    assert [issue.coverage_status for issue in response.coverage_issues] == [
        "known_satellite_gap",
        "unknown",
    ]


def test_query_catalog_is_static_select_only_and_has_no_user_values() -> None:
    attacker = "14'); DROP TABLE analytics_hotspot_observations_v1; --"
    for definition in QUERY_CATALOG.values():
        normalized = definition.sql.lstrip().upper()
        assert normalized.startswith("SELECT")
        assert ";" not in definition.sql
        assert attacker not in definition.sql
    assert set(QUERY_CATALOG) == set(QueryName)


@pytest.mark.asyncio
async def test_http_client_enforces_readonly_and_parameter_binding() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"data": []})

    client = ClickHouseHttpQueryClient(
        url="https://clickhouse.example.test/",
        database="wildfire",
        username="reader",
        password="server-secret",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )
    attacker = "14'); DROP TABLE analytics_hotspot_observations_v1; --"
    await client.query(
        QueryName.MONTHLY_COUNTS,
        {
            "product_id": PRODUCT_ID,
            "province_codes": [attacker],
            "date_from": "2023-07-01",
            "date_to": "2023-07-31",
        },
    )
    request = captured[0]
    assert request.url.params["readonly"] == "2"
    assert request.url.params["param_province_codes"] == (
        "['14\\'); DROP TABLE analytics_hotspot_observations_v1; --']"
    )
    assert attacker not in request.content.decode()
    assert "DROP TABLE" not in request.content.decode()


@pytest.mark.asyncio
async def test_http_timeout_maps_to_typed_safe_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("internal detail", request=request)

    client = ClickHouseHttpQueryClient(
        url="https://clickhouse.example.test/",
        database="wildfire",
        username="reader",
        password="server-secret",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(AppError) as caught:
        await client.query(QueryName.PROVINCES, {})
    assert caught.value.code == "REQUEST_TIMEOUT"
    assert caught.value.status_code == 504
    assert "internal detail" not in caught.value.message


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [[], "not-an-object", None])
async def test_http_client_rejects_non_object_json_payload(payload: object) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if payload is None:
            return httpx.Response(
                200, content=b"null", headers={"Content-Type": "application/json"}
            )
        return httpx.Response(200, json=payload)

    client = ClickHouseHttpQueryClient(
        url="https://clickhouse.example.test/",
        database="wildfire",
        username="reader",
        password="server-secret",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(AppError) as caught:
        await client.query(QueryName.PROVINCES, {})
    assert caught.value.code == "DEPENDENCY_UNAVAILABLE"
    assert caught.value.status_code == 503
    assert caught.value.message == "Analytics database returned an invalid response."


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query_name", "mutate"),
    [
        (QueryName.COVERAGE, lambda row: row.update(coverage_status="fabricated")),
        (QueryName.COVERAGE, lambda row: row.update(observation_count=0)),
        (QueryName.MONTHLY_COUNTS, lambda row: row.update(detection_count=-1)),
        (QueryName.OBSERVATIONS, lambda row: row.update(latitude=91)),
        (QueryName.OBSERVATIONS, lambda row: row.update(confidence_code="certain")),
    ],
)
async def test_malformed_d04_rows_fail_as_typed_dependency_errors(
    fixture_client: FixtureQueryClient,
    query_name: QueryName,
    mutate: Any,
) -> None:
    original = fixture_client.query

    async def malformed(
        name: QueryName, parameters: Mapping[str, str | int | list[str]]
    ) -> list[dict[str, Any]]:
        rows = await original(name, parameters)
        if name == query_name and rows:
            mutate(rows[0])
        return rows

    fixture_client.query = malformed  # type: ignore[method-assign]
    repository = ClickHouseHotspotRepository(fixture_client)
    with pytest.raises(AppError) as caught:
        if query_name == QueryName.COVERAGE:
            await repository.coverage(
                product_id=PRODUCT_ID,
                date_from=date(2023, 7, 25),
                date_to=date(2023, 7, 25),
            )
        elif query_name == QueryName.MONTHLY_COUNTS:
            await repository.count_by_month(
                product_id=PRODUCT_ID,
                province_codes=("14",),
                date_from=date(2023, 7, 25),
                date_to=date(2023, 7, 25),
            )
        else:
            await repository.observations(
                product_id=PRODUCT_ID,
                province_code="14",
                date_from=date(2023, 7, 25),
                date_to=date(2023, 7, 25),
                limit=2,
            )
    assert caught.value.code == "DEPENDENCY_UNAVAILABLE"
    assert caught.value.status_code == 503
    assert caught.value.message == "Analytics database returned invalid contract data."


@pytest.mark.asyncio
async def test_unsupported_contract_major_fails_closed(
    fixture_client: FixtureQueryClient,
) -> None:
    original = fixture_client.query

    async def incompatible(
        name: QueryName, parameters: Mapping[str, str | int | list[str]]
    ) -> list[dict[str, Any]]:
        rows = await original(name, parameters)
        for row in rows:
            row["contract_version"] = "2.0.0"
        return rows

    fixture_client.query = incompatible  # type: ignore[method-assign]
    repository = ClickHouseHotspotRepository(fixture_client)
    with pytest.raises(AppError) as caught:
        await repository.metadata()
    assert caught.value.code == "DEPENDENCY_UNAVAILABLE"
    assert "Unsupported analytics data contract" in caught.value.message
