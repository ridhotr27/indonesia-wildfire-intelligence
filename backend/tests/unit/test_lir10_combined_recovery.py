import asyncio
from datetime import date

import pytest

from wildfire_api.agent.runtime import AgentLimits, BoundedLangGraphRuntime
from wildfire_api.agent.state import (
    AnalyticsToolInput,
    ProvinceAnalyticsToolInput,
    RetrievalToolInput,
)
from wildfire_api.contracts.api_v1_2_proposal import ProvinceAnalytics
from wildfire_api.core.errors import AppError
from wildfire_api.llm.ollama import GeneratedAnswer, LocalModelError
from wildfire_api.rag.models import RetrievedPassage
from wildfire_api.schemas.common import CoverageIssue, Filters, SourceInfo
from wildfire_api.schemas.hotspots import SummaryPoint, SummaryResponse

MESSAGE = (
    "How many hotspot detections were recorded in Riau during September 2023, "
    "and what does FRP mean?"
)


def _state(message: str = MESSAGE) -> dict[str, object]:
    return {
        "request_id": "lir10-test",
        "message": message,
        "product_id": "VNP14IMG.002_SNPP_FIRMS_SP",
        "province_code": "14",
        "date_from": date(2023, 9, 1),
        "date_to": date(2023, 9, 30),
    }


def _summary(tool_input: AnalyticsToolInput, total: int | None = 7) -> SummaryResponse:
    coverage_issues = (
        []
        if total is not None
        else [
            CoverageIssue(
                date_utc=date(2023, 9, 1),
                coverage_status="unknown",
                note="Synthetic unavailable-period fixture.",
            )
        ]
    )
    return SummaryResponse(
        request_id="lir10-test",
        metric="satellite_hotspot_detections",
        product_id=tool_input.product_id,
        filters=Filters(
            province_codes=[tool_input.province_code],
            date_from=tool_input.date_from,
            date_to=tool_input.date_to,
        ),
        total=total,
        is_complete=total is not None,
        coverage_issues=coverage_issues,
        warnings=[] if total is not None else ["The requested range is unavailable."],
        series=[
            SummaryPoint(
                period="2023-09",
                count=total,
                is_complete=total is not None,
                coverage_issues=coverage_issues,
            )
        ],
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
        section="frp",
        text="Fire radiative power describes the rate of radiant energy emitted by a fire.",
        content_hash="a" * 64,
        retrieved_at="2026-10-21T00:00:00Z",
        untrusted_content=True,
    )


def _province_ranking(*, coverage_state: str = "complete") -> ProvinceAnalytics:
    issues = (
        []
        if coverage_state == "complete"
        else [
            {
                "date_utc": "2023-09-15",
                "coverage_status": "unknown",
                "evidence_url": None,
                "note": "Synthetic partial-coverage fixture.",
            }
        ]
    )
    return ProvinceAnalytics.model_validate(
        {
            "result": {
                "kind": "province_ranking",
                "metric": "satellite_hotspot_detections",
                "product_id": "VNP14IMG.002_SNPP_FIRMS_SP",
                "date_from": "2023-09-01",
                "date_to": "2023-09-30",
                "source": {
                    "provider": "NASA FIRMS",
                    "dataset_version": "VNP14IMG.002",
                    "data_status": "verified",
                    "url": "https://firms.modaps.eosdis.nasa.gov/",
                    "attribution": "NASA FIRMS",
                },
                "coverage_state": coverage_state,
                "is_complete": coverage_state == "complete",
                "coverage_issues": issues,
                "not_assigned_to_exactly_one_province_count": 3,
                "direction": "highest",
                "selection": {"kind": "top_n", "top_n": 2},
                "selection_complete": True,
                "rows": [
                    {
                        "province_code": "11",
                        "province_name": "Aceh",
                        "province_order": 1,
                        "count": 12,
                        "dense_rank": 1,
                    },
                    {
                        "province_code": "14",
                        "province_name": "Riau",
                        "province_order": 4,
                        "count": 7,
                        "dense_rank": 2,
                    },
                ],
                "cutoff_tie_count": 1,
            },
            "execution": {
                "operation_id": "hotspot_province_ranking_v1",
                "parameters": {
                    "kind": "province_ranking",
                    "product_id": "VNP14IMG.002_SNPP_FIRMS_SP",
                    "date_from": "2023-09-01",
                    "date_to": "2023-09-30",
                    "direction": "highest",
                    "selection": {"kind": "top_n", "top_n": 2},
                },
                "read_only": True,
                "parameterized": True,
                "returned_rows": 2,
                "metric_name": "satellite_hotspot_detections",
                "metric_value": 12,
            },
        }
    )


