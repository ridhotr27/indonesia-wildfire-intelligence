import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from wildfire_api.agent.intent_models import EntityCandidate, IntentPlan
from wildfire_api.agent.intent_validator import IntentPlanRejected, IntentPlanValidator
from wildfire_api.agent.operation_registry import (
    CatalogCompatibilityError,
    OperationRegistry,
)

ROOT = Path(__file__).resolve().parents[3]
CATALOG = ROOT / "data/contracts/hotspot_semantic_catalog_v1.0.0.json"


def entity(kind: str, value: str | int | bool) -> dict[str, object]:
    return {"kind": kind, "value": value, "source": "current_message"}


def analytics_entities(*province_codes: str) -> tuple[EntityCandidate, ...]:
    raw = [
        entity("metric_id", "satellite_hotspot_detections"),
        entity("product_id", "VNP14IMG.002_SNPP_FIRMS_SP"),
        entity("date_from", "2023-09-01"),
        entity("date_to", "2023-09-30"),
        *(entity("province_code", code) for code in province_codes),
    ]
    return tuple(EntityCandidate.model_validate(item) for item in raw)


@pytest.fixture
def registry() -> OperationRegistry:
    return OperationRegistry.from_catalog(CATALOG)


@pytest.fixture
def validator(registry: OperationRegistry) -> IntentPlanValidator:
    return IntentPlanValidator(registry, CATALOG)


def test_registry_maps_every_allowlisted_operation_to_one_typed_adapter(
    registry: OperationRegistry,
) -> None:
    assert set(registry.definitions) == {
        "hotspot_summary_v1",
        "hotspot_trend_v1",
        "hotspot_multi_province_summary_v1",
        "hotspot_province_ranking_v1",
        "nasa_documentation_v1",
    }
    assert all(definition.adapter_id for definition in registry.definitions.values())
    assert "hotspot_map_v1" not in registry.definitions


@pytest.mark.parametrize("operation_id", ["hotspot_summary_v1", "hotspot_trend_v1"])
def test_single_province_operations_validate(
    validator: IntentPlanValidator, operation_id: str
) -> None:
    plan = IntentPlan(
        route="analytics",
        operation_ids=(operation_id,),
        entities=analytics_entities("11"),
    )
    validated = validator.validate(plan)
    assert validated.operations[0].adapter_id == "hotspot_analytics_tool"
    assert validated.operations[0].arguments.province_codes == ("11",)


def test_multi_province_and_comparison_validate(validator: IntentPlanValidator) -> None:
    plan = IntentPlan(
        route="analytics",
        operation_ids=("hotspot_multi_province_summary_v1",),
        entities=analytics_entities("11", "13")
        + (EntityCandidate(kind="comparison_requested", value=True, source="current_message"),),
    )
    operation = validator.validate(plan).operations[0]
    assert operation.adapter_id == "hotspot_province_analytics_tool"
    assert operation.arguments.comparison_requested is True


def test_ranking_operator_and_bounds_validate(validator: IntentPlanValidator) -> None:
    plan = IntentPlan(
        route="analytics",
        operation_ids=("hotspot_province_ranking_v1",),
        entities=analytics_entities()
        + tuple(
            EntityCandidate.model_validate(item)
            for item in (
                entity("direction", "highest"),
                entity("ranking_selection", "top_n"),
                entity("top_n", 5),
            )
        ),
    )
    assert validator.validate(plan).operations[0].arguments.top_n == 5


def test_nasa_and_combined_routes_validate(validator: IntentPlanValidator) -> None:
    rag = IntentPlan(
        route="rag",
        operation_ids=("nasa_documentation_v1",),
        documentation_topics=("FRP",),
        retrieval_query="What does FRP mean?",
    )
    assert validator.validate(rag).operations[0].adapter_id == "nasa_retrieval_tool"
    combined = IntentPlan(
        route="combined",
        operation_ids=("hotspot_summary_v1", "nasa_documentation_v1"),
        entities=analytics_entities("11"),
        documentation_topics=("hotspot interpretation",),
        retrieval_query="How should hotspot detections be interpreted?",
    )
    assert len(validator.validate(combined).operations) == 2


@pytest.mark.parametrize(
    ("kind", "value", "code"),
    [
        ("metric_id", "confirmed_fires", "invalid_metric"),
        ("product_id", "MODIS", "invalid_product"),
        ("province_code", "99", "invalid_province"),
        ("date_to", "2024-01-01", "invalid_date"),
        ("dimension", "sql_table", "invalid_dimension"),
    ],
)
def test_catalog_incompatible_entities_are_rejected(
    validator: IntentPlanValidator, kind: str, value: str, code: str
) -> None:
    entities = list(analytics_entities("11"))
    entities = [item for item in entities if item.kind != kind]
    entities.append(EntityCandidate.model_validate(entity(kind, value)))
    plan = IntentPlan(
        route="analytics", operation_ids=("hotspot_summary_v1",), entities=tuple(entities)
    )
    with pytest.raises(IntentPlanRejected) as error:
        validator.validate(plan)
    assert error.value.code == code


