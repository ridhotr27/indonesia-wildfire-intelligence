"""Deterministic execution gate for accepted semantic route classifications."""

from __future__ import annotations

import re

from wildfire_api.agent.filter_resolver import ResolvedChatContext
from wildfire_api.agent.intent_models import EntityCandidate, IntentPlan, ValidatedPlan
from wildfire_api.agent.intent_validator import IntentPlanRejected, IntentPlanValidator
from wildfire_api.agent.operation_registry import OperationRegistry
from wildfire_api.agent.state import SemanticIntent


class SemanticExecutionRejected(ValueError):
    """A semantic route could not be converted into a safe executable plan."""


class SemanticExecutionGate:
    """Convert a route label plus deterministic slots into an LIR-04 plan.

    Similarity selects only a coarse route. Operation arguments always come from
    the deterministic resolver and must pass the server-owned allowlist validator.
    """

    def __init__(self, validator: IntentPlanValidator | None = None) -> None:
        registry = OperationRegistry.from_catalog()
        self._validator = validator or IntentPlanValidator(registry)
        self.metric_id = registry.metric_id
        self.product_id = registry.product_id

    def validate_documentation(self, message: str) -> ValidatedPlan:
        return self._validator.validate(
            IntentPlan(
                route="rag",
                operation_ids=("nasa_documentation_v1",),
                retrieval_query=message,
            )
        )

    def validate_analytics(
        self,
        *,
        message: str,
        product_id: str,
        semantic_intent: SemanticIntent,
        resolved: ResolvedChatContext,
        combined: bool,
    ) -> ValidatedPlan:
        if not resolved.date_from or not resolved.date_to:
            raise SemanticExecutionRejected("complete dates are required")
        if product_id != self.product_id:
            raise SemanticExecutionRejected("product is not approved by the semantic catalog")
        operation_id = self._operation_id(message, semantic_intent, resolved)
        entities = [
            EntityCandidate(kind="metric_id", value=self.metric_id, source="current_message"),
            EntityCandidate(kind="product_id", value=self.product_id, source="current_message"),
            EntityCandidate(
                kind="date_from", value=resolved.date_from.isoformat(), source="current_message"
            ),
            EntityCandidate(
                kind="date_to", value=resolved.date_to.isoformat(), source="current_message"
            ),
        ]
        entities.extend(
            EntityCandidate(kind="province_code", value=code, source="current_message")
            for code in resolved.province_codes
        )
        if operation_id == "hotspot_multi_province_summary_v1":
            entities.append(
                EntityCandidate(
                    kind="comparison_requested",
                    value=semantic_intent == "province_comparison",
                    source="current_message",
                )
            )
        elif operation_id == "hotspot_province_ranking_v1":
            lowest = bool(re.search(r"\b(lowest|least|bottom|paling\s+sedikit)\b", message, re.I))
            top_match = re.search(
                r"\b(?:top|bottom)\s+(\d+|one|two|three|four|five|"
                r"satu|dua|tiga|empat|lima)\b",
                message,
                re.I,
            )
            word_numbers = {
                "one": 1,
                "two": 2,
                "three": 3,
                "four": 4,
                "five": 5,
                "satu": 1,
                "dua": 2,
                "tiga": 3,
                "empat": 4,
                "lima": 5,
            }
            top_value = 1
            if top_match:
                token = top_match.group(1).casefold()
                top_value = int(token) if token.isdigit() else word_numbers[token]
            entities.extend(
                (
                    EntityCandidate(
                        kind="direction",
                        value="lowest" if lowest else "highest",
                        source="current_message",
                    ),
                    EntityCandidate(
                        kind="ranking_selection", value="top_n", source="current_message"
                    ),
                    EntityCandidate(
                        kind="top_n",
                        value=top_value,
                        source="current_message",
                    ),
                )
            )
        operations = (operation_id, "nasa_documentation_v1") if combined else (operation_id,)
        plan = IntentPlan(
            route="combined" if combined else "analytics",
            operation_ids=operations,
            entities=tuple(entities),
            retrieval_query=message if combined else None,
        )
        try:
            return self._validator.validate(plan)
        except IntentPlanRejected as exc:
            raise SemanticExecutionRejected(f"{exc.code}: {exc}") from exc

    @staticmethod
    def _operation_id(message: str, intent: SemanticIntent, resolved: ResolvedChatContext) -> str:
        if intent == "combined_analytics_documentation":
            if re.search(
                r"\b(which\s+province|top\s+\d+|bottom\s+\d+|highest|lowest|"
                r"most\s+hotspots?|least\s+hotspots?|provinsi\s+mana|terbanyak|tersedikit)\b",
                message,
                re.I,
            ):
                return "hotspot_province_ranking_v1"
            if len(resolved.province_codes) > 1:
                return "hotspot_multi_province_summary_v1"
            if re.search(r"\b(monthly|month by month|trend|bulanan|tren)\b", message, re.I):
                return "hotspot_trend_v1"
            if len(resolved.province_codes) == 1:
                return "hotspot_summary_v1"
            raise SemanticExecutionRejected("combined analytics operation is ambiguous")
        mapping = {
            "single_province_count": "hotspot_summary_v1",
            "monthly_trend": "hotspot_trend_v1",
            "multi_province_summary": "hotspot_multi_province_summary_v1",
            "province_comparison": "hotspot_multi_province_summary_v1",
            "province_ranking": "hotspot_province_ranking_v1",
        }
        operation_id = mapping.get(intent)
        if operation_id is None:
            raise SemanticExecutionRejected("semantic intent has no approved analytics operation")
        return operation_id