async def _retrieve(_: RetrievalToolInput) -> list[RetrievedPassage]:
    return [_passage()]


@pytest.mark.asyncio
async def test_combined_success_preserves_exact_analytics_and_supplied_citation() -> None:
    async def analytics(tool_input: AnalyticsToolInput, _: str) -> SummaryResponse:
        return _summary(tool_input)

    async def generate(_: str, passages: list[RetrievedPassage]) -> GeneratedAnswer:
        return GeneratedAnswer(
            answer="NASA documentation defines FRP as the rate of radiant energy emitted by fire.",
            cited_chunk_ids=[passages[0].chunk_id],
        )

    runtime = BoundedLangGraphRuntime(
        analytics_tool=analytics,
        retrieval_tool=_retrieve,
        answer_generator=generate,
    )
    response = (await runtime.invoke(_state()))["response"]

    assert response.mode == "combined"
    assert response.metrics is not None and response.metrics[0].value == 7
    assert response.citations[0].chunk_id == "b" * 64
    assert response.execution_trace is not None
    assert response.execution_trace.status == "complete"


@pytest.mark.asyncio
async def test_analytics_timeout_keeps_rag_evidence_without_generating_a_number() -> None:
    generation_calls = 0

    async def analytics(_: AnalyticsToolInput, __: str) -> SummaryResponse:
        raise TimeoutError

    async def generate(_: str, __: list[RetrievedPassage]) -> GeneratedAnswer:
        nonlocal generation_calls
        generation_calls += 1
        raise AssertionError("generation must not run without a verified analytics result")

    runtime = BoundedLangGraphRuntime(
        analytics_tool=analytics,
        retrieval_tool=_retrieve,
        answer_generator=generate,
    )
    response = (await runtime.invoke(_state()))["response"]

    assert response.mode == "combined"
    assert response.metrics is None
    assert response.citations[0].chunk_id == "b" * 64
    assert "7 hotspot" not in response.answer
    assert generation_calls == 0
    assert response.execution_trace is not None
    assert response.execution_trace.status == "partial"
    assert next(
        step for step in response.execution_trace.steps if step.kind == "analytics_query"
    ).status == "failed"


@pytest.mark.asyncio
async def test_retrieval_timeout_keeps_exact_analytics_without_citations() -> None:
    async def analytics(tool_input: AnalyticsToolInput, _: str) -> SummaryResponse:
        return _summary(tool_input)

    async def retrieve(_: RetrievalToolInput) -> list[RetrievedPassage]:
        raise TimeoutError

    runtime = BoundedLangGraphRuntime(analytics_tool=analytics, retrieval_tool=retrieve)
    response = (await runtime.invoke(_state()))["response"]

    assert response.mode == "combined"
    assert response.metrics is not None and response.metrics[0].value == 7
    assert response.citations == []
    assert "7 satellite hotspot detections" in response.answer
    assert response.execution_trace is not None
    assert response.execution_trace.status == "partial"
    assert next(
        step for step in response.execution_trace.steps if step.kind == "vector_retrieval"
    ).status == "failed"