@pytest.mark.parametrize(
    "payload",
    [
        {"route": "analytics", "operation_ids": ["drop_table"], "entities": []},
        {"route": "analytics", "operation_ids": ["hotspot_map_v1"], "entities": []},
        {
            "route": "analytics",
            "operation_ids": ["hotspot_summary_v1"],
            "entities": [],
            "sql": "DROP TABLE observations",
        },
        {
            "route": "rag",
            "operation_ids": ["nasa_documentation_v1"],
            "retrieval_query": "x",
            "answer": "invented",
        },
    ],
)
def test_unknown_operations_and_adversarial_fields_fail_schema(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        IntentPlan.model_validate(payload)


def test_required_forbidden_and_duplicate_slots_fail(validator: IntentPlanValidator) -> None:
    missing = IntentPlan(
        route="analytics",
        operation_ids=("hotspot_summary_v1",),
        entities=analytics_entities("11")[:-1],
    )
    with pytest.raises(IntentPlanRejected, match="missing required slots"):
        validator.validate(missing)

    forbidden = IntentPlan(
        route="analytics",
        operation_ids=("hotspot_summary_v1",),
        entities=analytics_entities("11")
        + (EntityCandidate(kind="top_n", value=2, source="current_message"),),
    )
    with pytest.raises(IntentPlanRejected) as error:
        validator.validate(forbidden)
    assert error.value.code == "forbidden_slot"

    duplicated = IntentPlan(
        route="analytics",
        operation_ids=("hotspot_summary_v1",),
        entities=analytics_entities("11")
        + (
            EntityCandidate(
                kind="product_id", value="VNP14IMG.002_SNPP_FIRMS_SP", source="ui_context"
            ),
        ),
    )
    with pytest.raises(IntentPlanRejected) as error:
        validator.validate(duplicated)
    assert error.value.code == "duplicate_entity"


@pytest.mark.parametrize(
    ("operation_id", "provinces", "extra_kind", "extra_value", "code"),
    [
        ("hotspot_summary_v1", ("11", "13"), None, None, "incompatible_operation"),
        ("hotspot_trend_v1", ("11",), "direction", "highest", "forbidden_slot"),
        ("hotspot_multi_province_summary_v1", ("11",), None, None, "incompatible_operation"),
        (
            "hotspot_multi_province_summary_v1",
            ("11", "13"),
            "ranking_selection",
            "top_n",
            "forbidden_slot",
        ),
        ("hotspot_province_ranking_v1", ("11",), "direction", "highest", "forbidden_slot"),
        (
            "hotspot_province_ranking_v1",
            (),
            "comparison_requested",
            True,
            "forbidden_slot",
        ),
    ],
)
def test_operation_slot_matrix_fails_closed(
    validator: IntentPlanValidator,
    operation_id: str,
    provinces: tuple[str, ...],
    extra_kind: str | None,
    extra_value: str | bool | None,
    code: str,
) -> None:
    entities = analytics_entities(*provinces)
    if operation_id == "hotspot_province_ranking_v1" and extra_kind != "direction":
        entities += (
            EntityCandidate(kind="direction", value="highest", source="current_message"),
            EntityCandidate(kind="ranking_selection", value="top_n", source="current_message"),
            EntityCandidate(kind="top_n", value=1, source="current_message"),
        )
    if extra_kind is not None:
        entities += (EntityCandidate.model_validate(entity(extra_kind, extra_value)),)
    plan = IntentPlan(route="analytics", operation_ids=(operation_id,), entities=entities)
    with pytest.raises(IntentPlanRejected) as error:
        validator.validate(plan)
    assert error.value.code == code


def test_invalid_ranking_and_deterministic_denial_fail_closed(
    validator: IntentPlanValidator,
) -> None:
    ranking = IntentPlan(
        route="analytics",
        operation_ids=("hotspot_province_ranking_v1",),
        entities=analytics_entities()
        + (EntityCandidate(kind="direction", value="highest", source="current_message"),),
    )
    with pytest.raises(IntentPlanRejected) as error:
        validator.validate(ranking)
    assert error.value.code == "invalid_operator"
    with pytest.raises(IntentPlanRejected) as denied:
        validator.validate(ranking, deterministic_denied=True)
    assert denied.value.code == "deterministic_denial"


def test_catalog_version_mismatch_fails_closed(tmp_path: Path) -> None:
    catalog = json.loads(CATALOG.read_text())
    catalog["catalog_version"] = "future-version"
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(catalog))
    with pytest.raises(CatalogCompatibilityError, match="unsupported"):
        OperationRegistry.from_catalog(path)


def test_models_have_no_execution_or_reasoning_escape_fields() -> None:
    schema = json.dumps(IntentPlan.model_json_schema()).casefold()
    for forbidden in ("sql", "table_name", "tool_name", "chain_of_thought", "confidence"):
        assert forbidden not in schema
