"""One-call local structured planner, isolated from the runtime graph."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import date
from time import perf_counter
from typing import Any, Literal

from pydantic import Field, ValidationError

from wildfire_api.agent.intent_models import FrozenStrictModel, IntentPlan, ValidatedPlan
from wildfire_api.agent.intent_validator import IntentPlanRejected, IntentPlanValidator
from wildfire_api.agent.operation_registry import OperationRegistry
from wildfire_api.llm.ollama import OllamaHttpClient

logger = logging.getLogger("wildfire_api.intent_planner")

PROMPT_VERSION = "lir05-intent-planner-v2"
PINNED_MODEL = "qwen2.5:1.5b"

PlannerReason = Literal[
    "accepted",
    "clarification",
    "unsupported",
    "disabled",
    "deterministic_denial",
    "timeout",
    "model_unavailable",
    "invalid_structured_output",
    "validation_rejected",
]


class PlannerContext(FrozenStrictModel):
    product_id: str
    province_code: str | None = None
    date_from: date | None = None
    date_to: date | None = None


class PlannerRequest(FrozenStrictModel):
    question: str = Field(min_length=1, max_length=2_000)
    context: PlannerContext
    policy_allows_planning: bool = True


class PlannerResult(FrozenStrictModel):
    reason: PlannerReason
    plan: IntentPlan | None = None
    validated_plan: ValidatedPlan | None = None
    model_calls: Literal[0, 1]
    duration_ms: float = Field(ge=0)
    rejection_codes: tuple[str, ...] = Field(default=(), max_length=8)
    prompt_version: Literal["lir05-intent-planner-v2"] = PROMPT_VERSION
    model: Literal["qwen2.5:1.5b"] = PINNED_MODEL


class OllamaStructuredIntentPlanner:
    def __init__(
        self,
        *,
        client: OllamaHttpClient,
        registry: OperationRegistry,
        validator: IntentPlanValidator,
        model: str = PINNED_MODEL,
        timeout_seconds: float = 8.0,
        max_tokens: int = 512,
        enabled: bool = False,
        transport: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        if model != PINNED_MODEL:
            raise ValueError(f"structured planner requires pinned model {PINNED_MODEL}")
        if not 0 < timeout_seconds <= 30:
            raise ValueError("planner timeout must be between 0 and 30 seconds")
        if not 128 <= max_tokens <= 1_024:
            raise ValueError("planner token limit must be between 128 and 1024")
        self._registry = registry
        self._validator = validator
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._max_tokens = max_tokens
        self._enabled = enabled
        self._transport = transport or client.post

    async def plan(self, request: PlannerRequest) -> PlannerResult:
        started = perf_counter()
        if not self._enabled:
            return self._result("disabled", started, model_calls=0)
        if not request.policy_allows_planning:
            return self._result("deterministic_denial", started, model_calls=0)
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(self._transport, "/api/chat", self._payload(request)),
                timeout=self._timeout_seconds,
            )
        except TimeoutError:
            return self._result("timeout", started, model_calls=1)
        except Exception:
            return self._result("model_unavailable", started, model_calls=1)
        try:
            plan = IntentPlan.model_validate_json(response["message"]["content"])
        except ValidationError as exc:
            codes = tuple(dict.fromkeys(f"pydantic:{error['type']}" for error in exc.errors()))
            return self._result(
                "invalid_structured_output",
                started,
                model_calls=1,
                rejection_codes=codes[:8],
            )
        except (KeyError, TypeError, ValueError):
            return self._result(
                "invalid_structured_output",
                started,
                model_calls=1,
                rejection_codes=("pydantic:response_shape",),
            )
        if plan.route == "clarification":
            return self._result("clarification", started, model_calls=1, plan=plan)
        if plan.route == "unsupported":
            return self._result("unsupported", started, model_calls=1, plan=plan)
        try:
            validated = self._validator.validate(plan)
        except IntentPlanRejected as exc:
            return self._result(
                "validation_rejected",
                started,
                model_calls=1,
                rejection_codes=(f"validator:{exc.code}",),
            )
        return self._result("accepted", started, model_calls=1, plan=plan, validated_plan=validated)

    def _payload(self, request: PlannerRequest) -> dict[str, Any]:
        operations = [
            {
                "id": item.operation_id,
                "route": item.route,
                "required": sorted(item.required_slots),
                "forbidden": sorted(item.forbidden_slots),
            }
            for item in self._registry.definitions.values()
        ]
        system = (
            "Classify only; never answer. Return one JSON object matching the schema. "
            "Use canonical catalog values and only entities present in the question or UI. "
            "Select exactly one compatible analytics operation, except combined also adds "
            "nasa_documentation_v1. Analytics has no retrieval/topics/clarification codes. "
            "RAG uses only nasa_documentation_v1, retrieval_query, and topics. Combined uses "
            "one analytics operation plus NASA retrieval. Clarification has no operations and "
            "at least one unique clarification code. Unsupported has no operations or codes. "
            "Hotspots are satellite detections, not confirmed fires or burned area."
        )
        examples = [
            {
                "route": "analytics",
                "operation_ids": ["hotspot_summary_v1"],
                "entities": [
                    {
                        "kind": "metric_id",
                        "value": self._registry.metric_id,
                        "source": "current_message",
                    },
                    {
                        "kind": "product_id",
                        "value": self._registry.product_id,
                        "source": "ui_context",
                    },
                    {"kind": "province_code", "value": "11", "source": "current_message"},
                    {"kind": "date_from", "value": "2023-09-01", "source": "current_message"},
                    {"kind": "date_to", "value": "2023-09-30", "source": "current_message"},
                ],
                "documentation_topics": [],
                "retrieval_query": None,
                "clarification_codes": [],
            },
            {
                "route": "rag",
                "operation_ids": ["nasa_documentation_v1"],
                "entities": [],
                "documentation_topics": ["FRP"],
                "retrieval_query": "What does FRP mean?",
                "clarification_codes": [],
            },
            {
                "route": "combined",
                "operation_ids": ["hotspot_summary_v1", "nasa_documentation_v1"],
                "entities": [
                    {
                        "kind": "metric_id",
                        "value": self._registry.metric_id,
                        "source": "current_message",
                    },
                    {
                        "kind": "product_id",
                        "value": self._registry.product_id,
                        "source": "ui_context",
                    },
                    {"kind": "province_code", "value": "11", "source": "current_message"},
                    {"kind": "date_from", "value": "2023-09-01", "source": "current_message"},
                    {"kind": "date_to", "value": "2023-09-30", "source": "current_message"},
                ],
                "documentation_topics": ["limitations"],
                "retrieval_query": "NASA hotspot limitations",
                "clarification_codes": [],
            },
            {
                "route": "clarification",
                "operation_ids": [],
                "entities": [],
                "documentation_topics": [],
                "retrieval_query": None,
                "clarification_codes": ["missing_province"],
            },
            {
                "route": "unsupported",
                "operation_ids": [],
                "entities": [],
                "documentation_topics": [],
                "retrieval_query": None,
                "clarification_codes": [],
            },
        ]
        operation_rules = {
            "hotspot_summary_v1": "one province,total",
            "hotspot_trend_v1": "one province,monthly series",
            "hotspot_multi_province_summary_v1": "2-38 provinces,optional comparison_requested",
            "hotspot_province_ranking_v1": "no province,direction+ranking_selection=top_n+top_n",
            "nasa_documentation_v1": "rag/combined only,retrieval_query required",
        }
        return {
            "model": self._model,
            "stream": False,
            "format": IntentPlan.model_json_schema(),
            "options": {"temperature": 0, "num_predict": self._max_tokens},
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "question": request.question,
                            "ui_context": request.context.model_dump(mode="json"),
                            "operations": operations,
                            "canonical": {
                                "metric_id": self._registry.metric_id,
                                "product_id": self._registry.product_id,
                                "province_codes": self._registry.province_codes,
                            },
                            "operation_rules": operation_rules,
                            "examples": examples,
                        },
                        separators=(",", ":"),
                    ),
                },
            ],
        }

    def _result(
        self,
        reason: PlannerReason,
        started: float,
        *,
        model_calls: Literal[0, 1],
        plan: IntentPlan | None = None,
        validated_plan: ValidatedPlan | None = None,
        rejection_codes: tuple[str, ...] = (),
    ) -> PlannerResult:
        result = PlannerResult(
            reason=reason,
            plan=plan,
            validated_plan=validated_plan,
            rejection_codes=rejection_codes,
            model_calls=model_calls,
            duration_ms=(perf_counter() - started) * 1_000,
        )
        logger.info(
            "intent_planner_complete",
            extra={
                "planner_reason": reason,
                "planner_duration_ms": round(result.duration_ms, 3),
                "planner_model_calls": model_calls,
                "planner_prompt_version": PROMPT_VERSION,
                "planner_rejection_codes": rejection_codes,
            },
        )
        return result
