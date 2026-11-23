"""Strict, versioned models for the LIR-01 intent-routing evaluation corpus."""

from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PRODUCT_ID = "VNP14IMG.002_SNPP_FIRMS_SP"
METRIC_ID = "satellite_hotspot_detections"

Language = Literal["en", "id", "mixed"]
Partition = Literal["development", "shadow_validation", "final_holdout"]
Route = Literal["analytics", "rag", "combined", "clarification", "unsupported"]
OperationId = Literal[
    "hotspot_summary_v1",
    "hotspot_trend_v1",
    "hotspot_map_v1",
    "hotspot_multi_province_summary_v1",
    "hotspot_province_ranking_v1",
    "nasa_documentation_v1",
]


class StrictFrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CorpusUiContext(StrictFrozenModel):
    province_code: str | None = Field(default=None, pattern=r"^\d{2}$")
    date_from: date | None = None
    date_to: date | None = None

    @model_validator(mode="after")
    def dates_are_complete_and_ordered(self) -> CorpusUiContext:
        if (self.date_from is None) != (self.date_to is None):
            raise ValueError("UI context dates must both be present or absent")
        if self.date_from and self.date_to and self.date_to < self.date_from:
            raise ValueError("UI context dates must be ordered")
        return self


class CorpusHistoryTurn(StrictFrozenModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=500)


class ExpectedEntities(StrictFrozenModel):
    product_id: Literal["VNP14IMG.002_SNPP_FIRMS_SP"] | None = None
    metric_id: Literal["satellite_hotspot_detections"] | None = None
    province_codes: tuple[str, ...] = Field(default=(), max_length=38)
    date_from: date | None = None
    date_to: date | None = None
    direction: Literal["highest", "lowest"] | None = None
    top_n: int | None = Field(default=None, ge=1, le=38)
    comparison_requested: bool = False
    coverage_expectation: Literal["complete", "partial", "unavailable"] | None = None
    ranking_selection: Literal["top_n", "all", "zero_count"] | None = None
    tie_policy: Literal["dense_rank_include_cutoff_ties"] | None = None
    geography_scope: Literal["assigned_only", "assigned_plus_unassigned_reported"] | None = None
    documentation_topics: tuple[str, ...] = Field(default=(), max_length=5)
    provenance: tuple[Literal["current_message", "ui_context", "user_history"], ...] = Field(
        default=(), max_length=3
    )

    @model_validator(mode="after")
    def entity_shape_is_consistent(self) -> ExpectedEntities:
        if any(not re.fullmatch(r"\d{2}", code) for code in self.province_codes):
            raise ValueError("province codes must be canonical two-digit strings")
        if len(self.province_codes) != len(set(self.province_codes)):
            raise ValueError("province codes must be unique and ordered")
        if (self.date_from is None) != (self.date_to is None):
            raise ValueError("expected dates must both be present or absent")
        if self.date_from and self.date_to and self.date_to < self.date_from:
            raise ValueError("expected dates must be ordered")
        return self


class ExpectedCallBoundary(StrictFrozenModel):
    analytics_calls: int = Field(ge=0, le=1)
    retrieval_calls: int = Field(ge=0, le=1)
    generation_calls: int = Field(ge=0, le=1)
    planner_calls: dict[Literal["A", "B", "C", "D"], int]
    forbidden_tool_calls: Literal[0] = 0

    @model_validator(mode="after")
    def all_variants_are_labeled(self) -> ExpectedCallBoundary:
        if set(self.planner_calls) != {"A", "B", "C", "D"}:
            raise ValueError("planner call labels must cover A, B, C, and D")
        if any(value not in {0, 1} for value in self.planner_calls.values()):
            raise ValueError("planner call counts must be zero or one")
        return self


class TruthReference(StrictFrozenModel):
    kind: Literal[
        "data_contract",
        "query_catalog",
        "nasa_manifest",
        "routing_policy",
        "contract_fixture",
    ]
    source_paths: tuple[str, ...] = Field(min_length=1, max_length=4)
    reference_query_ids: tuple[str, ...] = Field(default=(), max_length=3)
    numeric_result_claimed: Literal[False] = False


