from __future__ import annotations

from typing import Literal

from wildfire_api.agent.filter_resolver import ResolutionStatus, ResolvedChatContext
from wildfire_api.agent.state import AgentState
from wildfire_api.schemas.chat import (
    AbstentionDetails,
    AnalyticsParameters,
    AnalyticsQueryDetails,
    CitationValidationDetails,
    ExecutionTrace,
    ExecutionTraceStep,
    FilterResolutionDetails,
    LocalGenerationDetails,
    RetrievedItem,
    RouteSelectionDetails,
    VectorRetrievalDetails,
    YearComparisonParameters,
)

_FILTER_REASON_MAP = {
    "multiple_provinces": "ambiguous_province",
    "ambiguous_date": "invalid_date_range",
    "relative_date": "invalid_date_range",
    "open_ended_date": "invalid_date_range",
    "invalid_date": "invalid_date_range",
    "multiple_dates": "conflicting_date_range",
    "multiple_years": "conflicting_date_range",
    "reversed_range": "invalid_date_range",
    "date_out_of_coverage": "invalid_date_range",
    "missing_year": "missing_date_range",
    "missing_province": "missing_province",
    "missing_date_range": "missing_date_range",
}


def _duration(state: AgentState, operation: str) -> int | None:
    return state.get("operation_durations_ms", {}).get(operation)


def _step(
    steps: list[ExecutionTraceStep],
    *,
    kind: str,
    status: Literal["complete", "abstained", "failed"],
    label: str,
    details: object,
    duration_ms: int | None = None,
) -> None:
    steps.append(
        ExecutionTraceStep.model_validate(
            {
                "sequence": len(steps) + 1,
                "kind": kind,
                "status": status,
                "label": label,
                "duration_ms": duration_ms,
                "details": details,
            }
        )
    )


def _filter_details(resolved: ResolvedChatContext) -> FilterResolutionDetails:
    reasons = list(
        dict.fromkeys(
            _FILTER_REASON_MAP[code] for code in resolved.codes if code in _FILTER_REASON_MAP
        )
    )
    outcome = {
        ResolutionStatus.RESOLVED: "resolved",
        ResolutionStatus.NEEDS_CLARIFICATION: "needs_clarification",
        ResolutionStatus.INVALID: "invalid",
        ResolutionStatus.NOT_APPLICABLE: "not_applicable",
    }[resolved.status]
    return FilterResolutionDetails(
        province_codes=[resolved.province_code] if resolved.province_code else [],
        date_from=resolved.date_from,
        date_to=resolved.date_to,
        province_source=resolved.province_source,
        date_from_source=resolved.date_source,
        date_to_source=resolved.date_source,
        reason_codes=reasons,
        outcome=outcome,
    )


