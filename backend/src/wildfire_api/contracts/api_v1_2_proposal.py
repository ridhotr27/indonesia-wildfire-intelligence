"""A03 API v1.2.0 proposal models.

These models are contract-review artifacts. Runtime chat behavior continues to use
``wildfire_api.schemas.chat.ChatResponse`` until A03 is approved and B13 starts.
"""

from datetime import date
from ipaddress import ip_address
from typing import Annotated, Literal

from pydantic import Field, model_validator

from wildfire_api.schemas.chat import ChatResponse
from wildfire_api.schemas.common import CoverageIssue, SourceInfo, StrictModel
from wildfire_api.schemas.hotspots import ProductId

MetricName = Literal["satellite_hotspot_detections"]
CoverageState = Literal["complete", "partial", "unavailable"]
RankingDirection = Literal["highest", "lowest"]
MAX_SAFE_INTEGER = 9_007_199_254_740_991
A03ProvinceCode = Annotated[
    str,
    Field(min_length=2, max_length=2, pattern=r"^\d{2}$"),
]


def _is_safe_public_https_url(value: object) -> bool:
    """Reject local/numeric/root-like hosts in proposal provenance URLs."""
    scheme = getattr(value, "scheme", None)
    host = getattr(value, "host", None)
    username = getattr(value, "username", None)
    password = getattr(value, "password", None)
    if (
        scheme != "https"
        or not isinstance(host, str)
        or not host
        or username is not None
        or password is not None
        or host.endswith(".")
        or ".." in host
    ):
        return False
    unbracketed_host = host[1:-1] if host.startswith("[") and host.endswith("]") else host
    lowered_host = unbracketed_host.lower()
    if (
        lowered_host in {"localhost", "local"}
        or lowered_host.endswith(".localhost")
        or lowered_host.endswith(".local")
    ):
        return False
    try:
        ip_address(unbracketed_host)
    except ValueError:
        return True
    return False


class ProvinceResultBase(StrictModel):
    metric: MetricName
    product_id: ProductId
    date_from: date
    date_to: date
    source: SourceInfo
    coverage_state: CoverageState
    is_complete: bool
    coverage_issues: list[CoverageIssue] = Field(max_length=366)
    not_assigned_to_exactly_one_province_count: int | None = Field(ge=0, le=MAX_SAFE_INTEGER)

    @model_validator(mode="after")
    def coverage_is_consistent(self) -> "ProvinceResultBase":
        if not _is_safe_public_https_url(self.source.url):
            raise ValueError("source URL must use an approved public HTTPS hostname")
        if any(
            issue.evidence_url is not None and not _is_safe_public_https_url(issue.evidence_url)
            for issue in self.coverage_issues
        ):
            raise ValueError("coverage evidence URL must use a public HTTPS hostname")
        if self.date_to < self.date_from:
            raise ValueError("date_to must be on or after date_from")
        issue_dates = [issue.date_utc for issue in self.coverage_issues]
        requested_days = (self.date_to - self.date_from).days + 1
        if len(issue_dates) != len(set(issue_dates)) or any(
            issue_date < self.date_from or issue_date > self.date_to for issue_date in issue_dates
        ):
            raise ValueError("coverage issue dates must be unique and inside the requested range")
        if self.coverage_state == "complete":
            if not self.is_complete or self.coverage_issues:
                raise ValueError("complete results require no coverage issues")
        elif self.coverage_state == "partial":
            if self.is_complete or not 0 < len(self.coverage_issues) < requested_days:
                raise ValueError("partial results require coverage issues")
        else:
            if self.is_complete or len(self.coverage_issues) != requested_days:
                raise ValueError("unavailable results require coverage issues")
            if self.not_assigned_to_exactly_one_province_count is not None:
                raise ValueError("unavailable results cannot report an exclusion count")
        return self


class ProvinceCountRow(StrictModel):
    province_code: A03ProvinceCode
    province_name: str = Field(min_length=1, max_length=100)
    province_order: int = Field(ge=1, le=38)
    count: int | None = Field(ge=0, le=MAX_SAFE_INTEGER)


class ProvinceRankRow(StrictModel):
    province_code: A03ProvinceCode
    province_name: str = Field(min_length=1, max_length=100)
    province_order: int = Field(ge=1, le=38)
    count: int = Field(ge=0, le=MAX_SAFE_INTEGER)
    dense_rank: int = Field(ge=1, le=38)


