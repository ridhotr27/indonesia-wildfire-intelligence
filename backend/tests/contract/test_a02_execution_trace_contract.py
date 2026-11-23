import copy
import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from wildfire_api.schemas.chat import ChatResponse

ROOT = Path(__file__).parents[3]
FIXTURE_PATH = ROOT / "docs/fixtures/api_contract_v1.1.0.execution_trace.fixture.json"
OLD_FIXTURE_PATH = ROOT / "docs/fixtures/api_contract_v1.0.0.fixture.json"
CASES = ("chat_analytics", "chat_rag", "chat_combined", "chat_abstention")


@pytest.fixture(scope="module")
def fixture() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_four_trace_fixtures_and_old_field_absent_fixture_validate(
    fixture: dict[str, object],
) -> None:
    assert fixture["api_version"] == "1.1.0"
    for name in CASES:
        ChatResponse.model_validate(fixture[name])
    old = json.loads(OLD_FIXTURE_PATH.read_text(encoding="utf-8"))
    assert "execution_trace" not in old["chat"]
    ChatResponse.model_validate(old["chat"])
    old["chat"]["execution_trace"] = None
    ChatResponse.model_validate(old["chat"])


@pytest.mark.parametrize("mutation", ["extra", "kind", "sequence", "steps", "items"])
def test_discriminators_unknown_fields_and_bounds_fail_closed(
    fixture: dict[str, object], mutation: str
) -> None:
    payload = copy.deepcopy(fixture["chat_rag"])
    trace = payload["execution_trace"]
    if mutation == "extra":
        trace["steps"][1]["details"]["raw_prompt"] = "forbidden"
    elif mutation == "kind":
        trace["steps"][1]["details"]["kind"] = "analytics_query"
    elif mutation == "sequence":
        trace["steps"][1]["sequence"] = 7
    elif mutation == "steps":
        trace["steps"] = trace["steps"] * 3
    else:
        trace["steps"][1]["details"]["items"] = trace["steps"][1]["details"]["items"] * 6
    with pytest.raises(ValidationError):
        ChatResponse.model_validate(payload)


def test_trace_cross_field_invariants(fixture: dict[str, object]) -> None:
    analytics = copy.deepcopy(fixture["chat_analytics"])
    analytics["execution_trace"]["steps"][2]["details"]["parameters"]["province_codes"] = ["14"]
    with pytest.raises(ValidationError, match="parameters must match"):
        ChatResponse.model_validate(analytics)

    rag = copy.deepcopy(fixture["chat_rag"])
    rag["citations"][0]["chunk_id"] = "not-retrieved"
    with pytest.raises(ValidationError, match="subset"):
        ChatResponse.model_validate(rag)


def test_fixture_has_no_forbidden_debug_or_credential_shaped_content(
    fixture: dict[str, object],
) -> None:
    serialized = json.dumps(fixture, separators=(",", ":")).lower()
    forbidden_keys = (
        "raw_sql",
        "sql_query",
        "prompt",
        "passage_body",
        "vector",
        "embedding_vector",
        "password",
        "authorization",
        "api_key",
        "client_ip",
        "stack_trace",
        "filesystem_path",
    )
    assert not any(f'"{key}"' in serialized for key in forbidden_keys)
    assert not re.search(r"(?:/users/|/home/|[a-z]:\\\\|-----begin .*private key)", serialized)
    assert len(serialized.encode("utf-8")) < 50_000
