from datetime import date
from typing import Annotated, Literal

from pydantic import Field, model_validator

from wildfire_api.schemas.common import Citation, Filters, StrictModel, Usage
from wildfire_api.schemas.hotspots import (
    GeoJsonFeature,
    ProductId,
    ProvinceCode,
    SummaryPoint,
    SupportedYear,
    YearComparisonResponse,
)


class ChatContext(StrictModel):
    province_code: ProvinceCode | None = None
    date_from: date | None = None
    date_to: date | None = None

    @model_validator(mode="after")
    def dates_are_ordered(self) -> "ChatContext":
        if self.date_from and self.date_to and self.date_to < self.date_from:
            raise ValueError("date_to must be on or after date_from")
        return self


class ChatRequest(StrictModel):
    message: str = Field(min_length=1, max_length=2_000)
    product_id: ProductId
    context: ChatContext


class ChatMetric(StrictModel):
    name: str
    value: int | float | None
    unit: str


class ChatChart(StrictModel):
    type: Literal["line", "bar"]
    title: str
    series: list[SummaryPoint]


class ChatMap(StrictModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[GeoJsonFeature]


TraceRoute = Literal["analytics", "rag", "combined", "unsupported"]
TraceStepStatus = Literal["complete", "abstained", "failed"]
TraceSource = Literal["message", "ui_context", "absent"]


class RouteSelectionDetails(StrictModel):
    kind: Literal["route_selection"] = "route_selection"
    route: TraceRoute


class FilterResolutionDetails(StrictModel):
    kind: Literal["filter_resolution"] = "filter_resolution"
    province_codes: list[ProvinceCode] = Field(max_length=38)
    date_from: date | None
    date_to: date | None
    province_source: TraceSource
    date_from_source: TraceSource
    date_to_source: TraceSource
    reason_codes: list[
        Literal[
            "missing_province",
            "missing_date_range",
            "ambiguous_province",
            "conflicting_province",
            "conflicting_date_range",
            "invalid_date_range",
        ]
    ] = Field(max_length=5)
    outcome: Literal["resolved", "needs_clarification", "invalid", "not_applicable"]


class AnalyticsParameters(StrictModel):
    province_codes: list[ProvinceCode] = Field(min_length=1, max_length=38)
    date_from: date
    date_to: date


class YearComparisonParameters(StrictModel):
    province_code: ProvinceCode
    years: list[SupportedYear] = Field(min_length=2, max_length=3)


class AnalyticsQueryDetails(StrictModel):
    kind: Literal["analytics_query"] = "analytics_query"
    operation_id: Literal[
        "hotspot_summary_v1",
        "hotspot_trend_v1",
        "hotspot_map_v1",
        "hotspot_year_comparison_v1",
    ]
    parameters: AnalyticsParameters | YearComparisonParameters
    read_only: Literal[True]
    returned_rows: int = Field(ge=0, le=5_000)
    metric_name: Literal["satellite_hotspot_detections"] | None = None
    metric_value: int | None = Field(default=None, ge=0)


class RetrievedItem(StrictModel):
    chunk_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=200)
    url: str = Field(pattern=r"^https://", max_length=500)
    rank: int = Field(ge=1, le=5)


class VectorRetrievalDetails(StrictModel):
    kind: Literal["vector_retrieval"] = "vector_retrieval"
    provider: Literal["local"]
    embedding_model: str = Field(min_length=1, max_length=100)
    collection: str = Field(min_length=1, max_length=100)
    top_k: int = Field(ge=1, le=5)
    returned_count: int = Field(ge=0, le=5)
    items: list[RetrievedItem] = Field(max_length=5)

    @model_validator(mode="after")
    def count_matches_items(self) -> "VectorRetrievalDetails":
        if self.returned_count != len(self.items):
            raise ValueError("returned_count must match retrieved item count")
        if [item.rank for item in self.items] != list(range(1, len(self.items) + 1)):
            raise ValueError("retrieved item ranks must be contiguous and ordered")
        return self


class LocalGenerationDetails(StrictModel):
    kind: Literal["local_generation"] = "local_generation"
    provider: Literal["ollama"]
    model: str = Field(min_length=1, max_length=100)
    input_passage_count: int = Field(ge=0, le=5)
    model_calls: int = Field(ge=1, le=2)


