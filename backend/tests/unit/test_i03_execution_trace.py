from datetime import date

import pytest

from wildfire_api.agent.runtime import BoundedLangGraphRuntime
from wildfire_api.agent.state import AnalyticsToolInput, RetrievalToolInput
from wildfire_api.rag.models import RetrievedPassage
from wildfire_api.schemas.common import Filters, SourceInfo
from wildfire_api.schemas.hotspots import SummaryPoint, SummaryResponse


def _state(message: str) -> dict[str, object]:
    return {
        "request_id": "i03-test",
        "message": message,
        "product_id": "VNP14IMG.002_SNPP_FIRMS_SP",
        "province_code": "14",
        "date_from": date(2023, 1, 1),
        "date_to": date(2023, 12, 31),
    }


def _summary(tool_input: AnalyticsToolInput) -> SummaryResponse:
    return SummaryResponse(
        request_id="i03-test",
        metric="satellite_hotspot_detections",
        product_id=tool_input.product_id,
        filters=Filters(
            province_codes=[tool_input.province_code],
            date_from=tool_input.date_from,
            date_to=tool_input.date_to,
        ),
        total=12,
        is_complete=True,
        coverage_issues=[],
        warnings=[],
        series=[SummaryPoint(period="2023-09", count=12, is_complete=True, coverage_issues=[])],
        source=SourceInfo(
            provider="NASA FIRMS",
            dataset_version="VNP14IMG.002",
            data_status="verified",
            url="https://firms.modaps.eosdis.nasa.gov/",
            attribution="NASA FIRMS",
        ),
        caveat="Hotspot detections are not confirmed wildfires.",
    )


def _passage() -> RetrievedPassage:
    return RetrievedPassage(
        chunk_id="b" * 64,
        document_id="nasa-frp",
        title="NASA FIRMS attributes",
        url="https://www.earthdata.nasa.gov/data/tools/firms",
        section="FRP",
        text="Untrusted passage body that must never enter the trace.",
        content_hash="a" * 64,
        retrieved_at="2026-10-21T00:00:00Z",
        untrusted_content=True,
    )


@pytest.mark.asyncio
async def test_trace_uses_exact_b10_input_and_does_not_repeat_dependency_calls() -> None:
    analytics_calls: list[AnalyticsToolInput] = []
    retrieval_calls: list[RetrievalToolInput] = []

    async def analytics(tool_input: AnalyticsToolInput, _: str) -> SummaryResponse:
        analytics_calls.append(tool_input)
        return _summary(tool_input)

    async def retrieve(tool_input: RetrievalToolInput) -> list[RetrievedPassage]:
        retrieval_calls.append(tool_input)
        return [_passage()]

    runtime = BoundedLangGraphRuntime(
        analytics_tool=analytics,
        retrieval_tool=retrieve,
        embedding_model="all-minilm",
        retrieval_collection="nasa-firms-docs",
    )
    result = await runtime.invoke(
        _state("How many hotspots in Sumatera Barat in September 2023 and what is FRP?")
    )
    response = result["response"]
    trace = response.execution_trace

    assert len(analytics_calls) == len(retrieval_calls) == 1
    assert trace is not None and trace.route == response.mode == "combined"
    assert [step.sequence for step in trace.steps] == list(range(1, len(trace.steps) + 1))
    analytics_step = next(step for step in trace.steps if step.kind == "analytics_query")
    assert analytics_step.details.parameters.model_dump() == response.filters.model_dump()
    assert analytics_step.details.parameters.province_codes == ["13"]
    assert analytics_step.details.parameters.date_from == date(2023, 9, 1)
    assert analytics_step.details.parameters.date_to == date(2023, 9, 30)
    assert analytics_step.details.operation_id == "hotspot_summary_v1"
    assert analytics_step.details.read_only is True
    assert all(step.duration_ms is None or step.duration_ms >= 0 for step in trace.steps)


@pytest.mark.asyncio
async def test_trace_contains_only_safe_retrieval_metadata_and_no_passage_body() -> None:
    async def analytics(tool_input: AnalyticsToolInput, _: str) -> SummaryResponse:
        return _summary(tool_input)

    async def retrieve(_: RetrievalToolInput) -> list[RetrievedPassage]:
        return [_passage()]

    runtime = BoundedLangGraphRuntime(analytics_tool=analytics, retrieval_tool=retrieve)
    response = (await runtime.invoke(_state("What does FRP mean?")))["response"]
    serialized = response.execution_trace.model_dump_json()

    assert "Untrusted passage body" not in serialized
    for forbidden in ("SELECT ", "prompt", "credential", "127.0.0.1", "/Users/"):
        assert forbidden.casefold() not in serialized.casefold()
    assert "https://www.earthdata.nasa.gov/data/tools/firms" in serialized


@pytest.mark.asyncio
async def test_unsupported_trace_abstains_and_executes_no_dependencies() -> None:
    async def forbidden_analytics(_: AnalyticsToolInput, __: str) -> SummaryResponse:
        raise AssertionError("analytics must not execute")

    async def forbidden_retrieval(_: RetrievalToolInput) -> list[RetrievedPassage]:
        raise AssertionError("retrieval must not execute")

    runtime = BoundedLangGraphRuntime(
        analytics_tool=forbidden_analytics, retrieval_tool=forbidden_retrieval
    )
    response = (await runtime.invoke(_state("How many hectares burned?")))["response"]

    assert response.execution_trace is not None
    assert response.execution_trace.status == "abstained"
    assert [step.kind for step in response.execution_trace.steps] == [
        "route_selection",
        "abstention",
    ]
    assert response.usage.llm_calls == 0


@pytest.mark.asyncio
async def test_missing_filters_trace_reports_safe_clarification_without_query() -> None:
    calls = 0

    async def forbidden_analytics(_: AnalyticsToolInput, __: str) -> SummaryResponse:
        nonlocal calls
        calls += 1
        raise AssertionError("analytics must not execute")

    runtime = BoundedLangGraphRuntime(analytics_tool=forbidden_analytics, retrieval_tool=None)
    state = _state("How many hotspot detections?")
    state.update(province_code=None, date_from=None, date_to=None)
    response = (await runtime.invoke(state))["response"]

    assert calls == 0
    trace = response.execution_trace
    assert trace is not None and trace.status == "abstained"
    resolution = next(step for step in trace.steps if step.kind == "filter_resolution")
    assert resolution.status == "abstained"
    assert resolution.details.reason_codes == ["missing_province", "missing_date_range"]
