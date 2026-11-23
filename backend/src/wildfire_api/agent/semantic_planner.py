from __future__ import annotations

from wildfire_api.agent.intent_router import DeterministicIntentRouter
from wildfire_api.agent.semantic_intent import (
    SemanticIntent,
    SemanticIntentError,
    SemanticIntentIndex,
    SemanticRoutingMode,
)
from wildfire_api.agent.state import AgentPlan

_INTENT_MODES = {
    "single_province_count": "analytics",
    "multi_province_summary": "analytics",
    "province_comparison": "analytics",
    "province_ranking": "analytics",
    "monthly_trend": "analytics",
    "map_locations": "analytics",
    "documentation_semantics": "rag",
    "combined_analytics_documentation": "combined",
}


class GuardedSemanticPlanner:
    """Use semantic intent only after deterministic policy returns unrecognized."""

    def __init__(
        self,
        index: SemanticIntentIndex,
        *,
        mode: SemanticRoutingMode,
        router: DeterministicIntentRouter | None = None,
    ) -> None:
        if mode == "disabled":
            raise ValueError("disabled semantic routing must not construct a semantic planner")
        self._index = index
        self._mode = mode
        self._router = router or DeterministicIntentRouter()

    async def __call__(self, message: str) -> AgentPlan:
        deterministic = self._router.decide(message)
        if "unrecognized" not in deterministic.intent_codes:
            return AgentPlan(
                mode=deterministic.mode,
                reason=deterministic.reason,
                route_source="deterministic",
            )
        try:
            match = self._index.match(message)
        except SemanticIntentError:
            return AgentPlan(
                mode="unsupported",
                reason="Semantic routing is unavailable; safe fallback applied.",
                route_source="semantic_unavailable",
            )
        if not match.accepted or match.intent is None:
            return AgentPlan(
                mode="unsupported",
                reason="The request meaning is ambiguous; clarification is required.",
                route_source="semantic_rejected",
                semantic_intent=match.intent,
            )
        if self._mode == "shadow":
            return AgentPlan(
                mode="unsupported",
                reason=deterministic.reason,
                route_source="semantic_shadow",
                semantic_intent=match.intent,
            )
        intent: SemanticIntent = match.intent
        return AgentPlan(
            mode=_INTENT_MODES[intent],
            reason="A reviewed semantic intent matched an allowlisted operation.",
            route_source="semantic_guarded",
            semantic_intent=intent,
        )