class CitationValidationDetails(StrictModel):
    kind: Literal["citation_validation"] = "citation_validation"
    candidate_count: int = Field(ge=0, le=5)
    accepted_count: int = Field(ge=0, le=5)
    outcome: Literal["passed", "abstained", "failed"]

    @model_validator(mode="after")
    def accepted_does_not_exceed_candidates(self) -> "CitationValidationDetails":
        if self.accepted_count > self.candidate_count:
            raise ValueError("accepted citations cannot exceed candidates")
        return self


class AbstentionDetails(StrictModel):
    kind: Literal["abstention"] = "abstention"
    reason_code: Literal[
        "missing_province", "missing_date_range", "unsupported_intent", "insufficient_evidence"
    ]


TraceDetails = Annotated[
    RouteSelectionDetails
    | FilterResolutionDetails
    | AnalyticsQueryDetails
    | VectorRetrievalDetails
    | LocalGenerationDetails
    | CitationValidationDetails
    | AbstentionDetails,
    Field(discriminator="kind"),
]


class ExecutionTraceStep(StrictModel):
    sequence: int = Field(ge=1, le=8)
    kind: Literal[
        "route_selection",
        "filter_resolution",
        "analytics_query",
        "vector_retrieval",
        "local_generation",
        "citation_validation",
        "abstention",
    ]
    status: TraceStepStatus
    label: str = Field(min_length=1, max_length=200)
    duration_ms: int | None = Field(default=None, ge=0, le=300_000)
    details: TraceDetails

    @model_validator(mode="after")
    def kind_matches_details(self) -> "ExecutionTraceStep":
        if self.kind != self.details.kind:
            raise ValueError("step kind must match details discriminator")
        return self


class ExecutionTrace(StrictModel):
    trace_version: Literal["1.0"] = "1.0"
    route: TraceRoute
    status: Literal["complete", "abstained", "partial"]
    steps: list[ExecutionTraceStep] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def sequences_are_monotonic(self) -> "ExecutionTrace":
        if [step.sequence for step in self.steps] != list(range(1, len(self.steps) + 1)):
            raise ValueError("trace step sequences must be contiguous and monotonic")
        return self


class ChatResponse(StrictModel):
    request_id: str
    answer: str
    mode: Literal["analytics", "rag", "combined", "unsupported"]
    filters: Filters | None
    metrics: list[ChatMetric] | None
    chart: ChatChart | None
    map: ChatMap | None
    citations: list[Citation]
    limitations: list[str]
    usage: Usage
    execution_trace: ExecutionTrace | None = None
    province_analytics: dict[str, object] | None = None
    year_comparison: YearComparisonResponse | None = None

    @model_validator(mode="after")
    def trace_matches_response(self) -> "ChatResponse":
        trace = self.execution_trace
        if trace is None:
            return self
        if trace.route != self.mode:
            raise ValueError("trace route must match response mode")
        analytics = [step.details for step in trace.steps if step.kind == "analytics_query"]
        if analytics and self.filters is None:
            raise ValueError("analytics trace requires top-level filters")
        for details in analytics:
            if isinstance(details, AnalyticsQueryDetails) and self.filters is not None:
                if isinstance(details.parameters, YearComparisonParameters):
                    expected_filters = Filters(
                        province_codes=[details.parameters.province_code],
                        date_from=date(details.parameters.years[0], 1, 1),
                        date_to=date(details.parameters.years[-1], 12, 31),
                    )
                    parameters_match = expected_filters == self.filters
                else:
                    parameters_match = details.parameters.model_dump() == self.filters.model_dump()
                if not parameters_match:
                    raise ValueError("analytics parameters must match top-level filters")
        generations = [step.details for step in trace.steps if step.kind == "local_generation"]
        model_calls = sum(
            details.model_calls
            for details in generations
            if isinstance(details, LocalGenerationDetails)
        )
        if model_calls != self.usage.llm_calls:
            raise ValueError("trace model calls must match usage")
        retrieved_ids = {
            item.chunk_id
            for step in trace.steps
            if isinstance(step.details, VectorRetrievalDetails)
            for item in step.details.items
        }
        if not {citation.chunk_id for citation in self.citations} <= retrieved_ids:
            raise ValueError("citations must be a subset of retrieved trace items")
        return self
