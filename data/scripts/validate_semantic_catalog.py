#!/usr/bin/env python3
"""Validate LIR-02 catalog semantics and reconcile its independent truth artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from data.scripts.validate_data_contract import (
    ContractValidationError,
    validate_instance,
)

PRODUCT_ID = "VNP14IMG.002_SNPP_FIRMS_SP"
METRIC_ID = "satellite_hotspot_detections"
OPERATIONS = {
    "hotspot_summary_v1",
    "hotspot_trend_v1",
    "hotspot_multi_province_summary_v1",
    "hotspot_province_ranking_v1",
}
KNOWN_GAPS = {"2023-07-26", "2023-07-27"}


def normalize(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _expected_case_valid(rule_id: str, value: dict[str, Any]) -> bool:
    if rule_id == "metric_identity":
        return value.get("metric_id") == METRIC_ID
    if rule_id == "product_compatibility":
        return value.get("product_id") == PRODUCT_ID
    if rule_id == "coverage_null_zero":
        return (
            value.get("coverage_state") != "unavailable" or value.get("value") is None
        )
    if rule_id == "province_canonicalization":
        return (
            value.get("province_code") == "13" and value.get("term") == "West Sumatra"
        )
    if rule_id == "ranking_bounds":
        return value.get("selection") == "top_n" and 1 <= value.get("top_n", 0) <= 38
    if rule_id == "geography_assignment":
        return (
            value.get("status") not in {"unassigned", "multiple_match"}
            or value.get("province_code") is None
        )
    if rule_id == "safe_filtering":
        return value.get("field") in {
            "metric_id",
            "product_id",
            "province_codes",
            "date_from",
            "date_to",
            "direction",
            "ranking_selection",
        }
    if rule_id == "operation_slots":
        return (
            value.get("operation") != "hotspot_summary_v1"
            or value.get("province_count") == 1
        )
    raise ContractValidationError(f"unknown semantic rule: {rule_id}")


def validate_catalog(
    catalog: dict[str, Any],
    schema: dict[str, Any],
    provenance: dict[str, Any],
) -> None:
    validate_instance(catalog, schema, schema)
    if catalog["metric"]["id"] != METRIC_ID or catalog["product"]["id"] != PRODUCT_ID:
        raise ContractValidationError("catalog metric/product identity changed")
    if set(catalog["metric"]["valid_operations"]) != OPERATIONS:
        raise ContractValidationError(
            "catalog must map every current analytics operation"
        )
    if {item["id"] for item in catalog["operations"]} != OPERATIONS:
        raise ContractValidationError("operation definitions are incomplete")
    if set(catalog["coverage"]["known_unavailable_dates"]) != KNOWN_GAPS:
        raise ContractValidationError("known gap dates changed")

    approved = {
        item["canonical_code"]: item["canonical_name"]
        for item in provenance["crosswalk"]
    }
    provinces = catalog["geography"]["provinces"]
    actual = {item["code"]: item["canonical_name"] for item in provinces}
    if len(provinces) != 38 or actual != approved:
        raise ContractValidationError(
            "catalog provinces differ from approved 38-row crosswalk"
        )
    if [item["canonical_order"] for item in provinces] != list(range(1, 39)):
        raise ContractValidationError("canonical province order must be contiguous")

    alias_owner: dict[str, str] = {}
    for province in provinces:
        terms = [
            *province["labels"].values(),
            *(item["text"] for item in province["aliases"]),
        ]
        for term in terms:
            key = normalize(term)
            owner = alias_owner.setdefault(key, province["code"])
            if owner != province["code"]:
                raise ContractValidationError(f"province alias collision: {term}")
    if actual.get("91") != "Papua" or actual.get("92") != "Papua Barat":
        raise ContractValidationError(
            "Papua codes must follow the approved DE crosswalk"
        )

    metric_terms = [
        *catalog["metric"]["labels"].values(),
        *(item["text"] for item in catalog["metric"]["aliases"]),
    ]
    normalized_metric_terms = [normalize(term) for term in metric_terms]
    if len(normalized_metric_terms) != len(set(normalized_metric_terms)):
        raise ContractValidationError("metric labels and aliases must be unique")
    if any(not item.get("reason") for item in catalog["geography"]["ambiguous_scopes"]):
        raise ContractValidationError("ambiguous scopes require an explicit reason")

    safe_fields = {item["field"] for item in catalog["safe_retrieval_filter_fields"]}
    if safe_fields != {
        "metric_id",
        "product_id",
        "province_codes",
        "date_from",
        "date_to",
        "direction",
        "ranking_selection",
    }:
        raise ContractValidationError("safe retrieval filter allowlist changed")
    prohibited = {"sql", "table", "raw_table", "prompt", "vector", "access_token"}
    if safe_fields & prohibited:
        raise ContractValidationError("unsafe retrieval filter field published")


def validate_fixture(fixture: dict[str, Any]) -> None:
    if fixture["fixture_classification"] != "synthetic_semantic_edge_fixture":
        raise ContractValidationError("semantic fixture must remain visibly synthetic")
    rule_counts: Counter[tuple[str, bool]] = Counter()
    for case in fixture["semantic_cases"]:
        observed = _expected_case_valid(case["rule_id"], case["input"])
        if observed != case["expected_valid"]:
            raise ContractValidationError(
                f"semantic fixture label mismatch: {case['id']}"
            )
        rule_counts[(case["rule_id"], case["expected_valid"])] += 1
    rules = {case["rule_id"] for case in fixture["semantic_cases"]}
    if any(
        rule_counts[(rule, True)] != 1 or rule_counts[(rule, False)] != 1
        for rule in rules
    ):
        raise ContractValidationError(
            "every semantic rule needs one positive and negative case"
        )
    if set(fixture["scenario"]["province_counts_on_available_days"]) != {
        "11",
        "12",
        "13",
        "14",
        "15",
        "16",
        "17",
        "18",
        "19",
        "21",
        "31",
        "32",
        "33",
        "34",
        "35",
        "36",
        "51",
        "52",
        "53",
        "61",
        "62",
        "63",
        "64",
        "65",
        "71",
        "72",
        "73",
        "74",
        "75",
        "76",
        "81",
        "82",
        "91",
        "92",
        "93",
        "94",
        "95",
        "96",
    }:
        raise ContractValidationError(
            "synthetic truth fixture must cover all 38 provinces"
        )


def validate_results(
    catalog: dict[str, Any],
    fixture: dict[str, Any],
    results: dict[str, Any],
    d06: dict[str, Any],
) -> None:
    fixture_text = json.dumps(fixture, indent=2, ensure_ascii=False) + "\n"
    if results["fixture_sha256"] != hashlib.sha256(fixture_text.encode()).hexdigest():
        raise ContractValidationError("reference results fixture hash mismatch")
    by_id = {item["query_id"]: item for item in results["synthetic_edge_results"]}
    counts = fixture["scenario"]["province_counts_on_available_days"]
    order = {
        item["code"]: item["canonical_order"]
        for item in catalog["geography"]["provinces"]
    }

    maximum = max(counts.values())
    highest = sorted(
        (code for code, count in counts.items() if count == maximum), key=order.get
    )
    if [row["province_code"] for row in by_id["highest_tie"]["rows"]] != highest:
        raise ContractValidationError("highest tie result does not reconcile")
    zero_codes = sorted(
        (code for code, count in counts.items() if count == 0), key=order.get
    )
    if [
        row["province_code"] for row in by_id["covered_zero_tie"]["rows"]
    ] != zero_codes:
        raise ContractValidationError("covered zero result does not reconcile")
    if by_id["partial_riau_total"]["total"] != counts["14"]:
        raise ContractValidationError("partial available subtotal does not reconcile")
    unavailable = by_id["wholly_unavailable"]
    if unavailable["numeric_total_available"] or unavailable["total"] is not None:
        raise ContractValidationError("wholly unavailable range must remain null")
    if set(unavailable["unavailable_dates"]) != KNOWN_GAPS:
        raise ContractValidationError("unavailable result must use the known gaps")
    exclusion = by_id["national_geography_exclusion"]
    if exclusion["included_in_province_rows"]:
        raise ContractValidationError("null geography cannot enter province rows")

    verified = results["verified_snapshot_results"]
    full = d06["full_d05_batch"]
    expected = {
        "riau_september_2023": full["riau_september_2023"],
        "country_monthly_counts_2023": full["monthly_country_counts"],
        "observations": full["observations"],
        "unassigned": full["unassigned"],
        "multiple_match": full["multiple_match"],
    }
    for key, value in expected.items():
        if verified[key] != value:
            raise ContractValidationError(f"verified snapshot mismatch: {key}")
    if (
        verified["assigned"]
        != verified["observations"] - verified["not_assigned_to_exactly_one_province"]
    ):
        raise ContractValidationError(
            "assigned/geography exclusion reconciliation failed"
        )
    if verified["not_assigned_to_exactly_one_province"] != (
        verified["unassigned"] + verified["multiple_match"]
    ):
        raise ContractValidationError("national geography exclusion count mismatch")


def validate_sql(sql: str) -> None:
    required_parameters = {
        "{product_id:String}",
        "{date_from:Date}",
        "{date_to:Date}",
        "{province_codes:Array(String)}",
    }
    if not required_parameters <= set(re.findall(r"\{[^}]+\}", sql)):
        raise ContractValidationError("reference SQL parameter allowlist is incomplete")
    upper = sql.upper()
    if any(
        token in upper for token in ("INSERT ", "ALTER ", "DROP ", "CREATE ", "DELETE ")
    ):
        raise ContractValidationError("reference SQL must remain read-only")
    if "DE_HOTSPOT_OBSERVATIONS_V1" in upper:
        raise ContractValidationError("reference SQL cannot read DE-owned raw tables")


def load_and_validate(root: Path) -> dict[str, int]:
    catalog_path = root / "data/contracts/hotspot_semantic_catalog_v1.0.0.json"
    schema = json.loads(
        (
            root / "data/contracts/hotspot_semantic_catalog_v1.0.0.schema.json"
        ).read_text()
    )
    catalog = json.loads(catalog_path.read_text())
    fixture = json.loads(
        (
            root
            / "data/contracts/fixtures/hotspot_semantic_catalog_v1.0.0.fixture.json"
        ).read_text()
    )
    results = json.loads(
        (
            root
            / "data/contracts/reference/hotspot_semantic_reference_results_v1.0.0.json"
        ).read_text()
    )
    provenance = json.loads(
        (root / "data/provenance/d03b_reusable_boundary.json").read_text()
    )
    d06_path = root / "data/reports/d06_clickhouse_validation.json"
    d06 = json.loads(d06_path.read_text())
    if (
        results["verified_snapshot_results"]["source_sha256"]
        != hashlib.sha256(d06_path.read_bytes()).hexdigest()
    ):
        raise ContractValidationError("D06 evidence hash mismatch")
    validate_catalog(catalog, schema, provenance)
    validate_fixture(fixture)
    validate_results(catalog, fixture, results, d06)
    validate_sql(
        (
            root
            / "data/contracts/reference/hotspot_semantic_reference_queries_v1.0.0.sql"
        ).read_text(encoding="utf-8")
    )
    return {
        "provinces": len(catalog["geography"]["provinces"]),
        "operations": len(catalog["operations"]),
        "semantic_cases": len(fixture["semantic_cases"]),
        "synthetic_reference_results": len(results["synthetic_edge_results"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(
        json.dumps({"status": "passed", **load_and_validate(args.root)}, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
