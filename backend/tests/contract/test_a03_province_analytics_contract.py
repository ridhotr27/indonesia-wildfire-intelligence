import copy
import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from wildfire_api.contracts.api_v1_2_proposal import (
    ChatResponseV1_2Proposal,
    ProvinceBreakdownResult,
    ProvinceRankingResult,
)
from wildfire_api.contracts.openapi_v1_2_proposal import build_openapi_v1_2_proposal

ROOT = Path(__file__).parents[3]
FIXTURE_PATH = ROOT / "docs/fixtures/api_contract_v1.2.0.province_analytics.fixture.json"
SNAPSHOT_PATH = ROOT / "docs/openapi/api_v1.2.0-proposal.openapi.json"
EDGE_FIXTURE_PATH = ROOT / "docs/fixtures/api_contract_v1.2.0.province_analytics.edge.fixture.json"
MAX_SAFE_INTEGER = 9_007_199_254_740_991


def _nested_parent(payload: dict[str, object], path: tuple[object, ...]) -> tuple[object, object]:
    current: object = payload
    for segment in path[:-1]:
        current = current[segment]  # type: ignore[index]
    return current, path[-1]


def _delete_nested(payload: dict[str, object], path: tuple[object, ...]) -> None:
    parent, key = _nested_parent(payload, path)
    del parent[key]  # type: ignore[index]


def _set_nested(payload: dict[str, object], path: tuple[object, ...], value: object) -> None:
    parent, key = _nested_parent(payload, path)
    parent[key] = value  # type: ignore[index]


@pytest.fixture(scope="module")
def fixture() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_all_a03_fixtures_and_old_contracts_validate(fixture: dict[str, object]) -> None:
    cases = [value for key, value in fixture.items() if key.startswith("chat_")]
    assert len(cases) >= 9
    for case in cases:
        ChatResponseV1_2Proposal.model_validate(case)
    old_v1 = json.loads(
        (ROOT / "docs/fixtures/api_contract_v1.0.0.fixture.json").read_text(encoding="utf-8")
    )
    old_v1_1 = json.loads(
        (ROOT / "docs/fixtures/api_contract_v1.1.0.execution_trace.fixture.json").read_text(
            encoding="utf-8"
        )
    )
    assert "province_analytics" not in old_v1["chat"]
    ChatResponseV1_2Proposal.model_validate(old_v1["chat"])
    for name in ("chat_analytics", "chat_rag", "chat_combined", "chat_abstention"):
        ChatResponseV1_2Proposal.model_validate(old_v1_1[name])


@pytest.mark.parametrize(
    ("case_name", "mutation"),
    [
        ("chat_two_province_complete", "extra"),
        ("chat_two_province_complete", "duplicate"),
        ("chat_two_province_complete", "sum"),
        ("chat_top_5_cutoff_tie", "rank"),
        ("chat_top_5_cutoff_tie", "order"),
        ("chat_top_5_cutoff_tie", "rows"),
        ("chat_partial_ranking", "coverage"),
        ("chat_wholly_unavailable_ranking", "unavailable"),
        ("chat_highest_top_1", "trace"),
        ("chat_highest_top_1", "filters"),
    ],
)
def test_invalid_cross_field_payloads_fail_closed(
    fixture: dict[str, object], case_name: str, mutation: str
) -> None:
    payload = copy.deepcopy(fixture[case_name])
    analytics = payload["province_analytics"]
    result = analytics["result"]
    if mutation == "extra":
        result["raw_sql"] = "forbidden"
    elif mutation == "duplicate":
        result["rows"][1]["province_code"] = result["rows"][0]["province_code"]
    elif mutation == "sum":
        result["total"] = 999
    elif mutation == "rank":
        result["rows"][1]["dense_rank"] = 7
    elif mutation == "order":
        result["rows"][0], result["rows"][1] = result["rows"][1], result["rows"][0]
    elif mutation == "rows":
        analytics["execution"]["returned_rows"] = 38
    elif mutation == "coverage":
        result["coverage_state"] = "complete"
    elif mutation == "unavailable":
        result["rows"] = [
            {
                "province_code": "01",
                "province_name": "Synthetic Province A",
                "province_order": 1,
                "count": 0,
                "dense_rank": 1,
            }
        ]
    elif mutation == "trace":
        payload["execution_trace"] = copy.deepcopy(
            json.loads(
                (ROOT / "docs/fixtures/api_contract_v1.1.0.execution_trace.fixture.json").read_text(
                    encoding="utf-8"
                )
            )["chat_analytics"]["execution_trace"]
        )
    else:
        payload["filters"]["province_codes"] = ["01"]
    with pytest.raises(ValidationError):
        ChatResponseV1_2Proposal.model_validate(payload)


