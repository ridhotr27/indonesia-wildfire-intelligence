#!/usr/bin/env python3
"""Build the versioned LIR-02 semantic catalog and reviewed truth artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "data" / "contracts"
FIXTURES = CONTRACTS / "fixtures"
REFERENCE = CONTRACTS / "reference"
PROVENANCE = ROOT / "data" / "provenance" / "d03b_reusable_boundary.json"

CATALOG_PATH = CONTRACTS / "hotspot_semantic_catalog_v1.0.0.json"
FIXTURE_PATH = FIXTURES / "hotspot_semantic_catalog_v1.0.0.fixture.json"
RESULTS_PATH = REFERENCE / "hotspot_semantic_reference_results_v1.0.0.json"

PRODUCT_ID = "VNP14IMG.002_SNPP_FIRMS_SP"
METRIC_ID = "satellite_hotspot_detections"

ENGLISH_NAMES = {
    "11": "Aceh",
    "12": "North Sumatra",
    "13": "West Sumatra",
    "14": "Riau",
    "15": "Jambi",
    "16": "South Sumatra",
    "17": "Bengkulu",
    "18": "Lampung",
    "19": "Bangka Belitung Islands",
    "21": "Riau Islands",
    "31": "Special Capital Region of Jakarta",
    "32": "West Java",
    "33": "Central Java",
    "34": "Special Region of Yogyakarta",
    "35": "East Java",
    "36": "Banten",
    "51": "Bali",
    "52": "West Nusa Tenggara",
    "53": "East Nusa Tenggara",
    "61": "West Kalimantan",
    "62": "Central Kalimantan",
    "63": "South Kalimantan",
    "64": "East Kalimantan",
    "65": "North Kalimantan",
    "71": "North Sulawesi",
    "72": "Central Sulawesi",
    "73": "South Sulawesi",
    "74": "Southeast Sulawesi",
    "75": "Gorontalo",
    "76": "West Sulawesi",
    "81": "Maluku",
    "82": "North Maluku",
    "91": "Papua",
    "92": "West Papua",
    "93": "South Papua",
    "94": "Central Papua",
    "95": "Highland Papua",
    "96": "Southwest Papua",
}

EXTRA_ALIASES = {
    "19": [("Bangka Belitung", "id")],
    "31": [("DKI Jakarta", "id"), ("Jakarta", "mixed")],
    "34": [("DI Yogyakarta", "id"), ("Yogyakarta", "mixed")],
}


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def build_catalog() -> dict[str, object]:
    provenance = json.loads(PROVENANCE.read_text(encoding="utf-8"))
    provinces = []
    for position, item in enumerate(provenance["crosswalk"], 1):
        code = item["canonical_code"]
        provinces.append(
            {
                "code": code,
                "canonical_name": item["canonical_name"],
                "canonical_order": position,
                "labels": {"id": item["canonical_name"], "en": ENGLISH_NAMES[code]},
                "aliases": [
                    {"text": text, "language": language, "status": "approved"}
                    for text, language in EXTRA_ALIASES.get(code, [])
                ],
                "administrative_level": 1,
                "boundary_source_id": "osm-idn-adm1-2026-10-10b",
            }
        )

    return {
        "schema_version": "1.0.0",
        "catalog_version": "hotspot-semantic-catalog-v1.0.0",
        "data_contract_version": "1.0.0",
        "created_at": "2026-11-15",
        "metric": {
            "id": METRIC_ID,
            "labels": {
                "en": "satellite hotspot detections",
                "id": "deteksi hotspot satelit",
            },
            "aliases": [
                {"text": "hotspot count", "language": "en"},
                {"text": "detection count", "language": "en"},
                {"text": "jumlah hotspot", "language": "id"},
                {"text": "jumlah deteksi", "language": "id"},
            ],
            "definition": (
                "Count of canonical exact-deduplicated NASA FIRMS observations for the "
                "approved product, inclusive UTC date range, and explicit geographic scope."
            ),
            "unit": "detections",
            "aggregation": "count",
            "grain": "one canonical exact-deduplicated FIRMS observation",
            "valid_dimensions": [
                "product_id",
                "province_code",
                "date_utc",
                "month_utc",
            ],
            "valid_operations": [
                "hotspot_summary_v1",
                "hotspot_trend_v1",
                "hotspot_multi_province_summary_v1",
                "hotspot_province_ranking_v1",
            ],
            "unsupported_interpretations": [
                "confirmed_fires",
                "unique_fire_incidents",
                "burned_area",
                "severity",
                "cause",
                "forecast",
            ],
        },
        "product": {
            "id": PRODUCT_ID,
            "labels": {
                "en": "VIIRS S-NPP standard processing",
                "id": "pemrosesan standar VIIRS S-NPP",
            },
            "source_product": "VNP14IMG",
            "collection_version": "2",
            "processing_stream": "standard",
            "satellite": "Suomi NPP",
            "instrument": "VIIRS",
            "compatible_product_ids": [PRODUCT_ID],
            "incompatible_product_examples": [
                "MODIS",
                "VIIRS_NOAA20_NRT",
                "VNP14IMG.001",
            ],
            "cross_product_aggregation": "prohibited",
        },
        "coverage": {
            "timezone": "UTC",
            "date_bounds": {
                "from": "2023-01-01",
                "to": "2023-12-31",
                "inclusive": True,
            },
            "known_unavailable_dates": ["2023-07-26", "2023-07-27"],
            "states": {
                "complete": "Every requested day has observations_present or independently verified zero coverage.",
                "partial": "At least one day is unavailable; numeric values are subtotals over available days.",
                "unavailable": "The entire requested range is unavailable; numeric results are null.",
            },
            "zero_rule": "Zero is numeric only when coverage supports it; gaps and unknown coverage remain null.",
        },
        "geography": {
            "universe_size": 38,
            "assignment_rule": "Exactly one polygon match is assigned; zero or multiple matches retain null province fields.",
            "not_assigned_rule": (
                "Unassigned and multiple-match observations are excluded from province rows "
                "and disclosed once as an Indonesia-wide exclusion count."
            ),
            "provinces": provinces,
            "ambiguous_scopes": [
                {"text": "Kalimantan", "reason": "island_or_region_not_province"},
                {"text": "Sumatra", "reason": "island_not_province"},
                {"text": "Indonesia", "reason": "country_scope_not_province"},
            ],
        },
        "operations": [
            {
                "id": "hotspot_summary_v1",
                "required_slots": [
                    "metric_id",
                    "product_id",
                    "province_codes[1]",
                    "date_from",
                    "date_to",
                ],
                "forbidden_slots": ["direction", "ranking_selection", "top_n"],
                "result_semantics": "One selected province total over available coverage.",
            },
            {
                "id": "hotspot_trend_v1",
                "required_slots": [
                    "metric_id",
                    "product_id",
                    "province_codes[1]",
                    "date_from",
                    "date_to",
                ],
                "forbidden_slots": ["direction", "ranking_selection", "top_n"],
                "result_semantics": "UTC calendar-month detection series for one province.",
            },
            {
                "id": "hotspot_multi_province_summary_v1",
                "required_slots": [
                    "metric_id",
                    "product_id",
                    "province_codes[2..38]",
                    "date_from",
                    "date_to",
                ],
                "forbidden_slots": ["direction", "ranking_selection", "top_n"],
                "result_semantics": "Ordered selected rows, exact row sum, and optional typed comparison.",
            },
            {
                "id": "hotspot_province_ranking_v1",
                "required_slots": [
                    "metric_id",
                    "product_id",
                    "date_from",
                    "date_to",
                    "direction",
                    "ranking_selection",
                ],
                "forbidden_slots": ["selected_province_total"],
                "result_semantics": "Dense ranking across all 38 canonical provinces.",
            },
        ],
        "ranking": {
            "directions": ["highest", "lowest"],
            "selection_kinds": ["top_n", "ordinal", "rank_lookup", "all", "zero_count"],
            "top_n_bounds": {"minimum": 1, "maximum": 38},
            "tie_policy": "dense_rank_include_cutoff_ties",
            "tie_order": "canonical_order ascending",
            "zero_count_rule": "Covered zero-count provinces participate; unavailable periods do not fabricate zero rows.",
        },
        "safe_retrieval_filter_fields": [
            {
                "field": "metric_id",
                "type": "enum",
                "cardinality": 1,
                "allowed_values": [METRIC_ID],
                "missing": "reject",
            },
            {
                "field": "product_id",
                "type": "enum",
                "cardinality": 1,
                "allowed_values": [PRODUCT_ID],
                "missing": "reject",
            },
            {
                "field": "province_codes",
                "type": "canonical_code_array",
                "cardinality": 38,
                "allowed_values": [p["code"] for p in provinces],
                "missing": "operation_specific",
            },
            {
                "field": "date_from",
                "type": "date",
                "cardinality": 365,
                "allowed_values": "2023 inclusive",
                "missing": "clarify",
            },
            {
                "field": "date_to",
                "type": "date",
                "cardinality": 365,
                "allowed_values": "2023 inclusive",
                "missing": "clarify",
            },
            {
                "field": "direction",
                "type": "enum",
                "cardinality": 2,
                "allowed_values": ["highest", "lowest"],
                "missing": "operation_specific",
            },
            {
                "field": "ranking_selection",
                "type": "enum",
                "cardinality": 5,
                "allowed_values": [
                    "top_n",
                    "ordinal",
                    "rank_lookup",
                    "all",
                    "zero_count",
                ],
                "missing": "operation_specific",
            },
        ],
        "deprecations": [],
        "provenance": {
            "data_contract": "data/contracts/hotspot_data_contract_v1.0.0.md",
            "province_crosswalk": "data/provenance/d03b_reusable_boundary.json",
            "api_contract": "docs/API_CONTRACT.md#10-a03-optional-province-analytics-v120-proposal",
            "source_snapshot_sha256": "2dba3b772b5a3a2cc0feed128af74637810021dd41dc34d584cb99b40411665a",
        },
    }


def build_fixture(catalog: dict[str, object]) -> dict[str, object]:
    codes = [item["code"] for item in catalog["geography"]["provinces"]]
    counts = {code: 1 for code in codes}
    counts.update({"11": 10, "13": 10, "14": 0, "15": 0})
    rules = {
        "metric_identity": (
            {"metric_id": METRIC_ID},
            {"metric_id": "burned_area_hectares"},
        ),
        "product_compatibility": (
            {"product_id": PRODUCT_ID},
            {"product_id": "MODIS"},
        ),
        "coverage_null_zero": (
            {"coverage_state": "complete", "value": 0},
            {"coverage_state": "unavailable", "value": 0},
        ),
        "province_canonicalization": (
            {"term": "West Sumatra", "province_code": "13"},
            {"term": "Kalimantan", "province_code": None},
        ),
        "ranking_bounds": (
            {"selection": "top_n", "top_n": 5},
            {"selection": "top_n", "top_n": 100},
        ),
        "geography_assignment": (
            {"status": "unassigned", "province_code": None},
            {"status": "unassigned", "province_code": "14"},
        ),
        "safe_filtering": (
            {"field": "province_codes", "value": ["11", "13"]},
            {"field": "raw_table", "value": "de_hotspot_observations_v1"},
        ),
        "operation_slots": (
            {"operation": "hotspot_summary_v1", "province_count": 1},
            {"operation": "hotspot_summary_v1", "province_count": 2},
        ),
    }
    semantic_cases = []
    for rule_id, (positive, negative) in rules.items():
        semantic_cases.extend(
            [
                {
                    "id": f"{rule_id}.positive",
                    "rule_id": rule_id,
                    "expected_valid": True,
                    "input": positive,
                },
                {
                    "id": f"{rule_id}.negative",
                    "rule_id": rule_id,
                    "expected_valid": False,
                    "input": negative,
                },
            ]
        )
    return {
        "fixture_classification": "synthetic_semantic_edge_fixture",
        "catalog_version": catalog["catalog_version"],
        "product_id": PRODUCT_ID,
        "metric_id": METRIC_ID,
        "scenario": {
            "date_from": "2023-07-25",
            "date_to": "2023-07-27",
            "province_counts_on_available_days": counts,
            "not_assigned_to_exactly_one_province_count": 7,
            "coverage": [
                {"date": "2023-07-25", "status": "observations_present"},
                {"date": "2023-07-26", "status": "known_satellite_gap"},
                {"date": "2023-07-27", "status": "known_satellite_gap"},
            ],
        },
        "semantic_cases": semantic_cases,
    }


def build_results(
    catalog: dict[str, object], fixture: dict[str, object]
) -> dict[str, object]:
    counts = fixture["scenario"]["province_counts_on_available_days"]
    names = {
        item["code"]: item["canonical_name"]
        for item in catalog["geography"]["provinces"]
    }
    return {
        "results_version": "hotspot-semantic-reference-results-v1.0.0",
        "catalog_version": catalog["catalog_version"],
        "fixture_classification": fixture["fixture_classification"],
        "fixture_sha256": hashlib.sha256(
            (json.dumps(fixture, indent=2, ensure_ascii=False) + "\n").encode()
        ).hexdigest(),
        "synthetic_edge_results": [
            {
                "query_id": "highest_tie",
                "coverage_state": "partial",
                "rows": [
                    {
                        "province_code": code,
                        "province_name": names[code],
                        "count": 10,
                        "dense_rank": 1,
                    }
                    for code in ("11", "13")
                ],
                "cutoff_tie_count": 2,
            },
            {
                "query_id": "covered_zero_tie",
                "coverage_state": "partial",
                "rows": [
                    {
                        "province_code": code,
                        "province_name": names[code],
                        "count": 0,
                        "dense_rank": 1,
                    }
                    for code in ("14", "15")
                ],
                "cutoff_tie_count": 2,
            },
            {
                "query_id": "partial_riau_total",
                "coverage_state": "partial",
                "numeric_total_available": True,
                "total": counts["14"],
                "unavailable_dates": ["2023-07-26", "2023-07-27"],
            },
            {
                "query_id": "wholly_unavailable",
                "coverage_state": "unavailable",
                "numeric_total_available": False,
                "total": None,
                "unavailable_dates": ["2023-07-26", "2023-07-27"],
            },
            {
                "query_id": "national_geography_exclusion",
                "not_assigned_to_exactly_one_province_count": fixture["scenario"][
                    "not_assigned_to_exactly_one_province_count"
                ],
                "included_in_province_rows": False,
            },
        ],
        "verified_snapshot_results": {
            "source": "data/reports/d06_clickhouse_validation.json",
            "source_sha256": hashlib.sha256(
                (
                    ROOT / "data" / "reports" / "d06_clickhouse_validation.json"
                ).read_bytes()
            ).hexdigest(),
            "riau_september_2023": 687,
            "country_monthly_counts_2023": [
                1781,
                1868,
                2602,
                3808,
                5185,
                7407,
                13684,
                42818,
                71726,
                78784,
                19165,
                4560,
            ],
            "observations": 253388,
            "assigned": 252582,
            "unassigned": 796,
            "multiple_match": 10,
            "not_assigned_to_exactly_one_province": 806,
        },
    }


def main() -> int:
    catalog = build_catalog()
    fixture = build_fixture(catalog)
    results = build_results(catalog, fixture)
    _write(CATALOG_PATH, catalog)
    _write(FIXTURE_PATH, fixture)
    _write(RESULTS_PATH, results)
    print(
        json.dumps(
            {"catalog": str(CATALOG_PATH), "provinces": 38, "semantic_cases": 16}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
