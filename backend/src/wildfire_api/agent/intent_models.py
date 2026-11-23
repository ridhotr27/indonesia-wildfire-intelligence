"""Strict internal contracts for untrusted intent-planner proposals."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Route = Literal["analytics", "rag", "combined", "clarification", "unsupported"]
OperationId = Literal[
    "hotspot_summary_v1",
    "hotspot_trend_v1",
    "hotspot_multi_province_summary_v1",
    "hotspot_province_ranking_v1",
    "nasa_documentation_v1",
]
EntityKind = Literal[
    "metric_id",
    "product_id",
    "province_code",
    "date_from",
    "date_to",
    "dimension",
    "direction",
    "ranking_selection",
    "top_n",
    "comparison_requested",
]
EntitySource = Literal["current_message", "ui_context"]
ClarificationCode = Literal[
    "missing_province",
    "missing_date_range",
    "missing_year",
    "ambiguous_province",
    "conflicting_scope",
    "ambiguous_operation",
]


class FrozenStrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EntityCandidate(FrozenStrictModel):
    kind: EntityKind
    value: str | int | bool
    source: EntitySource


class IntentPlan(FrozenStrictModel):
    route: Route
    operation_ids: tuple[OperationId, ...] = Field(default=(), max_length=5)
    entities: tuple[EntityCandidate, ...] = Field(default=(), max_length=48)
    documentation_topics: tuple[str, ...] = Field(default=(), max_length=8)
    retrieval_query: str | None = Field(default=None, min_length=1, max_length=500)
    clarification_codes: tuple[ClarificationCode, ...] = Field(default=(), max_length=6)

    @model_validator(mode="after")
    def shape_matches_route(self) -> IntentPlan:
        if len(self.operation_ids) != len(set(self.operation_ids)):
            raise ValueError("operation_ids must be unique")
        if len(self.clarification_codes) != len(set(self.clarification_codes)):
            raise ValueError("clarification_codes must be unique")
        if any(not topic.strip() or len(topic) > 120 for topic in self.documentation_topics):
            raise ValueError("documentation topics must contain 1-120 characters")
        analytics = [op for op in self.operation_ids if op != "nasa_documentation_v1"]
        has_nasa = "nasa_documentation_v1" in self.operation_ids
        if self.route == "analytics" and (not analytics or has_nasa):
            raise ValueError("analytics route requires only analytics operations")
        if self.route == "rag" and self.operation_ids != ("nasa_documentation_v1",):
            raise ValueError("rag route requires the NASA documentation operation")
        if self.route == "combined" and (not analytics or not has_nasa):
            raise ValueError("combined route requires analytics and NASA operations")
        if self.route in {"clarification", "unsupported"} and self.operation_ids:
            raise ValueError("non-executable routes cannot contain operations")
        if self.route == "clarification" and not self.clarification_codes:
            raise ValueError("clarification route requires a clarification code")
        if self.route != "clarification" and self.clarification_codes:
            raise ValueError("clarification codes require the clarification route")
        if self.route in {"rag", "combined"} and not self.retrieval_query:
            raise ValueError("documentation routes require a retrieval query")
        if self.route not in {"rag", "combined"} and self.retrieval_query is not None:
            raise ValueError("retrieval query is limited to documentation routes")
        if self.route not in {"rag", "combined"} and self.documentation_topics:
            raise ValueError("documentation topics are limited to documentation routes")
        return self


class OperationArguments(FrozenStrictModel):
    metric_id: str
    product_id: str
    province_codes: tuple[str, ...] = Field(default=(), max_length=38)
    date_from: date
    date_to: date
    dimensions: tuple[str, ...] = Field(default=(), max_length=4)
    direction: Literal["highest", "lowest"] | None = None
    ranking_selection: Literal["top_n"] | None = None
    top_n: int | None = Field(default=None, ge=1, le=38)
    comparison_requested: bool | None = None


class ValidatedOperation(FrozenStrictModel):
    operation_id: OperationId
    adapter_id: Literal[
        "hotspot_analytics_tool",
        "hotspot_province_analytics_tool",
        "nasa_retrieval_tool",
    ]
    arguments: OperationArguments | None
    retrieval_query: str | None = Field(default=None, min_length=1, max_length=500)


class ValidatedPlan(FrozenStrictModel):
    route: Literal["analytics", "rag", "combined"]
    operations: tuple[ValidatedOperation, ...] = Field(min_length=1, max_length=5)
