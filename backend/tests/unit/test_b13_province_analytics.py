from datetime import UTC, date, datetime, timedelta

import pytest

from wildfire_api.agent.filter_resolver import PROVINCES_V1
from wildfire_api.repositories.hotspots import (
    CoverageRecord,
    ProductRecord,
    ProvinceCountRecord,
    ProvinceRecord,
    RepositoryMetadata,
)
from wildfire_api.services.hotspots import HotspotService


class ProvinceRepository:
    async def metadata(self) -> RepositoryMetadata:
        return RepositoryMetadata(
            products=(ProductRecord("VNP14IMG.002_SNPP_FIRMS_SP", "VIIRS S-NPP"),),
            provinces=tuple(ProvinceRecord(code, name) for code, name, _ in PROVINCES_V1),
            date_min=date(2023, 1, 1),
            date_max=date(2023, 12, 31),
            known_unavailable_dates=(),
            source_attribution="NASA FIRMS; OSM province boundaries",
            source_url="https://firms.modaps.eosdis.nasa.gov/",
            dataset_version="test-v1",
            data_freshness=datetime(2023, 12, 31, tzinfo=UTC),
            data_status="verified",
        )

    async def count_by_province(self, *, product_id, province_codes, date_from, date_to):
        values = {"11": 7, "13": 11, "14": 21}
        selected = province_codes or tuple(code for code, _, _ in PROVINCES_V1)
        rows = tuple(
            ProvinceCountRecord(code, name, order, values.get(code, 0))
            for order, (code, name, _) in enumerate(PROVINCES_V1, 1)
            if code in selected
        )
        return rows, 3

    async def coverage(self, *, product_id, date_from, date_to):
        rows = []
        current = date_from
        while current <= date_to:
            rows.append(CoverageRecord(current, "observations_present", 1, None, None))
            current += timedelta(days=1)
        return tuple(rows)


SERVICE = HotspotService(ProvinceRepository(), max_date_range_days=366, max_features=500)


@pytest.mark.asyncio
async def test_two_province_total_preserves_requested_order() -> None:
    analytics = await SERVICE.province_analytics(
        product_id="VNP14IMG.002_SNPP_FIRMS_SP",
        province_codes=("13", "11"),
        date_from=date(2023, 9, 1),
        date_to=date(2023, 9, 30),
        ranking=False,
        comparison_requested=True,
    )
    result = analytics.result
    assert result.kind == "province_breakdown"
    assert result.total == 18
    assert [row.count for row in result.rows] == [11, 7]
    assert result.comparison and result.comparison.max_min_difference == 4
    assert analytics.execution.operation_id == "hotspot_multi_province_summary_v1"


@pytest.mark.asyncio
async def test_highest_province_ranking_includes_exact_typed_result() -> None:
    analytics = await SERVICE.province_analytics(
        product_id="VNP14IMG.002_SNPP_FIRMS_SP",
        province_codes=(),
        date_from=date(2023, 9, 1),
        date_to=date(2023, 9, 30),
        ranking=True,
    )
    result = analytics.result
    assert result.kind == "province_ranking"
    assert [(row.province_code, row.count, row.dense_rank) for row in result.rows] == [
        ("14", 21, 1)
    ]
    assert analytics.execution.operation_id == "hotspot_province_ranking_v1"
