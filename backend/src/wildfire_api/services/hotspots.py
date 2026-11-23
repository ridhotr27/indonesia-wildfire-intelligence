from calendar import monthrange
from dataclasses import asdict
from datetime import date, timedelta

from wildfire_api.contracts.api_v1_2_proposal import (
    MultiProvinceParameters,
    ProvinceAnalytics,
    ProvinceAnalyticsExecution,
    ProvinceBreakdownResult,
    ProvinceComparison,
    ProvinceCountRow,
    ProvinceRankingParameters,
    ProvinceRankingResult,
    ProvinceRankRow,
    TopNSelection,
)
from wildfire_api.core.errors import invalid_filter
from wildfire_api.repositories.hotspots import CoverageRecord, HotspotRepository, RepositoryMetadata
from wildfire_api.schemas.common import CoverageIssue, Filters, SourceInfo
from wildfire_api.schemas.hotspots import (
    GeoJsonFeature,
    GeoJsonGeometry,
    GeoJsonMetadata,
    GeoJsonProperties,
    GeoJsonQuery,
    GeoJsonResponse,
    SummaryPoint,
    SummaryRequest,
    SummaryResponse,
    YearComparisonPoint,
    YearComparisonRequest,
    YearComparisonResponse,
)
from wildfire_api.schemas.metadata import (
    CoverageWindow,
    MetadataResponse,
    ProductMetadata,
    ProvinceMetadata,
)

CAVEAT = "Hotspot detections are not confirmed wildfires."


