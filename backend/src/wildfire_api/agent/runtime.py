from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime
from time import perf_counter
from typing import Literal, Protocol, TypeVar

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from wildfire_api.agent.execution_trace import build_execution_trace
from wildfire_api.agent.filter_resolver import ChatFilterResolver, ResolutionStatus
from wildfire_api.agent.intent_models import ValidatedPlan
from wildfire_api.agent.intent_router import DeterministicIntentRouter
from wildfire_api.agent.semantic_execution import (
    SemanticExecutionGate,
    SemanticExecutionRejected,
)
from wildfire_api.agent.state import (
    AgentPlan,
    AgentState,
    AnalyticsToolInput,
    ProvinceAnalyticsToolInput,
    RetrievalToolInput,
    YearComparisonToolInput,
)
from wildfire_api.contracts.api_v1_2_proposal import (
    MultiProvinceParameters,
    ProvinceAnalytics,
    ProvinceRankingParameters,
    TopNSelection,
)
from wildfire_api.core.errors import AppError, dependency_unavailable, request_timeout
from wildfire_api.llm.ollama import GeneratedAnswer, LocalModelError
from wildfire_api.rag.fetch import DocumentFetchError, validate_nasa_url
from wildfire_api.rag.models import RetrievedPassage
from wildfire_api.schemas.chat import ChatChart, ChatMetric, ChatResponse
from wildfire_api.schemas.common import Citation, Filters, Usage
from wildfire_api.schemas.hotspots import SummaryResponse, YearComparisonResponse

HOTSPOT_CAVEAT = "Hotspot detections are not confirmed wildfires or burned-area estimates."
UNSUPPORTED_ANSWER = (
    "I cannot support that request with this product. I can report satellite hotspot "
    "detections and explain NASA documentation, but I cannot provide confirmed fires, "
    "burned area, causes, predictions, or unsupported products, dates, or regions."
)


class AgentRuntime(Protocol):
    async def invoke(self, state: AgentState) -> AgentState: ...


class AnalyticsTool(Protocol):
    async def __call__(
        self, tool_input: AnalyticsToolInput, request_id: str
    ) -> SummaryResponse: ...


class ProvinceAnalyticsTool(Protocol):
    async def __call__(self, tool_input: ProvinceAnalyticsToolInput, request_id: str) -> object: ...


class YearComparisonTool(Protocol):
    async def __call__(
        self, tool_input: YearComparisonToolInput, request_id: str
    ) -> YearComparisonResponse: ...


class RetrievalTool(Protocol):
    async def __call__(self, tool_input: RetrievalToolInput) -> list[RetrievedPassage]: ...


class AnswerGenerator(Protocol):
    async def __call__(
        self, question: str, passages: list[RetrievedPassage]
    ) -> GeneratedAnswer: ...


Planner = Callable[[str], Awaitable[object]]
StageResult = TypeVar("StageResult")


@dataclass(frozen=True, slots=True)
class AgentLimits:
    max_graph_steps: int = 6
    max_tool_calls: int = 2
    timeout_seconds: float = 8.0
    max_retrieved_characters: int = 6_000
    max_model_tokens: int = 1_200
    combined_stage_budgeting: bool = True

    def __post_init__(self) -> None:
        if not 3 <= self.max_graph_steps <= 12:
            raise ValueError("max_graph_steps must be between 3 and 12")
        if not 1 <= self.max_tool_calls <= 4:
            raise ValueError("max_tool_calls must be between 1 and 4")
        if not 0 < self.timeout_seconds <= 120:
            raise ValueError("timeout_seconds must be between 0 and 120")
        if not 500 <= self.max_retrieved_characters <= 20_000:
            raise ValueError("max_retrieved_characters must be between 500 and 20000")
        if not 128 <= self.max_model_tokens <= 4_096:
            raise ValueError("max_model_tokens must be between 128 and 4096")


class RuleBasedPlanner:
    """Compatibility wrapper around the typed deterministic B11 intent router."""

    def __init__(self, router: DeterministicIntentRouter | None = None) -> None:
        self._router = router or DeterministicIntentRouter()

    async def __call__(self, message: str) -> AgentPlan:
        decision = self._router.decide(message)
        return AgentPlan(mode=decision.mode, reason=decision.reason)