@pytest.mark.asyncio
async def test_empty_retrieval_keeps_exact_analytics_and_reports_insufficient_evidence() -> None:
    async def analytics(tool_input: AnalyticsToolInput, _: str) -> SummaryResponse:
        return _summary(tool_input)

    async def retrieve(_: RetrievalToolInput) -> list[RetrievedPassage]:
        return []

    runtime = BoundedLangGraphRuntime(analytics_tool=analytics, retrieval_tool=retrieve)
    response = (await runtime.invoke(_state()))["response"]

    assert response.metrics is not None and response.metrics[0].value == 7
    assert response.citations == []
    assert any("No relevant NASA documentation" in item for item in response.limitations)
    assert response.execution_trace is not None
    assert response.execution_trace.status == "partial"


@pytest.mark.asyncio
@pytest.mark.parametrize("total", [0, None])
async def test_combined_preserves_zero_and_unavailable_analytics(total: int | None) -> None:
    async def analytics(tool_input: AnalyticsToolInput, _: str) -> SummaryResponse:
        return _summary(tool_input, total)

    runtime = BoundedLangGraphRuntime(analytics_tool=analytics, retrieval_tool=_retrieve)
    response = (await runtime.invoke(_state()))["response"]

    assert response.metrics is not None and response.metrics[0].value == total
    assert response.citations


@pytest.mark.asyncio
async def test_rejected_generation_cannot_replace_exact_count_or_fabricate_citation() -> None:
    async def analytics(tool_input: AnalyticsToolInput, _: str) -> SummaryResponse:
        return _summary(tool_input)

    async def generate(_: str, __: list[RetrievedPassage]) -> GeneratedAnswer:
        return GeneratedAnswer(
            answer="The analytics result was 999 hotspot detections according to another source.",
            cited_chunk_ids=["c" * 64],
        )

    runtime = BoundedLangGraphRuntime(
        analytics_tool=analytics,
        retrieval_tool=_retrieve,
        answer_generator=generate,
    )
    response = (await runtime.invoke(_state()))["response"]

    assert response.metrics is not None and response.metrics[0].value == 7
    assert "999" not in response.answer
    assert {citation.chunk_id for citation in response.citations} == {"b" * 64}
    assert response.execution_trace is not None
    assert response.execution_trace.status == "partial"
    assert next(
        step for step in response.execution_trace.steps if step.kind == "local_generation"
    ).status == "failed"


@pytest.mark.asyncio
async def test_citation_validator_failure_keeps_only_retrieved_citation() -> None:
    async def analytics(tool_input: AnalyticsToolInput, _: str) -> SummaryResponse:
        return _summary(tool_input)

    async def generate(_: str, __: list[RetrievedPassage]) -> GeneratedAnswer:
        raise LocalModelError("unknown citation")

    runtime = BoundedLangGraphRuntime(
        analytics_tool=analytics,
        retrieval_tool=_retrieve,
        answer_generator=generate,
    )
    response = (await runtime.invoke(_state()))["response"]

    assert response.metrics is not None and response.metrics[0].value == 7
    assert {citation.chunk_id for citation in response.citations} == {"b" * 64}
    assert any("rejected" in limitation for limitation in response.limitations)


@pytest.mark.asyncio
async def test_missing_analytics_filters_still_retrieves_documentation() -> None:
    analytics_calls = 0

    async def analytics(_: AnalyticsToolInput, __: str) -> SummaryResponse:
        nonlocal analytics_calls
        analytics_calls += 1
        raise AssertionError("analytics must not execute without validated filters")

    runtime = BoundedLangGraphRuntime(analytics_tool=analytics, retrieval_tool=_retrieve)
    state = _state("How many hotspot detections were recorded, and what does FRP mean?")
    state.update(province_code=None, date_from=None, date_to=None)
    response = (await runtime.invoke(state))["response"]

    assert analytics_calls == 0
    assert response.mode == "combined"
    assert response.metrics is None
    assert response.citations
    assert any("not executed" in limitation for limitation in response.limitations)