@pytest.mark.parametrize(
    ("case_name", "tag_path"),
    [
        ("chat_two_province_complete", ("result",)),
        ("chat_highest_top_1", ("result",)),
        ("chat_highest_top_1", ("result", "selection")),
        ("chat_two_province_complete", ("execution", "parameters")),
        ("chat_highest_top_1", ("execution", "parameters")),
        ("chat_highest_top_1", ("execution", "parameters", "selection")),
    ],
)
def test_a03_discriminated_unions_reject_missing_kind_tags(
    fixture: dict[str, object], case_name: str, tag_path: tuple[str, ...]
) -> None:
    payload = copy.deepcopy(fixture[case_name])
    tagged_object = payload["province_analytics"]
    for path_part in tag_path:
        tagged_object = tagged_object[path_part]
    del tagged_object["kind"]

    with pytest.raises(ValidationError, match="Unable to extract tag"):
        ChatResponseV1_2Proposal.model_validate(payload)


@pytest.mark.parametrize(
    ("case_name", "path"),
    [
        (
            "chat_two_province_complete",
            ("province_analytics", "result", "not_assigned_to_exactly_one_province_count"),
        ),
        (
            "chat_two_province_complete",
            ("province_analytics", "result", "rows", 0, "count"),
        ),
        ("chat_two_province_complete", ("province_analytics", "result", "total")),
        ("chat_two_province_complete", ("province_analytics", "result", "comparison")),
        ("chat_highest_top_1", ("province_analytics", "result", "cutoff_tie_count")),
        ("chat_two_province_complete", ("province_analytics", "execution", "metric_value")),
    ],
)
def test_nullable_a03_wire_fields_are_required(
    fixture: dict[str, object], case_name: str, path: tuple[object, ...]
) -> None:
    payload = copy.deepcopy(fixture[case_name])
    _delete_nested(payload, path)
    with pytest.raises(ValidationError, match="Field required"):
        ChatResponseV1_2Proposal.model_validate(payload)


def test_a03_rejects_one_character_province_codes(fixture: dict[str, object]) -> None:
    payload = copy.deepcopy(fixture["chat_three_province_comparison"])
    for path in (
        ("filters", "province_codes", 0),
        ("province_analytics", "result", "requested_province_codes", 0),
        ("province_analytics", "result", "rows", 0, "province_code"),
        ("province_analytics", "result", "comparison", "highest_province_codes", 0),
        ("province_analytics", "execution", "parameters", "province_codes", 0),
    ):
        _set_nested(payload, path, "1")
    with pytest.raises(ValidationError, match="String should have at least 2 characters"):
        ChatResponseV1_2Proposal.model_validate(payload)


@pytest.mark.parametrize(
    ("case_name", "path"),
    [
        (
            "chat_two_province_complete",
            ("province_analytics", "result", "not_assigned_to_exactly_one_province_count"),
        ),
        (
            "chat_two_province_complete",
            ("province_analytics", "result", "rows", 0, "count"),
        ),
        ("chat_two_province_complete", ("province_analytics", "result", "total")),
        (
            "chat_three_province_comparison",
            ("province_analytics", "result", "comparison", "max_min_difference"),
        ),
        ("chat_highest_top_1", ("province_analytics", "result", "rows", 0, "count")),
        ("chat_two_province_complete", ("province_analytics", "execution", "metric_value")),
    ],
)
def test_a03_rejects_public_counts_above_javascript_safe_integer(
    fixture: dict[str, object], case_name: str, path: tuple[object, ...]
) -> None:
    payload = copy.deepcopy(fixture[case_name])
    _set_nested(payload, path, MAX_SAFE_INTEGER + 1)
    with pytest.raises(ValidationError, match="less than or equal to 9007199254740991"):
        ChatResponseV1_2Proposal.model_validate(payload)


def test_dense_cutoff_ties_and_separate_geographic_exclusion(fixture: dict[str, object]) -> None:
    ranking = ChatResponseV1_2Proposal.model_validate(fixture["chat_top_5_cutoff_tie"])
    assert ranking.province_analytics is not None
    result = ranking.province_analytics.result
    assert len(result.rows) == 6
    assert [row.dense_rank for row in result.rows[-2:]] == [5, 5]
    breakdown = ChatResponseV1_2Proposal.model_validate(fixture["chat_two_province_complete"])
    assert breakdown.province_analytics is not None
    assert breakdown.province_analytics.result.not_assigned_to_exactly_one_province_count == 3


def test_ordinal_zero_all_38_and_unavailable_breakdown_edge_fixtures_validate() -> None:
    edge = json.loads(EDGE_FIXTURE_PATH.read_text(encoding="utf-8"))
    ProvinceRankingResult.model_validate(edge["ordinal_result"])
    ProvinceRankingResult.model_validate(edge["zero_count_result"])
    empty_zero = ProvinceRankingResult.model_validate(edge["zero_count_empty_result"])
    assert empty_zero.rows == [] and empty_zero.cutoff_tie_count is None
    empty_ordinal = ProvinceRankingResult.model_validate(edge["ordinal_no_match_result"])
    assert empty_ordinal.rows == [] and empty_ordinal.cutoff_tie_count is None
    assert len(ProvinceRankingResult.model_validate(edge["all_38_result"]).rows) == 38
    ProvinceBreakdownResult.model_validate(edge["unavailable_breakdown_result"])


