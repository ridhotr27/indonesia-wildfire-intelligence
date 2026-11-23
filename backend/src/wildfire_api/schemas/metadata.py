from datetime import date
from typing import Literal

from pydantic import Field

from wildfire_api.schemas.common import SourceInfo, StrictModel, UtcDateTime


class ProductMetadata(StrictModel):
    product_id: str
    display_name: str


class ProvinceMetadata(StrictModel):
    province_code: str
    display_name: str


class CoverageWindow(StrictModel):
    date_min: date
    date_max: date
    known_unavailable_dates: list[date]


class MetadataResponse(StrictModel):
    request_id: str
    api_version: Literal["1.0.0"] = "1.0.0"
    products: list[ProductMetadata]
    provinces: list[ProvinceMetadata]
    coverage: CoverageWindow
    source: SourceInfo
    data_freshness_at: UtcDateTime | None
    data_status: Literal["mock", "verified"] = Field(
        description="'mock' until a verified DE data contract is integrated"
    )
