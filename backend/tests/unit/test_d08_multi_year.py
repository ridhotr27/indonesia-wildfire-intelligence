from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from wildfire_api.agent.filter_resolver import ChatFilterResolver, ResolutionStatus
from wildfire_api.agent.intent_router import DeterministicIntentRouter
from wildfire_api.repositories.hotspots import (
    CoverageRecord,
    ProductRecord,
    ProvinceRecord,
    RepositoryMetadata,
)
from wildfire_api.schemas.hotspots import YearComparisonRequest, YearComparisonResponse
from wildfire_api.services.hotspots import HotspotService


class MultiYearRepository:
    async def metadata(self) -> RepositoryMetadata:
        return RepositoryMetadata(
            products=(ProductRecord("VNP14IMG.002_SNPP_FIRMS_SP", "VIIRS S-NPP"),),
            provinces=(ProvinceRecord("14", "Riau"),),
            date_min=date(2023, 1, 1),
            date_max=date(2025, 12, 31),
            known_unavailable_dates=(date(2023, 7, 26), date(2023, 7, 27)),
            source_attribution="NASA FIRMS; province boundaries: © OpenStreetMap contributors",
            source_url="https://firms.modaps.eosdis.nasa.gov/data/country/",
            dataset_version="hotspot-data-contract-v1.1.0",
            data_freshness=datetime(2026, 11, 21, tzinfo=UTC),
            data_status="verified",
        )

    async def count_by_year(
        self, *, product_id: str, province_code: str, years: tuple[int, ...]
    ) -> dict[int, int]:
        assert years == (2023, 2024, 2025)
        return {2023: 10, 2024: 20, 2025: 30}

    async def coverage(self, *, product_id: str, date_from: date, date_to: date):
        rows = []
        current = date_from
        while current <= date_to:
            unknown = current == date(2024, 1, 2)
            rows.append(
                CoverageRecord(
                    date_utc=current,
                    coverage_status="unknown" if unknown else "observations_present",
                    observation_count=None if unknown else 1,
                    evidence_url=None,
                    note="Annual artifact has no row for this date." if unknown else None,
                )
            )
            current += timedelta(days=1)
        return tuple(rows)


@pytest.mark.asyncio
async def test_year_comparison_preserves_unknown_dates_and_counts() -> None:
    service = HotspotService(MultiYearRepository(), max_date_range_days=366, max_features=500)  # type: ignore[arg-type]
    response = await service.year_comparison(
        YearComparisonRequest(
            product_id="VNP14IMG.002_SNPP_FIRMS_SP",
            province_code="14",
            years=[2023, 2024, 2025],
        ),
        "d08",
    )

    assert [point.count for point in response.points] == [10, 20, 30]
    assert [point.is_complete for point in response.points] == [True, False, True]
    assert response.points[1].coverage_issues[0].coverage_status == "unknown"


def test_year_comparison_request_rejects_duplicates_and_reordering() -> None:
    with pytest.raises(ValidationError):
        YearComparisonRequest(
            product_id="VNP14IMG.002_SNPP_FIRMS_SP",
            province_code="14",
            years=[2024, 2023],
        )


def test_chat_resolver_accepts_typed_year_comparison() -> None:
    resolved = ChatFilterResolver().resolve(
        "Compare Riau hotspot detections in 2023, 2024, and 2025",
        province_code=None,
        date_from=None,
        date_to=None,
    )

    assert resolved.status == ResolutionStatus.RESOLVED
    assert resolved.province_code == "14"
    assert resolved.comparison_years == (2023, 2024, 2025)
    assert (resolved.date_from, resolved.date_to) == (date(2023, 1, 1), date(2025, 12, 31))


def test_chat_router_accepts_supported_multi_year_comparison() -> None:
    decision = DeterministicIntentRouter().decide(
        "Compare Riau hotspot detections in 2023, 2024, and 2025"
    )

    assert decision.mode == "analytics"
    assert decision.intent_codes == ("analytics_operation",)


def test_versioned_year_comparison_fixture_matches_models() -> None:
    fixture_path = Path(__file__).parents[1] / "fixtures" / "d08_year_comparison.fixture.json"
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    request = YearComparisonRequest.model_validate(payload["request"])
    response = YearComparisonResponse.model_validate(payload["response"])

    assert request.years == response.years
    assert response.source.dataset_version == "hotspot-data-contract-v1.1.0"