@pytest.mark.asyncio
async def test_internal_retrieval_deadline_preserves_completed_analytics_and_cancels_work() -> None:
    cancelled = asyncio.Event()

    async def analytics(tool_input: AnalyticsToolInput, _: str) -> SummaryResponse:
        return _summary(tool_input)

    async def retrieve(_: RetrievalToolInput) -> list[RetrievedPassage]:
        try:
            await asyncio.sleep(1)
        finally:
            cancelled.set()
        return [_passage()]

    runtime = BoundedLangGraphRuntime(
        analytics_tool=analytics,
        retrieval_tool=retrieve,
        limits=AgentLimits(timeout_seconds=0.1),
    )
    response = (await runtime.invoke(_state()))["response"]

    assert response.metrics is not None and response.metrics[0].value == 7
    assert response.citations == []
    assert cancelled.is_set()
    assert response.execution_trace is not None
    assert response.execution_trace.status == "partial"


@pytest.mark.asyncio
async def test_internal_analytics_deadline_preserves_completed_rag_branch() -> None:
    cancelled = asyncio.Event()

    async def analytics(_: AnalyticsToolInput, __: str) -> SummaryResponse:
        try:
            await asyncio.sleep(1)
        finally:
            cancelled.set()
        raise AssertionError("cancelled analytics must not complete")

    runtime = BoundedLangGraphRuntime(
        analytics_tool=analytics,
        retrieval_tool=_retrieve,
        limits=AgentLimits(timeout_seconds=0.1),
    )
    response = (await runtime.invoke(_state()))["response"]

    assert response.metrics is None
    assert response.citations
    assert cancelled.is_set()
    assert response.execution_trace is not None
    assert response.execution_trace.status == "partial"


@pytest.mark.asyncio
async def test_internal_generation_deadline_preserves_analytics_and_retrieved_sources() -> None:
    cancelled = asyncio.Event()

    async def analytics(tool_input: AnalyticsToolInput, _: str) -> SummaryResponse:
        return _summary(tool_input)

    async def generate(_: str, __: list[RetrievedPassage]) -> GeneratedAnswer:
        try:
            await asyncio.sleep(1)
        finally:
            cancelled.set()
        raise AssertionError("cancelled generation must not complete")

    runtime = BoundedLangGraphRuntime(
        analytics_tool=analytics,
        retrieval_tool=_retrieve,
        answer_generator=generate,
        limits=AgentLimits(timeout_seconds=0.1),
    )
    response = (await runtime.invoke(_state()))["response"]

    assert response.metrics is not None and response.metrics[0].value == 7
    assert {citation.chunk_id for citation in response.citations} == {"b" * 64}
    assert cancelled.is_set()
    assert response.execution_trace is not None
    assert response.execution_trace.status == "partial"


@pytest.mark.asyncio
async def test_combined_stage_budgeting_can_be_reversibly_disabled() -> None:
    async def analytics(tool_input: AnalyticsToolInput, _: str) -> SummaryResponse:
        return _summary(tool_input)

    async def retrieve(_: RetrievalToolInput) -> list[RetrievedPassage]:
        await asyncio.sleep(1)
        return [_passage()]

    runtime = BoundedLangGraphRuntime(
        analytics_tool=analytics,
        retrieval_tool=retrieve,
        limits=AgentLimits(timeout_seconds=0.05, combined_stage_budgeting=False),
    )

    with pytest.raises(AppError) as captured:
        await runtime.invoke(_state())
    assert captured.value.code == "REQUEST_TIMEOUT"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "generated_claim",
    [
        "Riau ranked first and had the most hotspots in the requested period.",
        "Riau recorded more hotspot detections than Aceh in the requested period.",
        "Data coverage was unavailable for the requested period despite the result.",
        "There were no coverage gaps in the requested period.",
    ],
)
async def test_generated_ranking_ordering_and_coverage_claims_are_rejected(
    generated_claim: str,
) -> None:
    async def forbidden_summary(_: AnalyticsToolInput, __: str) -> SummaryResponse:
        raise AssertionError("ranking must use the typed province analytics tool")

    async def province_analytics(
        _: ProvinceAnalyticsToolInput, __: str
    ) -> ProvinceAnalytics:
        return _province_ranking(coverage_state="partial")

    async def generate(_: str, passages: list[RetrievedPassage]) -> GeneratedAnswer:
        return GeneratedAnswer(
            answer=generated_claim,
            cited_chunk_ids=[passages[0].chunk_id],
        )

    runtime = BoundedLangGraphRuntime(
        analytics_tool=forbidden_summary,
        province_analytics_tool=province_analytics,
        retrieval_tool=_retrieve,
        answer_generator=generate,
    )
    response = (
        await runtime.invoke(
            _state(
                "Top 2 provinces with the most hotspot detections in September 2023, "
                "and what does FRP mean?"
            )
        )
    )["response"]

    assert generated_claim not in response.answer
    assert response.province_analytics is not None
    assert response.province_analytics["execution"]["metric_value"] == 12
    assert response.execution_trace is not None
    assert response.execution_trace.status == "partial"
    assert any("rejected" in limitation for limitation in response.limitations)