class BoundedLangGraphRuntime:
    def __init__(
        self,
        *,
        analytics_tool: AnalyticsTool,
        province_analytics_tool: ProvinceAnalyticsTool | None = None,
        year_comparison_tool: YearComparisonTool | None = None,
        retrieval_tool: RetrievalTool | None,
        planner: Planner | None = None,
        limits: AgentLimits | None = None,
        answer_generator: AnswerGenerator | None = None,
        filter_resolver: ChatFilterResolver | None = None,
        embedding_model: str = "local-hashing-v1",
        retrieval_collection: str = "nasa_firms_documents_v1",
        generation_model: str = "qwen2.5:1.5b",
        semantic_execution_gate: SemanticExecutionGate | None = None,
    ) -> None:
        self._analytics_tool = analytics_tool
        self._province_analytics_tool = province_analytics_tool
        self._year_comparison_tool = year_comparison_tool
        self._retrieval_tool = retrieval_tool
        self._intent_router = DeterministicIntentRouter()
        self._planner = planner or RuleBasedPlanner(self._intent_router)
        self._limits = limits or AgentLimits()
        self._answer_generator = answer_generator
        self._filter_resolver = filter_resolver or ChatFilterResolver()
        self._embedding_model = embedding_model
        self._retrieval_collection = retrieval_collection
        self._generation_model = generation_model
        self._semantic_execution_gate = semantic_execution_gate
        self._graph = build_production_graph(self)

    def _semantic_gate(self) -> SemanticExecutionGate:
        if self._semantic_execution_gate is None:
            self._semantic_execution_gate = SemanticExecutionGate()
        return self._semantic_execution_gate

    async def invoke(self, state: AgentState) -> AgentState:
        workflow_deadline = perf_counter() + self._limits.timeout_seconds
        initial: AgentState = {
            **state,
            "graph_steps": 0,
            "tool_calls": 0,
            "max_graph_steps": min(
                state.get("max_graph_steps", self._limits.max_graph_steps),
                self._limits.max_graph_steps,
            ),
            "max_tool_calls": min(
                state.get("max_tool_calls", self._limits.max_tool_calls),
                self._limits.max_tool_calls,
            ),
            "workflow_deadline": workflow_deadline,
            "retrieved_passages": [],
            "operation_durations_ms": {},
            "retrieval_embedding_model": self._embedding_model,
            "retrieval_collection": self._retrieval_collection,
            "generation_model": self._generation_model,
        }
        try:
            async with asyncio.timeout(self._limits.timeout_seconds):
                return await self._graph.ainvoke(
                    initial,
                    config={"recursion_limit": self._limits.max_graph_steps + 2},
                )
        except TimeoutError as exc:
            raise request_timeout("The bounded chat workflow timed out.") from exc

    async def _run_combined_stage(
        self,
        state: AgentState,
        stage: Literal["analytics", "retrieval", "generation"],
        operation: Callable[[], Awaitable[StageResult]],
    ) -> StageResult:
        """Reserve bounded compose time without creating detached dependency tasks."""
        if state.get("mode") != "combined" or not self._limits.combined_stage_budgeting:
            return await operation()
        compose_reserve = min(
            0.25,
            max(0.001, self._limits.timeout_seconds * 0.10),
        )
        stage_fraction = {"analytics": 0.40, "retrieval": 0.35, "generation": 0.45}[stage]
        stage_cap = self._limits.timeout_seconds * stage_fraction
        available = min(
            stage_cap,
            state["workflow_deadline"] - perf_counter() - compose_reserve,
        )
        if available <= 0:
            raise TimeoutError("combined stage has no remaining bounded execution budget")
        async with asyncio.timeout(available):
            return await operation()

    def _step(self, state: AgentState) -> int:
        steps = state.get("graph_steps", 0) + 1
        if steps > state["max_graph_steps"]:
            raise dependency_unavailable("The chat workflow exceeded its graph-step budget.")
        return steps

    async def plan(self, state: AgentState) -> AgentState:
        started = perf_counter()
        try:
            raw_plan = await self._planner(state["message"])
            plan = (
                raw_plan if isinstance(raw_plan, AgentPlan) else AgentPlan.model_validate(raw_plan)
            )
        except (ValidationError, TypeError, ValueError, KeyError):
            plan = AgentPlan(
                mode="unsupported", reason="Planner output was invalid; safe fallback applied."
            )
        validated_plan: ValidatedPlan | None = None
        if plan.route_source == "semantic_guarded" and plan.mode == "rag":
            try:
                validated_plan = self._semantic_gate().validate_documentation(state["message"])
            except (SemanticExecutionRejected, ValidationError, ValueError, KeyError):
                plan = AgentPlan(
                    mode="unsupported",
                    reason="The semantic route failed deterministic validation.",
                    route_source="semantic_rejected",
                    semantic_intent=plan.semantic_intent,
                )
        result: AgentState = {
            **state,
            "mode": plan.mode,
            "plan_reason": plan.reason,
            "route_source": plan.route_source,
            "semantic_intent": plan.semantic_intent,
            "documentation_query": (
                self._intent_router.documentation_query(state["message"])
                if plan.mode == "combined"
                else state["message"]
            ),
            "graph_steps": self._step(state),
            "operation_durations_ms": {
                **state.get("operation_durations_ms", {}),
                "route_selection": round((perf_counter() - started) * 1000),
            },
        }
        if validated_plan is not None:
            result["validated_plan"] = validated_plan
        return result

    def route(self, state: AgentState) -> str:
        return state["mode"]

    async def resolve_filters(self, state: AgentState) -> AgentState:
        started = perf_counter()
        resolved = self._filter_resolver.resolve(
            state["message"],
            province_code=state.get("province_code"),
            date_from=state.get("date_from"),
            date_to=state.get("date_to"),
        )
        ranking_request = bool(
            state.get("semantic_intent") == "province_ranking"
            or re.search(
                r"\b(which\s+province|top\s+\d+|bottom\s+\d+|highest|lowest|"
                r"most\s+hotspots?|least\s+hotspots?)\b",
                state["message"],
                re.IGNORECASE,
            )
        )
        if (
            ranking_request
            and resolved.status == ResolutionStatus.NEEDS_CLARIFICATION
            and resolved.codes == ("missing_province",)
            and resolved.date_from
            and resolved.date_to
        ):
            resolved = resolved.model_copy(
                update={"status": ResolutionStatus.RESOLVED, "codes": ()}
            )
        # Synthetic A01 fixtures use deliberately non-D04 province identifiers. Preserve
        # their typed context while still exercising deterministic date resolution.
        if state["product_id"] == "MOCK_ONLY" and state.get("province_code"):
            resolved = resolved.model_copy(
                update={
                    "province_code": state["province_code"],
                    "province_source": "ui_context",
                }
            )
        if resolved.status != ResolutionStatus.RESOLVED:
            labels = {
                "missing_province": "a province",
                "missing_date_range": "a complete date range",
                "missing_year": "a year for the stated month",
            }
            fields = ", ".join(labels.get(code, code) for code in resolved.codes)
            if state["mode"] == "combined":
                failure = (
                    f"Analytics was not executed because it requires "
                    f"{fields or 'valid filters'}; NASA documentation was handled independently."
                )
                return {
                    **state,
                    "failure": failure,
                    "analytics_failure": failure,
                    "skip_analytics": True,
                    "resolved_context": resolved,
                    "graph_steps": self._step(state),
                    "operation_durations_ms": {
                        **state.get("operation_durations_ms", {}),
                        "filter_resolution": round((perf_counter() - started) * 1000),
                    },
                }
            return {
                **state,
                "mode": "unsupported",
                "plan_reason": f"Analytics requires {fields or 'valid filters'}.",
                "failure": "No analytics query was executed.",
                "resolved_context": resolved,
                "graph_steps": self._step(state),
                "operation_durations_ms": {
                    **state.get("operation_durations_ms", {}),
                    "filter_resolution": round((perf_counter() - started) * 1000),
                },
            }
        result: AgentState = {
            **state,
            "province_code": resolved.province_code,
            "province_codes": resolved.province_codes,
            "date_from": resolved.date_from,
            "date_to": resolved.date_to,
            "resolved_context": resolved,
            "graph_steps": self._step(state),
            "operation_durations_ms": {
                **state.get("operation_durations_ms", {}),
                "filter_resolution": round((perf_counter() - started) * 1000),
            },
        }
        if state.get("route_source") == "semantic_guarded":
            semantic_intent = state.get("semantic_intent")
            if semantic_intent is None:
                return {
                    **result,
                    "mode": "unsupported",
                    "plan_reason": "The semantic route omitted its reviewed intent.",
                    "failure": "No analytics query was executed.",
                }
            try:
                result["validated_plan"] = self._semantic_gate().validate_analytics(
                    message=state["message"],
                    product_id=state["product_id"],
                    semantic_intent=semantic_intent,
                    resolved=resolved,
                    combined=state["mode"] == "combined",
                )
            except (SemanticExecutionRejected, ValidationError, ValueError, KeyError):
                return {
                    **result,
                    "mode": "unsupported",
                    "plan_reason": "The semantic route failed deterministic operation validation.",
                    "failure": "No analytics query was executed.",
                }
        return result

    def _reserve_tool(self, state: AgentState) -> int:
        calls = state.get("tool_calls", 0) + 1
        if calls > state["max_tool_calls"]:
            raise dependency_unavailable("The chat workflow exceeded its tool-call budget.")
        return calls

    def _recover_combined_branch(
        self,
        state: AgentState,
        *,
        branch: str,
        message: str,
        tool_calls: int | None = None,
        duration_operation: str | None = None,
        started: float | None = None,
        **updates: object,
    ) -> AgentState:
        result: AgentState = {
            **state,
            **updates,
            "failure": message,
            f"{branch}_failure": message,
            "graph_steps": self._step(state),
        }
        if tool_calls is not None:
            result["tool_calls"] = tool_calls
        if duration_operation is not None and started is not None:
            result["operation_durations_ms"] = {
                **state.get("operation_durations_ms", {}),
                duration_operation: round((perf_counter() - started) * 1000),
            }
        return result

    @staticmethod
    def _combined_branch_message(
        branch: str, exc: BaseException, *, analytics_available: bool = True
    ) -> str:
        timed_out = isinstance(exc, TimeoutError) or (
            isinstance(exc, AppError) and exc.code == "REQUEST_TIMEOUT"
        )
        if branch == "analytics":
            return (
                "Analytics timed out; no hotspot number was produced."
                if timed_out
                else "Analytics could not be completed; no hotspot number was produced."
            )
        if timed_out:
            return (
                "NASA documentation retrieval timed out; the analytics result is still valid."
                if analytics_available
                else (
                    "NASA documentation retrieval timed out; "
                    "no documentation evidence was produced."
                )
            )
        return (
            "NASA documentation is unavailable; the analytics result is still valid."
            if analytics_available
            else "NASA documentation is unavailable; no documentation evidence was produced."
        )

    async def analytics(self, state: AgentState) -> AgentState:
        validated_operation = None
        if state.get("route_source") == "semantic_guarded":
            validated_plan = state.get("validated_plan")
            if validated_plan is None:
                return {
                    **state,
                    "mode": "unsupported",
                    "failure": "No validated semantic analytics plan was available.",
                    "graph_steps": self._step(state),
                }
            validated_operation = next(
                (operation for operation in validated_plan.operations if operation.arguments),
                None,
            )
            if validated_operation is None:
                return {
                    **state,
                    "mode": "unsupported",
                    "failure": "No validated semantic analytics operation was available.",
                    "graph_steps": self._step(state),
                }
        resolved_context = state.get("resolved_context")
        comparison_years = resolved_context.comparison_years if resolved_context else ()
        if comparison_years and self._year_comparison_tool is not None:
            tool_input = YearComparisonToolInput(
                product_id=state["product_id"],
                province_code=state["province_code"],
                years=comparison_years,
            )
            started = perf_counter()
            reserved_calls = self._reserve_tool(state)
            try:
                raw_result = await self._run_combined_stage(
                    state,
                    "analytics",
                    lambda: self._year_comparison_tool(tool_input, state["request_id"]),
                )
                result = YearComparisonResponse.model_validate(raw_result)
                if (
                    result.request_id != state["request_id"]
                    or result.product_id != tool_input.product_id
                    or result.province_code != tool_input.province_code
                    or result.years != list(tool_input.years)
                ):
                    raise ValueError("year comparison identity does not match tool request")
            except AppError:
                raise
            except Exception as exc:
                raise dependency_unavailable("Analytics is currently unavailable.") from exc
            return {
                **state,
                "year_comparison": result,
                "year_comparison_tool_input": tool_input,
                "tool_calls": reserved_calls,
                "graph_steps": self._step(state),
                "operation_durations_ms": {
                    **state.get("operation_durations_ms", {}),
                    "analytics_query": round((perf_counter() - started) * 1000),
                },
            }
        ranking = (
            validated_operation.operation_id == "hotspot_province_ranking_v1"
            if validated_operation is not None
            else bool(
                re.search(
                    r"\b(which\s+province|top\s+\d+|bottom\s+\d+|highest|lowest|most\s+hotspots?|least\s+hotspots?)\b",
                    state["message"],
                    re.IGNORECASE,
                )
            )
        )
        province_codes = (
            validated_operation.arguments.province_codes
            if validated_operation is not None and validated_operation.arguments
            else state.get("province_codes", ())
        )
        if self._province_analytics_tool is not None and (ranking or len(province_codes) > 1):
            top_match = re.search(r"\b(?:top|bottom)\s+(\d+)\b", state["message"], re.IGNORECASE)
            top_n = int(top_match.group(1)) if top_match else 1
            comparison_requested = bool(
                state.get("semantic_intent") == "province_comparison"
                or re.search(
                    r"\b(compare|versus|difference|higher|lower|which\s+had|bandingkan)\b",
                    state["message"],
                    re.IGNORECASE,
                )
            )
            if validated_operation is not None and validated_operation.arguments:
                arguments = validated_operation.arguments
                top_n = arguments.top_n or 1
                comparison_requested = bool(arguments.comparison_requested)
            tool_input = ProvinceAnalyticsToolInput(
                product_id=(
                    validated_operation.arguments.product_id
                    if validated_operation is not None and validated_operation.arguments
                    else state["product_id"]
                ),
                province_codes=province_codes,
                date_from=(
                    validated_operation.arguments.date_from
                    if validated_operation is not None and validated_operation.arguments
                    else state["date_from"]
                ),
                date_to=(
                    validated_operation.arguments.date_to
                    if validated_operation is not None and validated_operation.arguments
                    else state["date_to"]
                ),
                operation="ranking" if ranking else "multi_province",
                direction=(
                    validated_operation.arguments.direction
                    if validated_operation is not None
                    and validated_operation.arguments
                    and validated_operation.arguments.direction
                    else "lowest"
                    if re.search(
                        r"\b(lowest|least|bottom|paling\s+sedikit)\b",
                        state["message"],
                        re.IGNORECASE,
                    )
                    else "highest"
                ),
                top_n=top_n,
                comparison_requested=comparison_requested,
            )
            started = perf_counter()
            reserved_calls = self._reserve_tool(state)
            try:
                raw_result = await self._run_combined_stage(
                    state,
                    "analytics",
                    lambda: self._province_analytics_tool(tool_input, state["request_id"]),
                )
                result = ProvinceAnalytics.model_validate(raw_result)
                self._validate_province_analytics_identity(result, tool_input)
                payload = result.model_dump(mode="json")
            except AppError as exc:
                if state["mode"] != "combined":
                    raise
                return self._recover_combined_branch(
                    state,
                    branch="analytics",
                    message=self._combined_branch_message("analytics", exc),
                    tool_calls=reserved_calls,
                    duration_operation="analytics_query",
                    started=started,
                    province_analytics_tool_input=tool_input,
                )
            except Exception as exc:
                if state["mode"] != "combined":
                    raise dependency_unavailable("Analytics is currently unavailable.") from exc
                return self._recover_combined_branch(
                    state,
                    branch="analytics",
                    message=self._combined_branch_message("analytics", exc),
                    tool_calls=reserved_calls,
                    duration_operation="analytics_query",
                    started=started,
                    province_analytics_tool_input=tool_input,
                )
            return {
                **state,
                "province_analytics": payload,
                "province_analytics_tool_input": tool_input,
                "tool_calls": reserved_calls,
                "graph_steps": self._step(state),
                "operation_durations_ms": {
                    **state.get("operation_durations_ms", {}),
                    "analytics_query": round((perf_counter() - started) * 1000),
                },
            }
        if not state.get("province_code") or not state.get("date_from") or not state.get("date_to"):
            return {
                **state,
                "failure": "Analytics requires a province and complete date range.",
                "graph_steps": self._step(state),
            }
        arguments = validated_operation.arguments if validated_operation is not None else None
        tool_input = AnalyticsToolInput(
            product_id=arguments.product_id if arguments else state["product_id"],
            province_code=(arguments.province_codes[0] if arguments else state["province_code"]),
            date_from=arguments.date_from if arguments else state["date_from"],
            date_to=arguments.date_to if arguments else state["date_to"],
        )
        started = perf_counter()
        reserved_calls = self._reserve_tool(state)
        try:
            raw_result = await self._run_combined_stage(
                state,
                "analytics",
                lambda: self._analytics_tool(tool_input, state["request_id"]),
            )
            result = SummaryResponse.model_validate(raw_result)
            self._validate_analytics_identity(result, tool_input, state["request_id"])
        except AppError as exc:
            if state["mode"] != "combined":
                raise
            return self._recover_combined_branch(
                state,
                branch="analytics",
                message=self._combined_branch_message("analytics", exc),
                tool_calls=reserved_calls,
                duration_operation="analytics_query",
                started=started,
                analytics_tool_input=tool_input,
            )
        except (ValidationError, TypeError, ValueError, KeyError) as exc:
            if state["mode"] != "combined":
                raise dependency_unavailable("Analytics returned an invalid response.") from exc
            return self._recover_combined_branch(
                state,
                branch="analytics",
                message="Analytics returned an invalid response; no hotspot number was produced.",
                tool_calls=reserved_calls,
                duration_operation="analytics_query",
                started=started,
                analytics_tool_input=tool_input,
            )
        except Exception as exc:
            if state["mode"] != "combined":
                raise dependency_unavailable("Analytics is currently unavailable.") from exc
            return self._recover_combined_branch(
                state,
                branch="analytics",
                message=self._combined_branch_message("analytics", exc),
                tool_calls=reserved_calls,
                duration_operation="analytics_query",
                started=started,
                analytics_tool_input=tool_input,
            )
        return {
            **state,
            "analytics_result": result,
            "analytics_tool_input": tool_input,
            "tool_calls": reserved_calls,
            "graph_steps": self._step(state),
            "operation_durations_ms": {
                **state.get("operation_durations_ms", {}),
                "analytics_query": round((perf_counter() - started) * 1000),
            },
        }

    async def retrieve(self, state: AgentState) -> AgentState:
        if self._retrieval_tool is None:
            failure = "NASA documentation retrieval is not configured."
            return {
                **state,
                "failure": failure,
                "rag_failure": failure,
                "graph_steps": self._step(state),
            }
        tool_input = RetrievalToolInput(query=state["documentation_query"], limit=5)
        reserved_calls = self._reserve_tool(state)
        started = perf_counter()
        try:
            raw_passages = await self._run_combined_stage(
                state,
                "retrieval",
                lambda: self._retrieval_tool(tool_input),
            )
            passages = [RetrievedPassage.model_validate(item) for item in raw_passages]
            for passage in passages:
                self._validate_retrieval_provenance(passage)
        except AppError as exc:
            if state["mode"] != "combined":
                raise
            return self._recover_combined_branch(
                state,
                branch="rag",
                message=self._combined_branch_message(
                    "rag", exc, analytics_available=not bool(state.get("analytics_failure"))
                ),
                tool_calls=reserved_calls,
                duration_operation="vector_retrieval",
                started=started,
                retrieval_tool_input=tool_input,
            )
        except (ValidationError, TypeError, ValueError, KeyError) as exc:
            if state["mode"] != "combined":
                raise dependency_unavailable(
                    "NASA retrieval returned an invalid response."
                ) from exc
            return self._recover_combined_branch(
                state,
                branch="rag",
                message=(
                    "NASA documentation returned invalid evidence; "
                    "the analytics result is still valid."
                    if not state.get("analytics_failure")
                    else "NASA documentation returned invalid evidence; "
                    "no documentation evidence was produced."
                ),
                tool_calls=reserved_calls,
                duration_operation="vector_retrieval",
                started=started,
                retrieval_tool_input=tool_input,
            )
        except Exception as exc:
            if state["mode"] != "combined":
                raise dependency_unavailable(
                    "NASA documentation retrieval is unavailable."
                ) from exc
            return self._recover_combined_branch(
                state,
                branch="rag",
                message=self._combined_branch_message(
                    "rag", exc, analytics_available=not bool(state.get("analytics_failure"))
                ),
                tool_calls=reserved_calls,
                duration_operation="vector_retrieval",
                started=started,
                retrieval_tool_input=tool_input,
            )
        if not passages:
            failure = (
                "No relevant NASA documentation was retrieved; "
                "the analytics result is still valid."
                if state["mode"] == "combined" and not state.get("analytics_failure")
                else (
                    "No relevant NASA documentation was retrieved; "
                    "no documentation evidence was produced."
                )
                if state["mode"] == "combined"
                else "No relevant NASA documentation was retrieved."
            )
            return {
                **state,
                "failure": failure,
                "rag_failure": failure,
                "retrieval_tool_input": tool_input,
                "tool_calls": reserved_calls,
                "graph_steps": self._step(state),
                "operation_durations_ms": {
                    **state.get("operation_durations_ms", {}),
                    "vector_retrieval": round((perf_counter() - started) * 1000),
                },
            }
        bounded: list[RetrievedPassage] = []
        character_count = 0
        for passage in passages[: tool_input.limit]:
            character_count += len(passage.text)
            if character_count > self._limits.max_retrieved_characters:
                break
            bounded.append(passage)
        return {
            **state,
            "retrieved_passages": bounded,
            "retrieval_tool_input": tool_input,
            "tool_calls": reserved_calls,
            "graph_steps": self._step(state),
            "operation_durations_ms": {
                **state.get("operation_durations_ms", {}),
                "vector_retrieval": round((perf_counter() - started) * 1000),
            },
        }

    @staticmethod
    def _validate_analytics_identity(
        result: SummaryResponse,
        tool_input: AnalyticsToolInput,
        request_id: str,
    ) -> None:
        expected_provinces = [tool_input.province_code]
        identity_matches = (
            result.request_id == request_id
            and result.metric == "satellite_hotspot_detections"
            and result.product_id == tool_input.product_id
            and result.filters.province_codes == expected_provinces
            and result.filters.date_from == tool_input.date_from
            and result.filters.date_to == tool_input.date_to
        )
        expected_status = "mock" if tool_input.product_id == "MOCK_ONLY" else "verified"
        expected_provider = "Synthetic fixture" if expected_status == "mock" else "NASA FIRMS"
        source_matches = (
            result.source.data_status == expected_status
            and result.source.provider == expected_provider
        )
        if not identity_matches or not source_matches:
            raise ValueError("analytics response identity does not match the tool request")

    @staticmethod
    def _validate_province_analytics_identity(
        result: ProvinceAnalytics,
        tool_input: ProvinceAnalyticsToolInput,
    ) -> None:
        execution = result.execution
        params = execution.parameters
        identity_matches = (
            params.product_id == tool_input.product_id
            and params.date_from == tool_input.date_from
            and params.date_to == tool_input.date_to
        )
        expected_status = "mock" if tool_input.product_id == "MOCK_ONLY" else "verified"
        expected_provider = "Synthetic fixture" if expected_status == "mock" else "NASA FIRMS"
        source_matches = (
            result.result.source.data_status == expected_status
            and result.result.source.provider == expected_provider
        )
        if tool_input.operation == "multi_province":
            operation_matches = (
                execution.operation_id == "hotspot_multi_province_summary_v1"
                and isinstance(params, MultiProvinceParameters)
                and params.province_codes == list(tool_input.province_codes)
                and params.comparison_requested == tool_input.comparison_requested
            )
        else:
            selection = params.selection if isinstance(params, ProvinceRankingParameters) else None
            operation_matches = (
                execution.operation_id == "hotspot_province_ranking_v1"
                and isinstance(params, ProvinceRankingParameters)
                and params.direction == tool_input.direction
                and isinstance(selection, TopNSelection)
                and selection.top_n == tool_input.top_n
            )
        if not identity_matches or not source_matches or not operation_matches:
            raise ValueError("province analytics provenance does not match the tool request")

    @staticmethod
    def _validate_retrieval_provenance(passage: RetrievedPassage) -> None:
        try:
            validate_nasa_url(str(passage.url))
        except DocumentFetchError as exc:
            raise ValueError("retrieval passage has invalid NASA provenance") from exc
        if not passage.untrusted_content:
            raise ValueError("retrieval passage must remain marked as untrusted content")
        if not re.fullmatch(r"[a-f0-9]{64}", passage.content_hash):
            raise ValueError("retrieval passage has an invalid content hash")
        if not re.fullmatch(r"[a-f0-9]{64}", passage.chunk_id):
            raise ValueError("retrieval passage has an invalid stable chunk ID")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{2,63}", passage.document_id):
            raise ValueError("retrieval passage has an invalid document ID")
        try:
            retrieved_at = datetime.fromisoformat(passage.retrieved_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("retrieval passage has an invalid retrieval timestamp") from exc
        if retrieved_at.tzinfo is None or not passage.section.strip() or not passage.title.strip():
            raise ValueError("retrieval passage is missing citation metadata")

    async def compose(self, state: AgentState) -> AgentState:
        passages = state.get("retrieved_passages", [])
        should_generate = bool(
            passages
            and self._answer_generator is not None
            and not (state.get("mode") == "combined" and state.get("analytics_failure"))
        )
        if should_generate:
            started = perf_counter()
            model_calls = int(getattr(self._answer_generator, "model_calls", 1))
            try:
                generated = await self._run_combined_stage(
                    state,
                    "generation",
                    lambda: self._answer_generator(state["documentation_query"], passages),
                )
                supplied_chunk_ids = {passage.chunk_id for passage in passages}
                cited_chunk_ids = set(generated.cited_chunk_ids)
                if not cited_chunk_ids or not cited_chunk_ids <= supplied_chunk_ids:
                    raise LocalModelError(
                        "local chat model returned a citation outside supplied passages"
                    )
                if state.get("mode") == "combined":
                    self._validate_combined_generation(generated.answer, state)
            except LocalModelError as exc:
                if state.get("mode") != "combined":
                    raise dependency_unavailable("Local answer generation is unavailable.") from exc
                failure = (
                    "The local documentation answer was rejected; the exact analytics result "
                    "and retrieved NASA sources remain available."
                )
                state = {
                    **state,
                    "failure": failure,
                    "generation_failure": failure,
                    "llm_calls": model_calls,
                    "operation_durations_ms": {
                        **state.get("operation_durations_ms", {}),
                        "local_generation": round((perf_counter() - started) * 1000),
                    },
                }
            except (TimeoutError, AppError) as exc:
                if state.get("mode") != "combined":
                    raise dependency_unavailable("Local answer generation is unavailable.") from exc
                failure = (
                    "Local documentation generation timed out; the exact analytics result "
                    "and retrieved NASA sources remain available."
                    if isinstance(exc, TimeoutError)
                    or (isinstance(exc, AppError) and exc.code == "REQUEST_TIMEOUT")
                    else "Local documentation generation is unavailable; the exact analytics "
                    "result and retrieved NASA sources remain available."
                )
                state = {
                    **state,
                    "failure": failure,
                    "generation_failure": failure,
                    "llm_calls": model_calls,
                    "operation_durations_ms": {
                        **state.get("operation_durations_ms", {}),
                        "local_generation": round((perf_counter() - started) * 1000),
                    },
                }
            except Exception as exc:
                if state.get("mode") != "combined":
                    raise dependency_unavailable("Local answer generation is unavailable.") from exc
                failure = (
                    "Local documentation generation is unavailable; the exact analytics "
                    "result and retrieved NASA sources remain available."
                )
                state = {
                    **state,
                    "failure": failure,
                    "generation_failure": failure,
                    "llm_calls": model_calls,
                    "operation_durations_ms": {
                        **state.get("operation_durations_ms", {}),
                        "local_generation": round((perf_counter() - started) * 1000),
                    },
                }
            else:
                state = {
                    **state,
                    "generated_answer": generated.answer,
                    "generated_cited_chunk_ids": generated.cited_chunk_ids,
                    "llm_calls": model_calls,
                    "operation_durations_ms": {
                        **state.get("operation_durations_ms", {}),
                        "local_generation": round((perf_counter() - started) * 1000),
                    },
                }
        response = self._compose_response(state)
        citation_started = perf_counter()
        traced_state: AgentState = {
            **state,
            "mode": response.mode,
            "accepted_citation_ids": [citation.chunk_id for citation in response.citations],
            "operation_durations_ms": {
                **state.get("operation_durations_ms", {}),
                "citation_validation": round((perf_counter() - citation_started) * 1000),
            },
        }
        if not (state.get("province_analytics") and response.mode == "analytics"):
            response = response.model_copy(
                update={"execution_trace": build_execution_trace(traced_state)}
            )
        response = ChatResponse.model_validate(response.model_dump())
        return {**traced_state, "response": response, "graph_steps": self._step(state)}

    @staticmethod
    def _validate_combined_generation(answer: str, state: AgentState) -> None:
        """Reject model prose that conflicts with server-owned analytics facts."""
        allowed_counts: set[int] = set()
        summary = state.get("analytics_result")
        if summary is not None:
            allowed_counts.update(point.count for point in summary.series)
            if summary.total is not None:
                allowed_counts.add(summary.total)
        province_analytics = state.get("province_analytics")
        if province_analytics is not None:
            result = province_analytics.get("result", {})
            if isinstance(result, dict):
                total = result.get("total")
                if isinstance(total, int):
                    allowed_counts.add(total)
                rows = result.get("rows", [])
                if isinstance(rows, list):
                    allowed_counts.update(
                        row["count"]
                        for row in rows
                        if isinstance(row, dict) and isinstance(row.get("count"), int)
                    )
        claimed_counts = {
            int(match.replace(",", ""))
            for match in re.findall(
                r"\b([0-9][0-9,]*)\s+(?:satellite\s+)?(?:hotspots?|detections?)\b",
                answer,
                re.IGNORECASE,
            )
        }
        if not claimed_counts <= allowed_counts:
            raise LocalModelError("combined answer attempted to alter an analytics count")

        ranking_or_ordering_claim = re.search(
            r"\b(?:rank(?:ed|ing)?(?:\s+(?:first|second|third|\d+))?|"
            r"highest\s+province|lowest\s+province|most\s+hotspots?|least\s+hotspots?|"
            r"(?:more|fewer|higher|lower)\s+(?:hotspot\s+)?"
            r"(?:hotspots?|detections?)\s+than|"
            r"followed\s+by)\b",
            answer,
            re.IGNORECASE,
        )
        if ranking_or_ordering_claim:
            raise LocalModelError(
                "combined answer attempted to restate server-owned province ordering"
            )

        expected_coverage: str | None = None
        if summary is not None:
            expected_coverage = (
                "complete"
                if summary.is_complete
                else "unavailable"
                if summary.total is None
                else "partial"
            )
        if province_analytics is not None:
            result = province_analytics.get("result", {})
            if isinstance(result, dict) and result.get("coverage_state") in {
                "complete",
                "partial",
                "unavailable",
            }:
                expected_coverage = str(result["coverage_state"])
        coverage_claims = {
            claim.casefold()
            for claim in re.findall(
                r"\b(?:analytics\s+|data\s+|requested\s+(?:period|range)\s+)?"
                r"coverage\s+(?:is|was)\s+(complete|partial|unavailable)\b",
                answer,
                re.IGNORECASE,
            )
        }
        if expected_coverage is not None and any(
            claim != expected_coverage for claim in coverage_claims
        ):
            raise LocalModelError("combined answer contradicted authoritative coverage state")
        if re.search(r"\bno\s+coverage\s+gaps?\b", answer, re.IGNORECASE) and (
            expected_coverage != "complete"
        ):
            raise LocalModelError("combined answer contradicted authoritative coverage gaps")

    def _compose_response(self, state: AgentState) -> ChatResponse:
        mode = state.get("mode", "unsupported")
        summary = state.get("analytics_result")
        province_analytics = state.get("province_analytics")
        year_comparison = state.get("year_comparison")
        passages = state.get("retrieved_passages", [])
        failure = state.get("failure")
        limitations = [HOTSPOT_CAVEAT]
        filters = None
        metrics = None
        chart = None
        citations: list[Citation] = []
        answer_parts: list[str] = []

        resolved = state.get("resolved_context")
        if (
            mode == "combined"
            and state.get("analytics_failure")
            and resolved is not None
            and resolved.date_from is not None
            and resolved.date_to is not None
        ):
            province_codes = list(resolved.province_codes)
            if not province_codes and resolved.province_code:
                province_codes = [resolved.province_code]
            if province_codes:
                filters = Filters(
                    province_codes=province_codes,
                    date_from=resolved.date_from,
                    date_to=resolved.date_to,
                )

        if mode == "unsupported":
            reason = state.get("plan_reason", "")
            if state.get("route_source") == "semantic_rejected":
                answer_parts.append(
                    "I am not confident which supported operation you mean. Please clarify "
                    "whether you want a hotspot count, comparison, province ranking, trend, "
                    "or a NASA documentation explanation, and include the province and date "
                    "range when asking for analytics."
                )
            elif "province" in reason or "date range" in reason or "year" in reason:
                answer_parts.append(
                    f"I need {reason.removeprefix('Analytics requires ').rstrip('.').lower()} "
                    "before I can query hotspot detections. Try: 'How many hotspot "
                    "detections were recorded in Riau during September 2023?'"
                )
            elif "No approved tool intent" in reason:
                answer_parts.append(
                    "I could not map that wording to a supported operation. Ask for a hotspot "
                    "count, comparison, province ranking, or an explanation of FIRMS, VIIRS, "
                    "FRP, confidence, or detection limitations."
                )
            else:
                answer_parts.append(UNSUPPORTED_ANSWER)
            limitations.append(state.get("plan_reason", "Request is outside approved v1 scope."))
        if summary is not None:
            filters = summary.filters
            metrics = [ChatMetric(name=summary.metric, value=summary.total, unit="detections")]
            chart = ChatChart(
                type="line", title="Monthly hotspot detections", series=summary.series
            )
            value = "unavailable" if summary.total is None else str(summary.total)
            answer_parts.append(
                f"The validated analytics result is {value} satellite hotspot detections "
                f"for {summary.filters.date_from.isoformat()} through "
                f"{summary.filters.date_to.isoformat()}."
            )
            limitations.extend(summary.warnings)
        if province_analytics is not None:
            result = province_analytics["result"]
            filters = Filters(
                province_codes=result.get("requested_province_codes", []),
                date_from=result["date_from"],
                date_to=result["date_to"],
            )
            if result["kind"] == "province_breakdown":
                metrics = [
                    ChatMetric(
                        name="satellite_hotspot_detections",
                        value=result["total"],
                        unit="detections",
                    )
                ]
                values = ", ".join(
                    f"{row['province_name']}: {row['count']}" for row in result["rows"]
                )
                answer_parts.append(
                    f"{values}. Combined total: {result['total']} hotspot detections "
                    f"from {result['date_from']} through {result['date_to']}."
                )
                comparison = result.get("comparison")
                if comparison:
                    names = {row["province_code"]: row["province_name"] for row in result["rows"]}
                    winners = ", ".join(
                        names[code] for code in comparison["highest_province_codes"]
                    )
                    answer_parts.append(
                        f"Highest: {winners}; difference between highest and lowest: "
                        f"{comparison['max_min_difference']} detections."
                    )
            else:
                top_value = result["rows"][0]["count"] if result["rows"] else None
                metrics = [
                    ChatMetric(
                        name="satellite_hotspot_detections", value=top_value, unit="detections"
                    )
                ]
                values = ", ".join(
                    f"{row['province_name']} (rank {row['dense_rank']}): {row['count']}"
                    for row in result["rows"]
                )
                answer_parts.append(
                    f"{result['direction'].title()} province ranking for "
                    f"{result['date_from']} through {result['date_to']}: "
                    f"{values or 'unavailable'}."
                )
            if result["coverage_state"] == "partial":
                limitations.append(
                    "Ranking and totals cover available observations only; "
                    "the requested period has coverage gaps."
                )
            limitations.append(
                "Observations not assigned to exactly one province are excluded "
                "from province values."
            )
        if year_comparison is not None:
            filters = Filters(
                province_codes=[year_comparison.province_code],
                date_from=date(year_comparison.years[0], 1, 1),
                date_to=date(year_comparison.years[-1], 12, 31),
            )
            metrics = [
                ChatMetric(
                    name=f"satellite_hotspot_detections_{point.year}",
                    value=point.count,
                    unit="detections",
                )
                for point in year_comparison.points
            ]
            values = ", ".join(
                f"{point.year}: {'unavailable' if point.count is None else point.count}"
                for point in year_comparison.points
            )
            answer_parts.append(f"Year-over-year hotspot detections: {values}.")
            if any(not point.is_complete for point in year_comparison.points):
                limitations.append(
                    "One or more years have unknown or unavailable dates; no percentage "
                    "or directional comparison was calculated."
                )
        if passages:
            cited_ids = state.get("generated_cited_chunk_ids")
            selected = (
                [item for item in passages if item.chunk_id in cited_ids] if cited_ids else passages
            )
            citations = []
            for item in selected:
                citations.append(Citation(title=item.title, url=item.url, chunk_id=item.chunk_id))
            answer_parts.append(
                state.get("generated_answer")
                or "Relevant official NASA documentation was retrieved; use the cited sources "
                "for the technical context."
            )
            limitations.append(
                "Retrieved document text is treated as untrusted evidence and cannot issue "
                "instructions."
            )
        branch_failures = [
            state.get("analytics_failure"),
            state.get("rag_failure"),
            state.get("generation_failure"),
        ]
        for branch_failure in branch_failures:
            if branch_failure:
                limitations.append(branch_failure)
        if failure and failure not in branch_failures:
            limitations.append(failure)
            if not answer_parts:
                answer_parts.append(
                    "I cannot answer reliably because required evidence is unavailable."
                )
        if (
            mode != "unsupported"
            and not summary
            and not province_analytics
            and not year_comparison
            and not passages
        ):
            mode = "unsupported"
            answer_parts.append(
                "I cannot answer reliably because required evidence is unavailable."
            )

        return ChatResponse(
            request_id=state["request_id"],
            answer=" ".join(dict.fromkeys(answer_parts)),
            mode=mode,
            filters=filters,
            metrics=metrics,
            chart=chart,
            map=None,
            citations=citations,
            limitations=list(dict.fromkeys(limitations)),
            usage=Usage(llm_calls=state.get("llm_calls", 0)),
            province_analytics=province_analytics,
            year_comparison=year_comparison,
        )


def build_production_graph(runtime: BoundedLangGraphRuntime):  # type: ignore[no-untyped-def]
    """Build the single bounded graph; tool nodes are deterministic adapters, not agents."""
    graph = StateGraph(AgentState)
    graph.add_node("plan", runtime.plan)
    graph.add_node("resolve_filters", runtime.resolve_filters)
    graph.add_node("analytics", runtime.analytics)
    graph.add_node("retrieve", runtime.retrieve)
    graph.add_node("compose", runtime.compose)
    graph.add_edge(START, "plan")
    graph.add_conditional_edges(
        "plan",
        runtime.route,
        {
            "analytics": "resolve_filters",
            "rag": "retrieve",
            "combined": "resolve_filters",
            "unsupported": "compose",
        },
    )
    graph.add_conditional_edges(
        "resolve_filters",
        lambda state: (
            "compose"
            if state["mode"] == "unsupported"
            else "retrieve"
            if state.get("skip_analytics")
            else "analytics"
        ),
        {"compose": "compose", "retrieve": "retrieve", "analytics": "analytics"},
    )
    graph.add_conditional_edges(
        "analytics",
        lambda state: "retrieve" if state["mode"] == "combined" else "compose",
        {"retrieve": "retrieve", "compose": "compose"},
    )
    graph.add_edge("retrieve", "compose")
    graph.add_edge("compose", END)
    return graph.compile()
