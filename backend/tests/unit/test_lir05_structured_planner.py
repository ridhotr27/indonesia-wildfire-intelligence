import json
import logging
import time
from pathlib import Path

import pytest

from wildfire_api.agent.intent_models import IntentPlan
from wildfire_api.agent.intent_validator import IntentPlanValidator
from wildfire_api.agent.operation_registry import OperationRegistry
from wildfire_api.agent.structured_planner import (
    OllamaStructuredIntentPlanner,
    PlannerContext,
    PlannerRequest,
)
from wildfire_api.core.config import Settings
from wildfire_api.llm.ollama import LocalModelError, OllamaHttpClient

ROOT = Path(__file__).resolve().parents[3]
CATALOG = ROOT / "data/contracts/hotspot_semantic_catalog_v1.0.0.json"


def valid_plan() -> dict[str, object]:
    return {
        "route": "analytics",
        "operation_ids": ["hotspot_summary_v1"],
        "entities": [
            {
                "kind": "metric_id",
                "value": "satellite_hotspot_detections",
                "source": "current_message",
            },
            {
                "kind": "product_id",
                "value": "VNP14IMG.002_SNPP_FIRMS_SP",
                "source": "ui_context",
            },
            {"kind": "province_code", "value": "11", "source": "current_message"},
            {"kind": "date_from", "value": "2023-09-01", "source": "current_message"},
            {"kind": "date_to", "value": "2023-09-30", "source": "current_message"},
        ],
        "documentation_topics": [],
        "retrieval_query": None,
        "clarification_codes": [],
    }


def response(content: object) -> dict[str, object]:
    return {"message": {"content": content if isinstance(content, str) else json.dumps(content)}}


def request(*, allowed: bool = True) -> PlannerRequest:
    return PlannerRequest(
        question="How many hotspot detections were recorded in Aceh in September 2023?",
        context=PlannerContext(product_id="VNP14IMG.002_SNPP_FIRMS_SP"),
        policy_allows_planning=allowed,
    )


