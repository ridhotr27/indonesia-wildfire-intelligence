from datetime import date

import pytest
from pydantic import ValidationError

from wildfire_api.agent.context_resolution import (
    ContextResolutionError,
    ConversationContextResolver,
    PlanContextValidator,
    RetrievalRewriteValidator,
)
from wildfire_api.agent.intent_models import EntityCandidate, IntentPlan


def resolve(message: str, **overrides):
    values = {
        "province_code": None,
        "date_from": None,
        "date_to": None,
        **overrides,
    }
    return ConversationContextResolver().resolve(message, **values)


def analytics_plan(*entities: EntityCandidate) -> IntentPlan:
    return IntentPlan(
        route="analytics",
        operation_ids=("hotspot_summary_v1",),
        entities=entities,
    )


def test_current_message_overrides_ui_context_exactly() -> None:
    context = resolve(
        "How many hotspot detections in Aceh during September 2023?",
        province_code="13",
        date_from=date(2023, 1, 1),
        date_to=date(2023, 1, 31),
    )
    assert context.status == "resolved"
    assert context.province_codes == ("11",)
    assert context.province_source == "message"
    assert (context.date_from, context.date_to) == (date(2023, 9, 1), date(2023, 9, 30))
    assert context.date_source == "message"


def test_ui_context_fills_only_missing_current_values() -> None:
    context = resolve(
        "Show hotspot detections",
        province_code="11",
        date_from=date(2023, 9, 1),
        date_to=date(2023, 9, 30),
    )
    assert context.status == "resolved"
    assert context.province_codes == ("11",)
    assert context.province_source == "ui_context"
    assert context.date_source == "ui_context"


@pytest.mark.parametrize(
    "question",
    ["What about Aceh?", "And September 2023?", "Bagaimana dengan Aceh?", "Kalau di sana?"],
)
def test_history_dependent_follow_ups_clarify(question: str) -> None:
    context = resolve(
        question,
        province_code="13",
        date_from=date(2023, 9, 1),
        date_to=date(2023, 9, 30),
    )
    assert context.status == "needs_clarification"
    assert context.clarification_codes == ("ambiguous_reference",)


def test_standalone_negated_documentation_follow_up_keeps_its_topic() -> None:
    context = resolve("And why are hotspot detections not confirmed fires?")
    assert context.follow_up_frame is True
    assert context.clarification_codes != ("ambiguous_reference",)


def test_plan_entity_provenance_matches_canonical_context() -> None:
    context = resolve(
        "How many hotspot detections in Aceh during September 2023?",
        province_code="13",
        date_from=date(2023, 1, 1),
        date_to=date(2023, 1, 31),
    )
    plan = analytics_plan(
        EntityCandidate(
            kind="metric_id", value="satellite_hotspot_detections", source="current_message"
        ),
        EntityCandidate(kind="product_id", value="VNP14IMG.002_SNPP_FIRMS_SP", source="ui_context"),
        EntityCandidate(kind="province_code", value="11", source="current_message"),
        EntityCandidate(kind="date_from", value="2023-09-01", source="current_message"),
        EntityCandidate(kind="date_to", value="2023-09-30", source="current_message"),
    )
    PlanContextValidator().validate(
        plan,
        context,
        ui_product_id="VNP14IMG.002_SNPP_FIRMS_SP",
        ui_province_code="13",
        ui_date_from=date(2023, 1, 1),
        ui_date_to=date(2023, 1, 31),
    )


@pytest.mark.parametrize(
    "entity",
    [
        EntityCandidate(kind="province_code", value="13", source="ui_context"),
        EntityCandidate(kind="province_code", value="13", source="current_message"),
        EntityCandidate(kind="date_from", value="2023-01-01", source="ui_context"),
    ],
)
def test_conflicting_or_invented_provenance_is_rejected(entity: EntityCandidate) -> None:
    context = resolve(
        "How many hotspot detections in Aceh during September 2023?",
        province_code="13",
        date_from=date(2023, 1, 1),
        date_to=date(2023, 1, 31),
    )
    with pytest.raises(ContextResolutionError, match="provenance"):
        PlanContextValidator().validate(
            analytics_plan(entity),
            context,
            ui_product_id="VNP14IMG.002_SNPP_FIRMS_SP",
            ui_province_code="13",
            ui_date_from=date(2023, 1, 1),
            ui_date_to=date(2023, 1, 31),
        )