@pytest.mark.asyncio
async def test_a03_provenance_correlates_with_combined_trace_without_false_operation() -> None:
    captured_inputs: list[ProvinceAnalyticsToolInput] = []

    async def forbidden_summary(_: AnalyticsToolInput, __: str) -> SummaryResponse:
        raise AssertionError("ranking must use the typed province analytics tool")

    async def province_analytics(
        tool_input: ProvinceAnalyticsToolInput, _: str
    ) -> ProvinceAnalytics:
        captured_inputs.append(tool_input)
        return _province_ranking()

    runtime = BoundedLangGraphRuntime(
        analytics_tool=forbidden_summary,
        province_analytics_tool=province_analytics,
        retrieval_tool=_retrieve,
    )
    result = await runtime.invoke(
        _state(
            "Top 2 provinces with the most hotspot detections in September 2023, "
            "and what does FRP mean?"
        )
    )
    response = result["response"]
    provenance = response.province_analytics

    assert captured_inputs == [result["province_analytics_tool_input"]]
    assert provenance is not None
    assert provenance["execution"]["operation_id"] == "hotspot_province_ranking_v1"
    assert provenance["execution"]["read_only"] is True
    assert provenance["execution"]["parameterized"] is True
    assert provenance["result"]["source"]["provider"] == "NASA FIRMS"
    assert provenance["result"]["source"]["dataset_version"] == "VNP14IMG.002"
    trace = response.execution_trace
    assert trace is not None and trace.route == "combined" and trace.status == "complete"
    assert all(step.kind != "analytics_query" for step in trace.steps)


@pytest.mark.asyncio
async def test_a03_provenance_mismatch_fails_branch_without_false_trace_operation() -> None:
    async def forbidden_summary(_: AnalyticsToolInput, __: str) -> SummaryResponse:
        raise AssertionError("ranking must use the typed province analytics tool")

    async def mismatched_province_analytics(
        _: ProvinceAnalyticsToolInput, __: str
    ) -> ProvinceAnalytics:
        result = _province_ranking().model_dump(mode="json")
        result["execution"]["parameters"]["direction"] = "lowest"
        result["result"]["direction"] = "lowest"
        result["result"]["rows"] = list(reversed(result["result"]["rows"]))
        for dense_rank, row in enumerate(result["result"]["rows"], start=1):
            row["dense_rank"] = dense_rank
        return ProvinceAnalytics.model_validate(result)

    runtime = BoundedLangGraphRuntime(
        analytics_tool=forbidden_summary,
        province_analytics_tool=mismatched_province_analytics,
        retrieval_tool=_retrieve,
    )
    response = (
        await runtime.invoke(
            _state(
                "Top 2 provinces with the most hotspot detections in September 2023, "
                "and what does FRP mean?"
            )
        )
    )["response"]

    assert response.province_analytics is None
    assert response.citations
    assert response.execution_trace is not None
    assert response.execution_trace.status == "partial"
    assert all(step.kind != "analytics_query" for step in response.execution_trace.steps)