class ProvinceComparison(StrictModel):
    highest_province_codes: list[A03ProvinceCode] = Field(min_length=1, max_length=38)
    lowest_province_codes: list[A03ProvinceCode] = Field(min_length=1, max_length=38)
    max_min_difference: int = Field(ge=0, le=MAX_SAFE_INTEGER)


class ProvinceBreakdownResult(ProvinceResultBase):
    kind: Literal["province_breakdown"]
    requested_province_codes: list[A03ProvinceCode] = Field(min_length=2, max_length=38)
    total: int | None = Field(ge=0, le=MAX_SAFE_INTEGER)
    rows: list[ProvinceCountRow] = Field(min_length=2, max_length=38)
    comparison: ProvinceComparison | None

    @model_validator(mode="after")
    def breakdown_is_consistent(self) -> "ProvinceBreakdownResult":
        codes = [row.province_code for row in self.rows]
        if len(self.requested_province_codes) != len(set(self.requested_province_codes)):
            raise ValueError("requested province codes must be unique")
        if codes != self.requested_province_codes or len(codes) != len(set(codes)):
            raise ValueError("breakdown rows must uniquely follow requested province order")
        if len({row.province_order for row in self.rows}) != len(self.rows):
            raise ValueError("province_order values must be unique")
        counts = [row.count for row in self.rows]
        if self.coverage_state == "unavailable":
            if self.total is not None or any(count is not None for count in counts):
                raise ValueError("unavailable breakdowns require null total and row counts")
            if self.comparison is not None:
                raise ValueError("unavailable breakdowns cannot compare values")
            return self
        if any(count is None for count in counts):
            raise ValueError("complete or partial breakdown rows require numeric counts")
        numeric = [count for count in counts if count is not None]
        if self.total != sum(numeric):
            raise ValueError("breakdown total must equal the province row sum")
        if self.comparison is not None:
            highest = max(numeric)
            lowest = min(numeric)
            expected_high = [row.province_code for row in self.rows if row.count == highest]
            expected_low = [row.province_code for row in self.rows if row.count == lowest]
            if self.comparison.highest_province_codes != expected_high:
                raise ValueError("comparison highest provinces must match rows")
            if self.comparison.lowest_province_codes != expected_low:
                raise ValueError("comparison lowest provinces must match rows")
            if self.comparison.max_min_difference != highest - lowest:
                raise ValueError("comparison difference must match rows")
        return self


class TopNSelection(StrictModel):
    kind: Literal["top_n"]
    top_n: int = Field(ge=1, le=38)


class OrdinalSelection(StrictModel):
    kind: Literal["ordinal"]
    dense_rank: int = Field(ge=1, le=38)


class RankLookupSelection(StrictModel):
    kind: Literal["rank_lookup"]
    province_code: A03ProvinceCode


class AllProvincesSelection(StrictModel):
    kind: Literal["all"]


class ZeroCountSelection(StrictModel):
    kind: Literal["zero_count"]


RankingSelection = Annotated[
    TopNSelection
    | OrdinalSelection
    | RankLookupSelection
    | AllProvincesSelection
    | ZeroCountSelection,
    Field(discriminator="kind"),
]


