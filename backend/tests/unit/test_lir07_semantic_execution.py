from datetime import date

import pytest

from wildfire_api.agent.filter_resolver import ChatFilterResolver
from wildfire_api.agent.runtime import BoundedLangGraphRuntime
from wildfire_api.agent.semantic_execution import (
    SemanticExecutionGate,
    SemanticExecutionRejected,
)
from wildfire_api.agent.state import AgentPlan

PRODUCT = "VNP14IMG.002_SNPP_FIRMS_SP"


def _resolved(message: str):
    return ChatFilterResolver().resolve(message, province_code=None, date_from=None, date_to=None)


def test_semantic_comparison_requires_deterministic_slots_and_lir04_validation() -> None:
    message = "Aceh versus West Sumatra during September 2023"
    plan = SemanticExecutionGate().validate_analytics(
        message=message,
        product_id=PRODUCT,
        semantic_intent="province_comparison",
        resolved=_resolved(message),
        combined=False,
    )

    operation = plan.operations[0]
    assert operation.operation_id == "hotspot_multi_province_summary_v1"
    assert operation.arguments is not None
    assert operation.arguments.province_codes == ("11", "13")
    assert operation.arguments.date_from == date(2023, 9, 1)
    assert operation.arguments.date_to == date(2023, 9, 30)
    assert operation.arguments.comparison_requested is True


@pytest.mark.parametrize(
    ("product_id", "message", "intent"),
    [
        ("UNAPPROVED", "Aceh in September 2023", "single_province_count"),
        (PRODUCT, "Aceh and West Sumatra", "province_comparison"),
        (PRODUCT, "Map detections in Aceh in September 2023", "map_locations"),
    ],
)
def test_semantic_similarity_cannot_bypass_catalog_or_required_slots(
    product_id: str, message: str, intent: str
) -> None:
    with pytest.raises(SemanticExecutionRejected):
        SemanticExecutionGate().validate_analytics(
            message=message,
            product_id=product_id,
            semantic_intent=intent,
            resolved=_resolved(message),
            combined=False,
        )


def test_semantic_rag_uses_only_allowlisted_nasa_operation() -> None:
    plan = SemanticExecutionGate().validate_documentation("What does VIIRS confidence mean?")
    assert plan.route == "rag"
    assert [operation.operation_id for operation in plan.operations] == ["nasa_documentation_v1"]


@pytest.mark.parametrize(("number", "expected"), [("five", 5), ("lima", 5), ("3", 3)])
def test_ranking_word_numbers_remain_strictly_validated(number: str, expected: int) -> None:
    message = f"List the top {number} provinces by detection count for September 2023"
    plan = SemanticExecutionGate().validate_analytics(
        message=message,
        product_id=PRODUCT,
        semantic_intent="province_ranking",
        resolved=_resolved(message),
        combined=False,
    )

    arguments = plan.operations[0].arguments
    assert arguments is not None
    assert arguments.top_n == expected


@pytest.mark.asyncio
async def test_similarity_only_map_route_executes_no_analytics_tool() -> None:
    calls = 0

    async def planner(_: str) -> AgentPlan:
        return AgentPlan(
            mode="analytics",
            reason="semantic match",
            route_source="semantic_guarded",
            semantic_intent="map_locations",
        )

    async def analytics_tool(tool_input, request_id):
        nonlocal calls
        calls += 1
        raise AssertionError("analytics must not execute")

    runtime = BoundedLangGraphRuntime(
        analytics_tool=analytics_tool,
        retrieval_tool=None,
        planner=planner,
    )
    state = await runtime.invoke(
        {
            "request_id": "lir07-map-rejected",
            "message": "Map detections in Aceh during September 2023",
            "product_id": PRODUCT,
            "province_code": None,
            "date_from": None,
            "date_to": None,
        }
    )

    assert calls == 0
    assert state["response"].mode == "unsupported"
    assert state["failure"] == "No analytics query was executed."
