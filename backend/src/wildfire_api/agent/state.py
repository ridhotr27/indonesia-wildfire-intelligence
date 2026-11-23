from datetime import date
from typing import Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from wildfire_api.agent.filter_resolver import ResolvedChatContext
from wildfire_api.agent.intent_models import ValidatedPlan
from wildfire_api.rag.models import RetrievedPassage
from wildfire_api.schemas.chat import ChatResponse
from wildfire_api.schemas.hotspots import SummaryResponse, YearComparisonResponse

AgentMode = Literal["analytics", "rag", "combined", "unsupported"]
SemanticIntent = Literal[
    "single_province_count",
    "multi_province_summary",
    "province_comparison",
    "province_ranking",
    "monthly_trend",
    "map_locations",
    "documentation_semantics",
    "combined_analytics_documentation",
]


class AgentPlan(BaseModel):
    """Validated planner output; model-produced dictionaries never reach tools directly."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: AgentMode
    reason: str = Field(min_length=1, max_length=240)
    route_source: Literal[
        "deterministic",
        "semantic_shadow",
        "semantic_guarded",
        "semantic_rejected",
        "semantic_unavailable",
    ] = "deterministic"
    semantic_intent: SemanticIntent | None = None


class AnalyticsToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    product_id: str
    province_code: str
    date_from: date
    date_to: date


class ProvinceAnalyticsToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    product_id: str
    province_codes: tuple[str, ...] = Field(default=(), max_length=38)
    date_from: date
    date_to: date
    operation: Literal["multi_province", "ranking"]
    direction: Literal["highest", "lowest"] = "highest"
    top_n: int = Field(default=1, ge=1, le=38)
    comparison_requested: bool = False


class YearComparisonToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    product_id: str
    province_code: str
    years: tuple[int, ...] = Field(min_length=2, max_length=3)


class RetrievalToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=5)


class AgentState(TypedDict, total=False):
    request_id: str
    message: str
    documentation_query: str
    product_id: str
    province_code: str | None
    province_codes: tuple[str, ...]
    date_from: date | None
    date_to: date | None
    mode: AgentMode
    plan_reason: str
    route_source: str
    semantic_intent: SemanticIntent | None
    graph_steps: int
    tool_calls: int
    max_graph_steps: int
    max_tool_calls: int
    workflow_deadline: float
    analytics_result: SummaryResponse | None
    retrieved_passages: list[RetrievedPassage]
    response: ChatResponse
    failure: str | None
    analytics_failure: str
    rag_failure: str
    generation_failure: str
    skip_analytics: bool
    generated_answer: str
    generated_cited_chunk_ids: list[str]
    llm_calls: int
    resolved_context: ResolvedChatContext
    operation_durations_ms: dict[str, int]
    analytics_tool_input: AnalyticsToolInput
    province_analytics_tool_input: ProvinceAnalyticsToolInput
    province_analytics: dict[str, object]
    year_comparison_tool_input: YearComparisonToolInput
    year_comparison: YearComparisonResponse
    retrieval_tool_input: RetrievalToolInput
    retrieval_embedding_model: str
    retrieval_collection: str
    generation_model: str
    accepted_citation_ids: list[str]
    validated_plan: ValidatedPlan