def planner(transport, **kwargs) -> OllamaStructuredIntentPlanner:
    registry = OperationRegistry.from_catalog(CATALOG)
    return OllamaStructuredIntentPlanner(
        client=OllamaHttpClient("http://127.0.0.1:11434"),
        registry=registry,
        validator=IntentPlanValidator(registry, CATALOG),
        enabled=True,
        transport=transport,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_valid_response_is_strictly_parsed_and_validated() -> None:
    calls = []

    def transport(path, payload):
        calls.append((path, payload))
        return response(valid_plan())

    result = await planner(transport).plan(request())
    assert result.reason == "accepted"
    assert result.model_calls == 1
    assert result.validated_plan.operations[0].adapter_id == "hotspot_analytics_tool"
    assert len(calls) == 1
    payload = calls[0][1]
    assert payload["options"] == {"temperature": 0, "num_predict": 512}
    assert payload["stream"] is False
    assert payload["format"]["additionalProperties"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [
        "not-json",
        {**valid_plan(), "answer": "invented"},
        {**valid_plan(), "operation_ids": ["unknown_tool"]},
        {**valid_plan(), "sql": "destructive statement"},
        {**valid_plan(), "retrieval_query": "x" * 501},
    ],
)
async def test_malformed_unknown_oversized_and_injection_outputs_fail_closed(content) -> None:
    result = await planner(lambda *_: response(content)).plan(request())
    assert result.reason == "invalid_structured_output"
    assert result.rejection_codes
    assert result.plan is None
    assert result.validated_plan is None


@pytest.mark.asyncio
async def test_catalog_validation_failure_does_not_authorize_operation() -> None:
    content = valid_plan()
    content["entities"][0]["value"] = "confirmed_fires"
    result = await planner(lambda *_: response(content)).plan(request())
    assert result.reason == "validation_rejected"
    assert result.rejection_codes == ("validator:invalid_metric",)
    assert result.plan is None
    assert result.validated_plan is None


@pytest.mark.asyncio
async def test_timeout_and_model_failure_are_safe() -> None:
    def slow(*_):
        time.sleep(0.05)
        return response(valid_plan())

    timed_out = await planner(slow, timeout_seconds=0.01).plan(request())
    assert timed_out.reason == "timeout"
    assert timed_out.validated_plan is None

    def unavailable(*_):
        raise LocalModelError("offline")

    failed = await planner(unavailable).plan(request())
    assert failed.reason == "model_unavailable"
    assert failed.validated_plan is None


@pytest.mark.asyncio
async def test_disabled_and_denied_paths_make_zero_model_calls() -> None:
    calls = 0

    def transport(*_):
        nonlocal calls
        calls += 1
        return response(valid_plan())

    instance = planner(transport)
    denied = await instance.plan(request(allowed=False))
    assert denied.reason == "deterministic_denial"
    assert denied.model_calls == 0
    registry = OperationRegistry.from_catalog(CATALOG)
    disabled = OllamaStructuredIntentPlanner(
        client=OllamaHttpClient("http://localhost:11434"),
        registry=registry,
        validator=IntentPlanValidator(registry, CATALOG),
        transport=transport,
    )
    assert (await disabled.plan(request())).reason == "disabled"
    assert calls == 0


@pytest.mark.asyncio
async def test_clarification_and_unsupported_are_non_executable() -> None:
    clarification = {
        "route": "clarification",
        "operation_ids": [],
        "entities": [],
        "documentation_topics": [],
        "retrieval_query": None,
        "clarification_codes": ["missing_province"],
    }
    result = await planner(lambda *_: response(clarification)).plan(request())
    assert result.reason == "clarification"
    assert result.validated_plan is None
    unsupported = {**clarification, "route": "unsupported", "clarification_codes": []}
    result = await planner(lambda *_: response(unsupported)).plan(request())
    assert result.reason == "unsupported"
    assert result.validated_plan is None


@pytest.mark.asyncio
async def test_calls_are_deterministic_and_logs_are_privacy_safe(caplog) -> None:
    payloads = []

    def transport(_, payload):
        payloads.append(payload)
        return response(valid_plan())

    instance = planner(transport)
    caplog.set_level(logging.INFO, logger="wildfire_api.intent_planner")
    first = await instance.plan(request())
    second = await instance.plan(request())
    assert payloads[0] == payloads[1]
    assert first.plan == second.plan
    log_text = caplog.text
    assert request().question not in log_text
    assert json.dumps(valid_plan()) not in log_text


def test_prompt_template_and_configuration_are_bounded() -> None:
    captured = {}

    def transport(_, payload):
        captured.update(payload)
        return response(valid_plan())

    instance = planner(transport)
    payload = instance._payload(request())
    template = payload["messages"][0]["content"].casefold()
    guidance = json.loads(payload["messages"][1]["content"])
    assert "sql" not in template
    assert guidance["canonical"]["metric_id"] == "satellite_hotspot_detections"
    assert guidance["canonical"]["product_id"] == "VNP14IMG.002_SNPP_FIRMS_SP"
    assert ["13", ["Sumatera Barat", "West Sumatra"]] in guidance["canonical"]["province_codes"]
    assert {example["route"] for example in guidance["examples"]} == {
        "analytics",
        "rag",
        "combined",
        "clarification",
        "unsupported",
    }
    for example in guidance["examples"]:
        IntentPlan.model_validate(example)
    assert guidance["operation_rules"]["hotspot_province_ranking_v1"].startswith("no province")
    assert "password" not in json.dumps(payload).casefold()
    assert Settings().intent_planning_mode == "disabled"
    with pytest.raises(ValueError, match="pinned model"):
        planner(transport, model="unapproved")
    with pytest.raises(ValueError, match="loopback"):
        OllamaHttpClient("https://remote.example")
