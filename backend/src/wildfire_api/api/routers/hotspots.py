from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from wildfire_api.api.dependencies import HotspotServiceDependency
from wildfire_api.core.request_context import get_request_id
from wildfire_api.schemas.hotspots import (
    GeoJsonQuery,
    GeoJsonResponse,
    SummaryRequest,
    SummaryResponse,
    YearComparisonRequest,
    YearComparisonResponse,
)

router = APIRouter(prefix="/hotspots", tags=["hotspots"])


@router.post("/summary", response_model=SummaryResponse)
async def summary(payload: SummaryRequest, service: HotspotServiceDependency) -> SummaryResponse:
    return await service.summary(payload, get_request_id())


@router.post("/year-comparison", response_model=YearComparisonResponse)
async def year_comparison(
    payload: YearComparisonRequest, service: HotspotServiceDependency
) -> YearComparisonResponse:
    return await service.year_comparison(payload, get_request_id())


@router.get("/geojson", response_model=GeoJsonResponse)
async def geojson(
    service: HotspotServiceDependency,
    product_id: Annotated[str, Query(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")],
    province_code: Annotated[str, Query(min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")],
    date_from: Annotated[date, Query()],
    date_to: Annotated[date, Query()],
    limit: Annotated[int, Query(ge=1, le=5_000)] = 500,
) -> GeoJsonResponse:
    query = GeoJsonQuery(
        product_id=product_id,
        province_code=province_code,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )
    return await service.geojson(query, get_request_id())
