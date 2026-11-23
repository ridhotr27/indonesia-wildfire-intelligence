from datetime import date
from typing import Annotated, Literal

from pydantic import Field, model_validator

from wildfire_api.schemas.common import (
    CoverageIssue,
    Filters,
    SourceInfo,
    StrictModel,
    UtcDateTime,
)

ProductId = Annotated[str, Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")]
ProvinceCode = Annotated[str, Field(min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")]


class DateRangeModel(StrictModel):
    date_from: date
    date_to: date

    @model_validator(mode="after")
    def dates_are_ordered(self) -> "DateRangeModel":
        if self.date_to < self.date_from:
            raise ValueError("date_to must be on or after date_from")
        return self


class SummaryRequest(DateRangeModel):
    product_id: ProductId
    province_codes: list[ProvinceCode] = Field(min_length=1, max_length=38)
    group_by: Literal["month"]

    @model_validator(mode="after")
    def province_codes_are_distinct(self) -> "SummaryRequest":
        if len(self.province_codes) != len(set(self.province_codes)):
            raise ValueError("province_codes must be distinct")
        return self


class SummaryPoint(StrictModel):
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    count: int | None = Field(default=None, ge=0)
    is_complete: bool
    coverage_issues: list[CoverageIssue]

    @model_validator(mode="after")
    def coverage_matches_count(self) -> "SummaryPoint":
        if self.is_complete and self.coverage_issues:
            raise ValueError("complete periods cannot have coverage issues")
        if self.count is None and self.is_complete:
            raise ValueError("a complete period requires a numeric count")
        return self


class SummaryResponse(StrictModel):
    request_id: str
    metric: Literal["satellite_hotspot_detections"]
    product_id: str
    filters: Filters
    total: int | None = Field(default=None, ge=0)
    is_complete: bool
    coverage_issues: list[CoverageIssue]
    warnings: list[str]
    series: list[SummaryPoint]
    source: SourceInfo
    caveat: Literal["Hotspot detections are not confirmed wildfires."]

    @model_validator(mode="after")
    def coverage_matches_total(self) -> "SummaryResponse":
        if self.is_complete and self.coverage_issues:
            raise ValueError("complete responses cannot have coverage issues")
        if not self.is_complete and not self.coverage_issues:
            raise ValueError("incomplete responses require coverage issues")
        if self.total is None and (self.is_complete or not self.coverage_issues):
            raise ValueError("an unavailable total requires incomplete coverage evidence")
        return self


SupportedYear = Literal[2023, 2024, 2025]


class YearComparisonRequest(StrictModel):
    product_id: ProductId
    province_code: ProvinceCode
    years: list[SupportedYear] = Field(min_length=2, max_length=3)

    @model_validator(mode="after")
    def years_are_ordered_and_distinct(self) -> "YearComparisonRequest":
        if self.years != sorted(set(self.years)):
            raise ValueError("years must be distinct and ascending")
        return self


class YearComparisonPoint(StrictModel):
    year: SupportedYear
    count: int | None = Field(default=None, ge=0)
    is_complete: bool
    coverage_issues: list[CoverageIssue]

    @model_validator(mode="after")
    def coverage_matches_count(self) -> "YearComparisonPoint":
        if self.is_complete and self.coverage_issues:
            raise ValueError("complete years cannot have coverage issues")
        if self.count is None and self.is_complete:
            raise ValueError("a complete year requires a numeric count")
        return self


class YearComparisonResponse(StrictModel):
    request_id: str
    operation_id: Literal["hotspot_year_comparison_v1"] = "hotspot_year_comparison_v1"
    metric: Literal["satellite_hotspot_detections"]
    product_id: str
    province_code: str
    years: list[SupportedYear] = Field(min_length=2, max_length=3)
    points: list[YearComparisonPoint] = Field(min_length=2, max_length=3)
    source: SourceInfo
    caveat: Literal["Hotspot detections are not confirmed wildfires."]

    @model_validator(mode="after")
    def points_match_years(self) -> "YearComparisonResponse":
        if [point.year for point in self.points] != self.years:
            raise ValueError("comparison points must match requested years")
        return self


class GeoJsonQuery(DateRangeModel):
    product_id: ProductId
    province_code: ProvinceCode
    limit: int = Field(default=500, ge=1, le=5_000)


class GeoJsonGeometry(StrictModel):
    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float]

    @model_validator(mode="after")
    def coordinates_are_wgs84(self) -> "GeoJsonGeometry":
        longitude, latitude = self.coordinates
        if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
            raise ValueError("coordinates must be WGS84 longitude/latitude")
        return self


class GeoJsonProperties(StrictModel):
    observation_id: str
    acquired_at_utc: UtcDateTime
    product_id: str
    province_code: str
    confidence_code: Literal["l", "n", "h"]
    frp_mw: float = Field(ge=0)
    daynight_code: Literal["D", "N"]


class GeoJsonFeature(StrictModel):
    type: Literal["Feature"] = "Feature"
    geometry: GeoJsonGeometry
    properties: GeoJsonProperties


class GeoJsonMetadata(StrictModel):
    request_id: str
    product_id: str
    filters: Filters
    truncated: bool
    returned: int = Field(ge=0)
    limit: int = Field(ge=1, le=5_000)
    is_complete: bool
    coverage_issues: list[CoverageIssue]
    source: SourceInfo
    caveat: Literal["Hotspot detections are not confirmed wildfires."]

    @model_validator(mode="after")
    def completeness_matches_issues(self) -> "GeoJsonMetadata":
        if self.is_complete and self.coverage_issues:
            raise ValueError("complete map responses cannot have coverage issues")
        return self


class GeoJsonResponse(StrictModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[GeoJsonFeature]
    metadata: GeoJsonMetadata

    @model_validator(mode="after")
    def returned_matches_features(self) -> "GeoJsonResponse":
        if self.metadata.returned != len(self.features):
            raise ValueError("metadata.returned must match feature count")
        return self