class ProvinceRankingResult(ProvinceResultBase):
    kind: Literal["province_ranking"]
    direction: RankingDirection
    selection: RankingSelection
    universe_size: Literal[38] = 38
    tie_policy: Literal["dense_rank_include_cutoff_ties"] = "dense_rank_include_cutoff_ties"
    selection_complete: Literal[True]
    cutoff_tie_count: int | None = Field(ge=1, le=38)
    rows: list[ProvinceRankRow] = Field(max_length=38)

    @model_validator(mode="after")
    def ranking_is_consistent(self) -> "ProvinceRankingResult":
        if isinstance(self.selection, ZeroCountSelection) and self.direction != "lowest":
            raise ValueError("zero-count selection requires lowest direction")
        if self.coverage_state == "unavailable":
            if self.rows:
                raise ValueError("unavailable rankings cannot contain rows")
            if self.cutoff_tie_count is not None:
                raise ValueError("unavailable rankings cannot report cutoff ties")
            return self
        codes = [row.province_code for row in self.rows]
        if len(codes) != len(set(codes)):
            raise ValueError("ranking province codes must be unique")
        if len({row.province_order for row in self.rows}) != len(self.rows):
            raise ValueError("ranking province_order values must be unique")
        expected = sorted(
            self.rows,
            key=lambda row: (
                -row.count if self.direction == "highest" else row.count,
                row.province_order,
            ),
        )
        if self.rows != expected:
            raise ValueError("ranking rows must follow direction and canonical tie order")
        for previous, current in zip(self.rows, self.rows[1:], strict=False):
            if previous.count == current.count and previous.dense_rank != current.dense_rank:
                raise ValueError("equal counts must share a dense rank")
            if previous.count != current.count and previous.dense_rank >= current.dense_rank:
                raise ValueError("different ordered counts must increase dense rank")
            if previous.count != current.count and current.dense_rank != previous.dense_rank + 1:
                raise ValueError("dense ranks cannot contain gaps within returned ordered rows")
        selection = self.selection
        if isinstance(selection, TopNSelection):
            if not self.rows:
                raise ValueError("available top_n rankings require at least one province")
            if self.rows[0].dense_rank != 1:
                raise ValueError("top_n results must begin at dense rank one")
            if any(row.dense_rank > selection.top_n for row in self.rows):
                raise ValueError("top_n is a dense-rank cutoff")
            last_rank = self.rows[-1].dense_rank
            if len(self.rows) < self.universe_size and last_rank != selection.top_n:
                raise ValueError(
                    "top_n must reach its dense-rank cutoff unless universe is exhausted"
                )
            expected_ties = sum(row.dense_rank == last_rank for row in self.rows)
            if self.cutoff_tie_count != expected_ties:
                raise ValueError("cutoff_tie_count must prove every cutoff tie is returned")
        elif isinstance(selection, OrdinalSelection):
            if any(row.dense_rank != selection.dense_rank for row in self.rows):
                raise ValueError("ordinal results contain only the requested dense rank")
            expected_ordinal_ties = len(self.rows) or None
            if self.cutoff_tie_count != expected_ordinal_ties:
                raise ValueError("ordinal results require every tied row")
        elif isinstance(selection, RankLookupSelection):
            if self.cutoff_tie_count is not None:
                raise ValueError("rank lookup has no cutoff tie count")
            if len(self.rows) != 1 or self.rows[0].province_code != selection.province_code:
                raise ValueError("rank lookup must return exactly the requested province")
        elif isinstance(selection, AllProvincesSelection):
            if self.cutoff_tie_count is not None:
                raise ValueError("all-province ranking has no cutoff tie count")
            if len(self.rows) != self.universe_size:
                raise ValueError("all-province ranking must return the full universe")
            if self.rows[0].dense_rank != 1:
                raise ValueError("all-province ranking must begin at dense rank one")
        elif isinstance(selection, ZeroCountSelection):
            expected_zero_ties = len(self.rows) or None
            if self.cutoff_tie_count != expected_zero_ties:
                raise ValueError("zero-count selection requires every zero-count province")
            if any(row.count != 0 or row.dense_rank != 1 for row in self.rows):
                raise ValueError("zero-count rows must be covered zeroes at dense rank one")
        return self


ProvinceAnalyticsResult = Annotated[
    ProvinceBreakdownResult | ProvinceRankingResult,
    Field(discriminator="kind"),
]


class MultiProvinceParameters(StrictModel):
    kind: Literal["multi_province_summary"]
    product_id: ProductId
    province_codes: list[A03ProvinceCode] = Field(min_length=2, max_length=38)
    date_from: date
    date_to: date
    comparison_requested: bool

    @model_validator(mode="after")
    def filters_are_valid(self) -> "MultiProvinceParameters":
        if self.date_to < self.date_from:
            raise ValueError("date_to must be on or after date_from")
        if len(self.province_codes) != len(set(self.province_codes)):
            raise ValueError("province_codes must be unique")
        return self


class ProvinceRankingParameters(StrictModel):
    kind: Literal["province_ranking"]
    product_id: ProductId
    date_from: date
    date_to: date
    direction: RankingDirection
    selection: RankingSelection

    @model_validator(mode="after")
    def dates_are_ordered(self) -> "ProvinceRankingParameters":
        if self.date_to < self.date_from:
            raise ValueError("date_to must be on or after date_from")
        return self


ProvinceAnalyticsParameters = Annotated[
    MultiProvinceParameters | ProvinceRankingParameters,
    Field(discriminator="kind"),
]