class Lir01Case(StrictFrozenModel):
    id: str = Field(pattern=r"^lir01\.[a-z0-9_.-]{4,100}$")
    semantic_family_id: str = Field(pattern=r"^[a-z0-9_.-]{4,100}$")
    category: Literal[
        "analytics",
        "nasa_rag",
        "combined",
        "multi_turn",
        "ambiguous_clarification",
        "unsupported_adversarial",
    ]
    intent: Literal[
        "single_province_count",
        "monthly_trend",
        "multi_province_summary",
        "province_ranking",
        "documentation_semantics",
        "combined_analytics_documentation",
        "clarification",
        "unsupported",
    ]
    language: Language
    difficulty: Literal["standard", "paraphrased", "implicit", "adversarial"]
    partition: Partition
    current_message: str = Field(min_length=2, max_length=500)
    product_id: Literal["VNP14IMG.002_SNPP_FIRMS_SP"] = PRODUCT_ID
    ui_context: CorpusUiContext = CorpusUiContext()
    history: tuple[CorpusHistoryTurn, ...] = Field(default=(), max_length=4)
    expected_route: Route
    expected_operation_ids: tuple[OperationId, ...] = Field(default=(), max_length=2)
    expected_entities: ExpectedEntities
    expected_reason_code: str = Field(min_length=2, max_length=80)
    expected_calls: ExpectedCallBoundary
    truth_reference: TruthReference
    safety_tags: tuple[str, ...] = Field(default=(), max_length=6)
    review_status: Literal["reviewed"] = "reviewed"
    reviewer_roles: tuple[Literal["backend_engineer", "data_engineer"], ...] = Field(
        min_length=1, max_length=2
    )

    @model_validator(mode="after")
    def route_matches_operations_and_calls(self) -> Lir01Case:
        analytics_ops = {
            "hotspot_summary_v1",
            "hotspot_trend_v1",
            "hotspot_map_v1",
            "hotspot_multi_province_summary_v1",
            "hotspot_province_ranking_v1",
        }
        has_analytics = any(item in analytics_ops for item in self.expected_operation_ids)
        has_rag = "nasa_documentation_v1" in self.expected_operation_ids
        if has_analytics != (self.expected_route in {"analytics", "combined"}):
            raise ValueError("analytics operation must match expected route")
        if has_rag != (self.expected_route in {"rag", "combined"}):
            raise ValueError("NASA operation must match expected route")
        if self.expected_calls.analytics_calls != int(has_analytics):
            raise ValueError("analytics call boundary must match operations")
        if self.expected_calls.retrieval_calls != int(has_rag):
            raise ValueError("retrieval call boundary must match operations")
        if self.expected_calls.generation_calls != int(has_rag):
            raise ValueError("generation call boundary must match NASA generation")
        if self.category == "multi_turn" and not self.history:
            raise ValueError("multi-turn cases require explicit bounded history")
        if self.category != "multi_turn" and self.history:
            raise ValueError("history is limited to multi-turn cases")
        return self


class Lir01Corpus(StrictFrozenModel):
    schema_version: Literal["1.0.0"]
    dataset_version: Literal["lir01-intent-routing-corpus-v1.0.0"]
    generated_from: Literal["reviewed synthetic template families; no production chats"]
    product_id: Literal["VNP14IMG.002_SNPP_FIRMS_SP"]
    supported_window: tuple[date, date]
    known_unavailable_dates: tuple[date, date]
    cases: tuple[Lir01Case, ...] = Field(min_length=800)

    @model_validator(mode="after")
    def corpus_identity_and_ids_are_valid(self) -> Lir01Corpus:
        if self.supported_window != (date(2023, 1, 1), date(2023, 12, 31)):
            raise ValueError("supported window must match D04")
        if self.known_unavailable_dates != (date(2023, 7, 26), date(2023, 7, 27)):
            raise ValueError("known unavailable dates must match D04")
        identifiers = [case.id for case in self.cases]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("case IDs must be unique")
        normalized = [
            "|".join(
                [
                    " ".join(case.current_message.casefold().split()),
                    *(" ".join(turn.content.casefold().split()) for turn in case.history),
                ]
            )
            for case in self.cases
        ]
        if len(normalized) != len(set(normalized)):
            raise ValueError("case message/history signatures must be unique after normalization")
        family_partitions: dict[str, set[Partition]] = {}
        for case in self.cases:
            family_partitions.setdefault(case.semantic_family_id, set()).add(case.partition)
        if any(len(partitions) != 1 for partitions in family_partitions.values()):
            raise ValueError("a semantic family must not cross partitions")
        return self