class HotspotService:
    def __init__(self, repository: HotspotRepository, max_date_range_days: int, max_features: int):
        self._repository = repository
        self._max_date_range_days = max_date_range_days
        self._max_features = max_features

    async def metadata(self, request_id: str) -> MetadataResponse:
        metadata = await self._repository.metadata()
        return MetadataResponse(
            request_id=request_id,
            products=[ProductMetadata(**asdict(item)) for item in metadata.products],
            provinces=[ProvinceMetadata(**asdict(item)) for item in metadata.provinces],
            coverage=CoverageWindow(
                date_min=metadata.date_min,
                date_max=metadata.date_max,
                known_unavailable_dates=list(metadata.known_unavailable_dates),
            ),
            source=self._source(metadata),
            data_freshness_at=metadata.data_freshness,
            data_status=metadata.data_status,
        )

    async def summary(self, request: SummaryRequest, request_id: str) -> SummaryResponse:
        metadata = await self._validate_scope(
            request.product_id, tuple(request.province_codes), request.date_from, request.date_to
        )
        raw_series = await self._repository.count_by_month(
            product_id=request.product_id,
            province_codes=tuple(request.province_codes),
            date_from=request.date_from,
            date_to=request.date_to,
        )
        coverage = await self._repository.coverage(
            product_id=request.product_id,
            date_from=request.date_from,
            date_to=request.date_to,
        )
        coverage_by_date = self._complete_coverage(coverage, request.date_from, request.date_to)
        periods = self._month_periods(request.date_from, request.date_to)
        series: list[SummaryPoint] = []
        for period in periods:
            period_coverage = [
                row for day, row in coverage_by_date.items() if day.strftime("%Y-%m") == period
            ]
            issues = self._coverage_issues(period_coverage)
            has_available_day = any(self._is_available(row) for row in period_coverage)
            series.append(
                SummaryPoint(
                    period=period,
                    count=raw_series.get(period, 0) if has_available_day else None,
                    is_complete=not issues,
                    coverage_issues=issues,
                )
            )
        issues = self._coverage_issues(list(coverage_by_date.values()))
        available_points = [point for point in series if point.count is not None]
        return SummaryResponse(
            request_id=request_id,
            metric="satellite_hotspot_detections",
            product_id=request.product_id,
            filters=Filters(
                province_codes=request.province_codes,
                date_from=request.date_from,
                date_to=request.date_to,
            ),
            total=sum(point.count or 0 for point in available_points) if available_points else None,
            is_complete=not issues,
            coverage_issues=issues,
            warnings=(
                ["Result excludes dates with unavailable or unknown satellite coverage."]
                if issues
                else []
            ),
            series=series,
            source=self._source(metadata),
            caveat=CAVEAT,
        )

    async def geojson(self, query: GeoJsonQuery, request_id: str) -> GeoJsonResponse:
        metadata = await self._validate_scope(
            query.product_id, (query.province_code,), query.date_from, query.date_to
        )
        effective_limit = min(query.limit, self._max_features)
        coverage = await self._repository.coverage(
            product_id=query.product_id,
            date_from=query.date_from,
            date_to=query.date_to,
        )
        coverage_by_date = self._complete_coverage(coverage, query.date_from, query.date_to)
        issues = self._coverage_issues(list(coverage_by_date.values()))
        observations, truncated = await self._repository.observations(
            product_id=query.product_id,
            province_code=query.province_code,
            date_from=query.date_from,
            date_to=query.date_to,
            limit=effective_limit,
        )
        features = [
            GeoJsonFeature(
                geometry=GeoJsonGeometry(coordinates=(item.longitude, item.latitude)),
                properties=GeoJsonProperties(
                    observation_id=item.observation_id,
                    acquired_at_utc=item.acquired_at_utc.isoformat().replace("+00:00", "Z"),
                    product_id=item.product_id,
                    province_code=item.province_code,
                    confidence_code=item.confidence_code,
                    frp_mw=item.frp_mw,
                    daynight_code=item.daynight_code,
                ),
            )
            for item in observations
        ]
        return GeoJsonResponse(
            features=features,
            metadata=GeoJsonMetadata(
                request_id=request_id,
                product_id=query.product_id,
                filters=Filters(
                    province_codes=[query.province_code],
                    date_from=query.date_from,
                    date_to=query.date_to,
                ),
                truncated=truncated,
                returned=len(features),
                limit=effective_limit,
                is_complete=not issues,
                coverage_issues=issues,
                source=self._source(metadata),
                caveat=CAVEAT,
            ),
        )

    async def year_comparison(
        self, request: YearComparisonRequest, request_id: str
    ) -> YearComparisonResponse:
        date_from = date(request.years[0], 1, 1)
        date_to = date(request.years[-1], 12, 31)
        metadata = await self._validate_scope(
            request.product_id,
            (request.province_code,),
            date_from,
            date_to,
            enforce_range_limit=False,
        )
        counts = await self._repository.count_by_year(
            product_id=request.product_id,
            province_code=request.province_code,
            years=tuple(request.years),
        )
        coverage = await self._repository.coverage(
            product_id=request.product_id,
            date_from=date_from,
            date_to=date_to,
        )
        completed = self._complete_coverage(coverage, date_from, date_to)
        points: list[YearComparisonPoint] = []
        for year in request.years:
            year_coverage = [row for day, row in completed.items() if day.year == year]
            issues = self._coverage_issues(year_coverage)
            available = any(self._is_available(row) for row in year_coverage)
            points.append(
                YearComparisonPoint(
                    year=year,
                    count=counts.get(year, 0) if available else None,
                    is_complete=not issues,
                    coverage_issues=issues,
                )
            )
        return YearComparisonResponse(
            request_id=request_id,
            metric="satellite_hotspot_detections",
            product_id=request.product_id,
            province_code=request.province_code,
            years=request.years,
            points=points,
            source=self._source(metadata),
            caveat=CAVEAT,
        )

    async def province_analytics(
        self,
        *,
        product_id: str,
        province_codes: tuple[str, ...],
        date_from: date,
        date_to: date,
        ranking: bool,
        direction: str = "highest",
        top_n: int = 1,
        comparison_requested: bool = False,
    ) -> ProvinceAnalytics:
        if not ranking and len(province_codes) < 2:
            raise invalid_filter("Multi-province analytics requires at least two provinces")
        metadata = await self._validate_scope(product_id, province_codes, date_from, date_to)
        records, excluded = await self._repository.count_by_province(
            product_id=product_id,
            province_codes=() if ranking else province_codes,
            date_from=date_from,
            date_to=date_to,
        )
        coverage = await self._repository.coverage(
            product_id=product_id, date_from=date_from, date_to=date_to
        )
        completed = self._complete_coverage(coverage, date_from, date_to)
        issues = self._coverage_issues(list(completed.values()))
        available = any(self._is_available(row) for row in completed.values())
        state = "unavailable" if not available else ("partial" if issues else "complete")
        source = self._source(metadata)
        if not ranking:
            records_by_code = {row.province_code: row for row in records}
            records = tuple(records_by_code[code] for code in province_codes)
            count_rows = [
                ProvinceCountRow(
                    province_code=row.province_code,
                    province_name=row.province_name,
                    province_order=row.province_order,
                    count=row.detection_count if available else None,
                )
                for row in records
            ]
            counts = [row.detection_count for row in records]
            comparison = None
            if comparison_requested and available:
                comparison = ProvinceComparison(
                    highest_province_codes=[
                        row.province_code for row in records if row.detection_count == max(counts)
                    ],
                    lowest_province_codes=[
                        row.province_code for row in records if row.detection_count == min(counts)
                    ],
                    max_min_difference=max(counts) - min(counts),
                )
            result = ProvinceBreakdownResult(
                kind="province_breakdown",
                metric="satellite_hotspot_detections",
                product_id=product_id,
                date_from=date_from,
                date_to=date_to,
                source=source,
                coverage_state=state,
                is_complete=not issues,
                coverage_issues=issues,
                not_assigned_to_exactly_one_province_count=excluded if available else None,
                requested_province_codes=list(province_codes),
                total=sum(counts) if available else None,
                rows=count_rows,
                comparison=comparison,
            )
            params = MultiProvinceParameters(
                kind="multi_province_summary",
                product_id=product_id,
                province_codes=list(province_codes),
                date_from=date_from,
                date_to=date_to,
                comparison_requested=comparison_requested,
            )
            operation_id = "hotspot_multi_province_summary_v1"
            metric_value = result.total
        else:
            reverse = direction == "highest"
            ordered = sorted(
                records,
                key=lambda row: (
                    (-row.detection_count) if reverse else row.detection_count,
                    row.province_order,
                ),
            )
            rank = 0
            previous = None
            ranked = []
            for row in ordered:
                if previous is None or row.detection_count != previous:
                    rank += 1
                    previous = row.detection_count
                if rank <= top_n:
                    ranked.append(
                        ProvinceRankRow(
                            province_code=row.province_code,
                            province_name=row.province_name,
                            province_order=row.province_order,
                            count=row.detection_count,
                            dense_rank=rank,
                        )
                    )
            if not available:
                ranked = []
            selection = TopNSelection(kind="top_n", top_n=top_n)
            result = ProvinceRankingResult(
                kind="province_ranking",
                metric="satellite_hotspot_detections",
                product_id=product_id,
                date_from=date_from,
                date_to=date_to,
                source=source,
                coverage_state=state,
                is_complete=not issues,
                coverage_issues=issues,
                not_assigned_to_exactly_one_province_count=excluded if available else None,
                direction=direction,
                selection=selection,
                selection_complete=True,
                rows=ranked,
                cutoff_tie_count=(
                    sum(row.dense_rank == ranked[-1].dense_rank for row in ranked)
                    if ranked
                    else None
                ),
            )
            params = ProvinceRankingParameters(
                kind="province_ranking",
                product_id=product_id,
                date_from=date_from,
                date_to=date_to,
                direction=direction,
                selection=selection,
            )
            operation_id = "hotspot_province_ranking_v1"
            metric_value = ranked[0].count if ranked else None
        return ProvinceAnalytics(
            result=result,
            execution=ProvinceAnalyticsExecution(
                operation_id=operation_id,
                parameters=params,
                read_only=True,
                parameterized=True,
                returned_rows=len(result.rows),
                metric_name="satellite_hotspot_detections",
                metric_value=metric_value,
            ),
        )

    async def validate_product(self, product_id: str) -> None:
        metadata = await self._repository.metadata()
        if product_id not in {item.product_id for item in metadata.products}:
            raise invalid_filter(f"Unsupported product_id: {product_id}")

    async def _validate_scope(
        self,
        product_id: str,
        province_codes: tuple[str, ...],
        date_from: date,
        date_to: date,
        enforce_range_limit: bool = True,
    ) -> RepositoryMetadata:
        metadata = await self._repository.metadata()
        if product_id not in {item.product_id for item in metadata.products}:
            raise invalid_filter(f"Unsupported product_id: {product_id}")
        supported_provinces = {item.province_code for item in metadata.provinces}
        unknown = sorted(set(province_codes) - supported_provinces)
        if unknown:
            raise invalid_filter(f"Unsupported province_codes: {', '.join(unknown)}")
        if enforce_range_limit and (date_to - date_from).days + 1 > self._max_date_range_days:
            raise invalid_filter(f"Date range exceeds {self._max_date_range_days} days")
        if date_from < metadata.date_min or date_to > metadata.date_max:
            raise invalid_filter(
                f"Dates must be within {metadata.date_min.isoformat()} and "
                f"{metadata.date_max.isoformat()}"
            )
        return metadata

    @staticmethod
    def _source(metadata: RepositoryMetadata) -> SourceInfo:
        return SourceInfo(
            provider="Synthetic fixture" if metadata.data_status == "mock" else "NASA FIRMS",
            dataset_version=metadata.dataset_version,
            data_status=metadata.data_status,
            url=metadata.source_url,
            attribution=metadata.source_attribution,
        )

    @staticmethod
    def _month_periods(date_from: date, date_to: date) -> list[str]:
        periods: list[str] = []
        current = date(date_from.year, date_from.month, 1)
        while current <= date_to:
            periods.append(current.strftime("%Y-%m"))
            _, last_day = monthrange(current.year, current.month)
            current = current.replace(day=last_day) + timedelta(days=1)
        return periods

    @staticmethod
    def _complete_coverage(
        rows: tuple[CoverageRecord, ...], date_from: date, date_to: date
    ) -> dict[date, CoverageRecord]:
        by_date = {row.date_utc: row for row in rows}
        current = date_from
        while current <= date_to:
            by_date.setdefault(
                current,
                CoverageRecord(
                    date_utc=current,
                    coverage_status="unknown",
                    observation_count=None,
                    evidence_url=None,
                    note="No published coverage record is available for this date.",
                ),
            )
            current += timedelta(days=1)
        return dict(sorted(by_date.items()))

    @staticmethod
    def _is_available(row: CoverageRecord) -> bool:
        return row.coverage_status in {"observations_present", "zero_detections_verified"}

    @staticmethod
    def _coverage_issues(rows: list[CoverageRecord]) -> list[CoverageIssue]:
        return [
            CoverageIssue(
                date_utc=row.date_utc,
                coverage_status=row.coverage_status,
                evidence_url=row.evidence_url,
                note=row.note,
            )
            for row in rows
            if row.coverage_status in {"known_satellite_gap", "unknown"}
        ]