class ProvinceAnalyticsExecution(StrictModel):
    operation_id: Literal["hotspot_multi_province_summary_v1", "hotspot_province_ranking_v1"]
    parameters: ProvinceAnalyticsParameters
    read_only: Literal[True]
    parameterized: Literal[True]
    returned_rows: int = Field(ge=0, le=38)
    metric_name: MetricName
    metric_value: int | None = Field(ge=0, le=MAX_SAFE_INTEGER)


class ProvinceAnalytics(StrictModel):
    result: ProvinceAnalyticsResult
    execution: ProvinceAnalyticsExecution

    @model_validator(mode="after")
    def execution_matches_result(self) -> "ProvinceAnalytics":
        result = self.result
        execution = self.execution
        if execution.returned_rows != len(result.rows):
            raise ValueError("returned_rows must equal province result rows")
        if execution.metric_name != result.metric:
            raise ValueError("execution metric must match result")
        params = execution.parameters
        if params.product_id != result.product_id:
            raise ValueError("execution product must match result")
        if params.date_from != result.date_from or params.date_to != result.date_to:
            raise ValueError("execution dates must match result")
        if isinstance(result, ProvinceBreakdownResult):
            if execution.operation_id != "hotspot_multi_province_summary_v1":
                raise ValueError("breakdown requires the multi-province operation")
            if not isinstance(params, MultiProvinceParameters):
                raise ValueError("breakdown requires multi-province parameters")
            if params.province_codes != result.requested_province_codes:
                raise ValueError("execution province order must match result")
            if result.coverage_state != "unavailable" and params.comparison_requested != (
                result.comparison is not None
            ):
                raise ValueError("comparison request must match comparison result presence")
            if execution.metric_value != result.total:
                raise ValueError("execution metric value must match breakdown total")
        else:
            if execution.operation_id != "hotspot_province_ranking_v1":
                raise ValueError("ranking requires the province-ranking operation")
            if not isinstance(params, ProvinceRankingParameters):
                raise ValueError("ranking requires ranking parameters")
            if params.direction != result.direction or params.selection != result.selection:
                raise ValueError("ranking parameters must match result")
            expected_value = result.rows[0].count if result.rows else None
            if execution.metric_value != expected_value:
                raise ValueError("execution metric value must match the first ranking row")
        return self


class ChatResponseV1_2Proposal(ChatResponse):
    """The only v1.2.0 response addition is this optional bounded object."""

    province_analytics: ProvinceAnalytics | None = None

    @model_validator(mode="after")
    def province_analytics_matches_legacy_fields(self) -> "ChatResponseV1_2Proposal":
        analytics = self.province_analytics
        if analytics is None:
            return self
        if self.mode not in {"analytics", "combined"}:
            raise ValueError("province analytics requires analytics or combined mode")
        if self.execution_trace is not None:
            legacy_analytics_steps = [
                step for step in self.execution_trace.steps if step.kind == "analytics_query"
            ]
            if legacy_analytics_steps:
                raise ValueError(
                    "v1.2 province operations cannot use legacy analytics_query trace details"
                )
            if self.mode != "combined":
                raise ValueError(
                    "legacy execution_trace is retained only for the documentation "
                    "branch of combined mode"
                )
        result = analytics.result
        if self.filters is None:
            raise ValueError("province analytics requires top-level filters")
        if self.filters.date_from != result.date_from or self.filters.date_to != result.date_to:
            raise ValueError("top-level filter dates must match province result")
        expected_codes = (
            result.requested_province_codes if isinstance(result, ProvinceBreakdownResult) else []
        )
        if self.filters.province_codes != expected_codes:
            raise ValueError("ranking uses an empty filter scope; breakdown uses requested codes")
        if self.chart is not None:
            raise ValueError("categorical province analytics must not use monthly chart series")
        expected_metric = (
            result.total
            if isinstance(result, ProvinceBreakdownResult)
            else (result.rows[0].count if result.rows else None)
        )
        if self.metrics is not None:
            matching = [
                metric for metric in self.metrics if metric.name == "satellite_hotspot_detections"
            ]
            if len(matching) != 1 or matching[0].value != expected_metric:
                raise ValueError("top-level analytics metric must match province result")
        if self.usage.llm_calls != 0 and self.mode == "analytics":
            raise ValueError("analytics-only province operations cannot call an LLM")
        return self