def test_unavailable_comparison_preserves_request_and_top_n_cannot_truncate(
    fixture: dict[str, object],
) -> None:
    unavailable = copy.deepcopy(fixture["chat_two_province_complete"])
    result = unavailable["province_analytics"]["result"]
    result.update(
        coverage_state="unavailable",
        is_complete=False,
        coverage_issues=[
            {
                "date_utc": f"2023-09-{day:02d}",
                "coverage_status": "unknown",
                "evidence_url": None,
                "note": None,
            }
            for day in range(1, 31)
        ],
        not_assigned_to_exactly_one_province_count=None,
        total=None,
        comparison=None,
    )
    for row in result["rows"]:
        row["count"] = None
    unavailable["metrics"][0]["value"] = None
    execution = unavailable["province_analytics"]["execution"]
    execution["parameters"]["comparison_requested"] = True
    execution["metric_value"] = None
    ChatResponseV1_2Proposal.model_validate(unavailable)
    execution["parameters"]["comparison_requested"] = False
    ChatResponseV1_2Proposal.model_validate(unavailable)

    truncated = copy.deepcopy(fixture["chat_top_5_cutoff_tie"])
    truncated_rows = truncated["province_analytics"]["result"]["rows"]
    truncated["province_analytics"]["result"]["rows"] = truncated_rows[:1]
    truncated["province_analytics"]["execution"]["returned_rows"] = 1
    with pytest.raises(ValidationError):
        ChatResponseV1_2Proposal.model_validate(truncated)
    missing_tie = copy.deepcopy(fixture["chat_top_5_cutoff_tie"])
    missing_tie["province_analytics"]["result"]["rows"].pop()
    missing_tie["province_analytics"]["execution"]["returned_rows"] = 5
    with pytest.raises(ValidationError):
        ChatResponseV1_2Proposal.model_validate(missing_tie)


@pytest.mark.parametrize(
    "url",
    [
        "https://localhost/private",
        "https://foo.localhost/private",
        "https://local/private",
        "https://foo.local/private",
        "https://example.com./private",
        "https://foo..example.com/private",
        "https://./private",
        "https://127.0.0.1/private",
        "https://[::1]/private",
    ],
)
def test_proposal_rejects_non_public_or_root_like_https_hosts(
    fixture: dict[str, object], url: str
) -> None:
    payload = copy.deepcopy(fixture["chat_two_province_complete"])
    payload["province_analytics"]["result"]["source"]["url"] = url
    with pytest.raises(ValidationError):
        ChatResponseV1_2Proposal.model_validate(payload)


def test_proposal_openapi_snapshot_matches_generator() -> None:
    committed = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    assert committed == build_openapi_v1_2_proposal()
    assert committed["info"]["version"] == "1.2.0"
    schemas = committed["components"]["schemas"]
    assert "ProvinceBreakdownResult" in schemas
    assert "ProvinceRankingResult" in schemas
    assert "province_analytics" in schemas["ChatResponse"]["properties"]
    discriminated_members = (
        "ProvinceBreakdownResult",
        "ProvinceRankingResult",
        "TopNSelection",
        "OrdinalSelection",
        "RankLookupSelection",
        "AllProvincesSelection",
        "ZeroCountSelection",
        "MultiProvinceParameters",
        "ProvinceRankingParameters",
    )
    assert all("kind" in schemas[name]["required"] for name in discriminated_members)
    assert schemas["ProvinceCountRow"]["properties"]["province_code"]["pattern"] == r"^\d{2}$"
    assert schemas["ProvinceRankRow"]["properties"]["province_code"]["pattern"] == r"^\d{2}$"
    count_schema = schemas["ProvinceCountRow"]["properties"]["count"]["anyOf"][0]
    assert count_schema["maximum"] == MAX_SAFE_INTEGER
    assert schemas["ProvinceRankRow"]["properties"]["count"]["maximum"] == MAX_SAFE_INTEGER
    required_nullable_fields = {
        "ProvinceCountRow": {"count"},
        "ProvinceBreakdownResult": {
            "not_assigned_to_exactly_one_province_count",
            "total",
            "comparison",
        },
        "ProvinceRankingResult": {
            "not_assigned_to_exactly_one_province_count",
            "cutoff_tie_count",
        },
        "ProvinceAnalyticsExecution": {"metric_value"},
    }
    for schema_name, required_fields in required_nullable_fields.items():
        assert required_fields <= set(schemas[schema_name]["required"])


def test_fixture_has_no_forbidden_or_real_evidence_claims(fixture: dict[str, object]) -> None:
    serialized = json.dumps(fixture, separators=(",", ":")).lower()
    forbidden_keys = (
        "raw_sql",
        "sql_query",
        "prompt",
        "passage_body",
        "vector",
        "password",
        "authorization",
        "api_key",
        "query_id",
        "stack_trace",
        "filesystem_path",
    )
    assert not any(f'"{key}"' in serialized for key in forbidden_keys)
    assert not re.search(r"(?:/users/|/home/|[a-z]:\\\\|-----begin .*private key)", serialized)
    assert "synthetic contract values only" in serialized
    assert len(serialized.encode("utf-8")) < 100_000