def test_unresolved_context_cannot_authorize_analytics() -> None:
    context = resolve("What about Aceh?")
    with pytest.raises(ContextResolutionError, match="cannot authorize"):
        PlanContextValidator().validate(
            analytics_plan(),
            context,
            ui_product_id="VNP14IMG.002_SNPP_FIRMS_SP",
            ui_province_code=None,
            ui_date_from=None,
            ui_date_to=None,
        )


def test_ranking_does_not_invent_or_require_a_selected_province() -> None:
    message = "Top 5 provinces with highest hotspot detections in September 2023"
    context = resolve(message)
    plan = IntentPlan(
        route="analytics",
        operation_ids=("hotspot_province_ranking_v1",),
        entities=(
            EntityCandidate(
                kind="metric_id",
                value="satellite_hotspot_detections",
                source="current_message",
            ),
            EntityCandidate(
                kind="product_id",
                value="VNP14IMG.002_SNPP_FIRMS_SP",
                source="ui_context",
            ),
            EntityCandidate(kind="date_from", value="2023-09-01", source="current_message"),
            EntityCandidate(kind="date_to", value="2023-09-30", source="current_message"),
            EntityCandidate(kind="direction", value="highest", source="current_message"),
            EntityCandidate(kind="ranking_selection", value="top_n", source="current_message"),
            EntityCandidate(kind="top_n", value=5, source="current_message"),
        ),
    )
    PlanContextValidator().validate(
        plan,
        context,
        ui_product_id="VNP14IMG.002_SNPP_FIRMS_SP",
        ui_province_code=None,
        ui_date_from=None,
        ui_date_to=None,
    )


def test_retrieval_rewrite_preserves_entities_negation_and_measurement() -> None:
    context = resolve("Why are VIIRS hotspot detections in Aceh not confirmed fires?")
    result = RetrievalRewriteValidator().validate(
        context.original_message,
        "Why are VIIRS hotspot detections in Aceh not confirmed fires according to NASA?",
        context,
    )
    assert result.accepted is True


@pytest.mark.parametrize(
    ("original", "rewritten", "reason"),
    [
        ("What does FRP mean?", "What does FRP mean in Aceh?", "added_entity"),
        ("What are hotspots in Aceh?", "What are hotspots?", "dropped_entity"),
        (
            "Why are hotspot detections not confirmed fires?",
            "Why are hotspot detections confirmed fires?",
            "changed_negation",
        ),
        ("What does FRP mean?", "What burned area does FRP measure?", "changed_measurement"),
        ("What does FRP mean?", "Explain cloud temperature", "topic_mismatch"),
        ("What does FRP mean?", "What does FRP mean in 2024?", "added_entity"),
        (
            "What were hotspot detections in September 2023?",
            "What were hotspot detections?",
            "dropped_entity",
        ),
    ],
)
def test_rewrite_cannot_add_drop_or_change_meaning(
    original: str, rewritten: str, reason: str
) -> None:
    result = RetrievalRewriteValidator().validate(original, rewritten, resolve(original))
    assert result.accepted is False
    assert result.reason == reason
    assert result.query is None


def test_ambiguous_follow_up_cannot_be_rewritten_from_hidden_history() -> None:
    context = resolve("What about Aceh?")
    result = RetrievalRewriteValidator().validate(
        context.original_message, "How many hotspot detections were in Aceh?", context
    )
    assert result.accepted is False
    assert result.reason == "ambiguous_reference"


def test_history_provenance_and_oversized_context_are_rejected() -> None:
    with pytest.raises(ValidationError):
        EntityCandidate(kind="province_code", value="11", source="user_history")
    with pytest.raises(ContextResolutionError, match="2000"):
        resolve("x" * 2_001)


def test_operator_cannot_be_invented_or_sourced_from_ui() -> None:
    context = resolve(
        "Show hotspot detections in Aceh during September 2023",
    )
    for candidate in (
        EntityCandidate(kind="direction", value="highest", source="current_message"),
        EntityCandidate(kind="top_n", value=5, source="current_message"),
        EntityCandidate(kind="comparison_requested", value=True, source="current_message"),
        EntityCandidate(kind="dimension", value="month_utc", source="ui_context"),
    ):
        with pytest.raises(ContextResolutionError):
            PlanContextValidator().validate(
                analytics_plan(candidate),
                context,
                ui_product_id="VNP14IMG.002_SNPP_FIRMS_SP",
                ui_province_code=None,
                ui_date_from=None,
                ui_date_to=None,
            )
