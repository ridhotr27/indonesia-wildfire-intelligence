from datetime import date

import pytest

from wildfire_api.core.errors import AppError
from wildfire_api.repositories.mock import MockHotspotRepository
from wildfire_api.schemas.hotspots import SummaryRequest
from wildfire_api.services.hotspots import HotspotService


@pytest.fixture
def service() -> HotspotService:
    return HotspotService(MockHotspotRepository(), max_date_range_days=366, max_features=500)


@pytest.mark.asyncio
async def test_summary_aggregates_only_synthetic_records(service: HotspotService) -> None:
    response = await service.summary(
        SummaryRequest(
            product_id="MOCK_ONLY",
            province_codes=["MOCK-WEST"],
            date_from=date(2023, 9, 1),
            date_to=date(2023, 10, 31),
            group_by="month",
        ),
        "request-1",
    )

    assert response.total == 3
    assert [point.count for point in response.series] == [2, 1]
    assert response.source.data_status == "mock"
    assert "not NASA" in response.source.attribution


@pytest.mark.asyncio
async def test_summary_rejects_unknown_product(service: HotspotService) -> None:
    with pytest.raises(AppError) as caught:
        await service.summary(
            SummaryRequest(
                product_id="REAL_LOOKING_PRODUCT",
                province_codes=["MOCK-WEST"],
                date_from=date(2023, 9, 1),
                date_to=date(2023, 9, 30),
                group_by="month",
            ),
            "request-1",
        )

    assert caught.value.code == "INVALID_FILTER"
    assert caught.value.status_code == 400