def build_execution_trace(state: AgentState) -> ExecutionTrace:
    """Serialize allowlisted facts already present in state; never perform an operation."""
    route = state.get("mode", "unsupported")
    steps: list[ExecutionTraceStep] = []
    _step(
        steps,
        kind="route_selection",
        status="complete",
        label=f"Final route is {route}.",
        details=RouteSelectionDetails(route=route),
        duration_ms=_duration(state, "route_selection"),
    )

    resolved = state.get("resolved_context")
    if resolved is not None:
        resolved_ok = resolved.status == ResolutionStatus.RESOLVED
        _step(
            steps,
            kind="filter_resolution",
            status="complete" if resolved_ok else "abstained",
            label=(
                "Resolved canonical analytics filters."
                if resolved_ok
                else "Analytics filters require clarification."
            ),
            details=_filter_details(resolved),
            duration_ms=_duration(state, "filter_resolution"),
        )

    tool_input = state.get("analytics_tool_input")
    summary = state.get("analytics_result")
    if tool_input is not None and summary is not None:
        _step(
            steps,
            kind="analytics_query",
            status="complete",
            label="Read hotspot detections using a read-only analytics operation.",
            details=AnalyticsQueryDetails(
                operation_id="hotspot_summary_v1",
                parameters=AnalyticsParameters(
                    province_codes=[tool_input.province_code],
                    date_from=tool_input.date_from,
                    date_to=tool_input.date_to,
                ),
                read_only=True,
                returned_rows=len(summary.series),
                metric_name=summary.metric,
                metric_value=summary.total,
            ),
            duration_ms=_duration(state, "analytics_query"),
        )
    elif tool_input is not None and state.get("analytics_failure"):
        _step(
            steps,
            kind="analytics_query",
            status="failed",
            label="The read-only analytics operation did not return a usable result.",
            details=AnalyticsQueryDetails(
                operation_id="hotspot_summary_v1",
                parameters=AnalyticsParameters(
                    province_codes=[tool_input.province_code],
                    date_from=tool_input.date_from,
                    date_to=tool_input.date_to,
                ),
                read_only=True,
                returned_rows=0,
                metric_name=None,
                metric_value=None,
            ),
            duration_ms=_duration(state, "analytics_query"),
        )

    year_input = state.get("year_comparison_tool_input")
    year_result = state.get("year_comparison")
    if year_input is not None and year_result is not None:
        _step(
            steps,
            kind="analytics_query",
            status="complete",
            label="Compared yearly hotspot detections using a read-only analytics operation.",
            details=AnalyticsQueryDetails(
                operation_id="hotspot_year_comparison_v1",
                parameters=YearComparisonParameters(
                    province_code=year_input.province_code,
                    years=list(year_input.years),
                ),
                read_only=True,
                returned_rows=len(year_result.points),
                metric_name=year_result.metric,
                metric_value=None,
            ),
            duration_ms=_duration(state, "analytics_query"),
        )

    passages = state.get("retrieved_passages", [])
    retrieval_input = state.get("retrieval_tool_input")
    if retrieval_input is not None:
        items = [
            RetrievedItem(
                chunk_id=passage.chunk_id,
                title=passage.title,
                url=str(passage.url),
                rank=rank,
            )
            for rank, passage in enumerate(passages, 1)
        ]
        _step(
            steps,
            kind="vector_retrieval",
            status=(
                "complete"
                if passages
                else "failed"
                if state.get("rag_failure")
                else "abstained"
            ),
            label=(
                f"Retrieved {len(passages)} approved NASA passages locally."
                if passages
                else "NASA documentation retrieval did not return usable evidence."
            ),
            details=VectorRetrievalDetails(
                provider="local",
                embedding_model=state["retrieval_embedding_model"],
                collection=state["retrieval_collection"],
                top_k=retrieval_input.limit,
                returned_count=len(items),
                items=items,
            ),
            duration_ms=_duration(state, "vector_retrieval"),
        )

    if state.get("llm_calls", 0):
        _step(
            steps,
            kind="local_generation",
            status="failed" if state.get("generation_failure") else "complete",
            label=(
                "Local answer generation did not return an accepted answer."
                if state.get("generation_failure")
                else "Generated an answer locally."
            ),
            details=LocalGenerationDetails(
                provider="ollama",
                model=state["generation_model"],
                input_passage_count=len(passages),
                model_calls=state["llm_calls"],
            ),
            duration_ms=_duration(state, "local_generation"),
        )

    if retrieval_input is not None and passages:
        accepted = len(state.get("accepted_citation_ids", []))
        _step(
            steps,
            kind="citation_validation",
            status="complete" if accepted else "abstained",
            label=f"Validated {accepted} citations.",
            details=CitationValidationDetails(
                candidate_count=len(passages),
                accepted_count=accepted,
                outcome="passed" if accepted else "abstained",
            ),
            duration_ms=_duration(state, "citation_validation"),
        )

    if route == "unsupported":
        reason: Literal[
            "missing_province",
            "missing_date_range",
            "unsupported_intent",
            "insufficient_evidence",
        ] = "unsupported_intent"
        if resolved is not None:
            if "missing_province" in resolved.codes:
                reason = "missing_province"
            elif "missing_date_range" in resolved.codes or "missing_year" in resolved.codes:
                reason = "missing_date_range"
            elif state.get("failure"):
                reason = "insufficient_evidence"
        elif state.get("failure"):
            reason = "insufficient_evidence"
        _step(
            steps,
            kind="abstention",
            status="abstained",
            label="Abstained from an unsupported or insufficiently evidenced request.",
            details=AbstentionDetails(reason_code=reason),
        )

    status = (
        "abstained"
        if route == "unsupported"
        else ("partial" if state.get("failure") else "complete")
    )
    return ExecutionTrace(route=route, status=status, steps=steps)
