from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from data.scripts.build_semantic_catalog import (
    build_catalog,
    build_fixture,
    build_results,
)
from data.scripts.validate_data_contract import (
    ContractValidationError,
    validate_instance,
)
from data.scripts.validate_semantic_catalog import (
    load_and_validate,
    validate_catalog,
    validate_fixture,
    validate_results,
    validate_sql,
)

ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "data/contracts/hotspot_semantic_catalog_v1.0.0.json"
SCHEMA_PATH = ROOT / "data/contracts/hotspot_semantic_catalog_v1.0.0.schema.json"
FIXTURE_PATH = (
    ROOT / "data/contracts/fixtures/hotspot_semantic_catalog_v1.0.0.fixture.json"
)
RESULTS_PATH = (
    ROOT / "data/contracts/reference/hotspot_semantic_reference_results_v1.0.0.json"
)
SQL_PATH = (
    ROOT / "data/contracts/reference/hotspot_semantic_reference_queries_v1.0.0.sql"
)
PROVENANCE_PATH = ROOT / "data/provenance/d03b_reusable_boundary.json"
D06_PATH = ROOT / "data/reports/d06_clickhouse_validation.json"


class Lir02SemanticCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
        cls.provenance = json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))
        cls.d06 = json.loads(D06_PATH.read_text(encoding="utf-8"))

    def test_complete_catalog_and_truth_bundle_validates(self) -> None:
        self.assertEqual(
            load_and_validate(ROOT),
            {
                "provinces": 38,
                "operations": 4,
                "semantic_cases": 16,
                "synthetic_reference_results": 5,
            },
        )

    def test_generated_artifacts_are_reproducible(self) -> None:
        catalog = build_catalog()
        fixture = build_fixture(catalog)
        results = build_results(catalog, fixture)
        self.assertEqual(catalog, self.catalog)
        self.assertEqual(fixture, self.fixture)
        self.assertEqual(results, self.results)

    def test_schema_rejects_version_and_unknown_field_changes(self) -> None:
        invalid = copy.deepcopy(self.catalog)
        invalid["catalog_version"] = "hotspot-semantic-catalog-v2.0.0"
        with self.assertRaises(ContractValidationError):
            validate_instance(invalid, self.schema, self.schema)

        invalid = copy.deepcopy(self.catalog)
        invalid["runtime_prompt"] = "not data-owned"
        with self.assertRaises(ContractValidationError):
            validate_instance(invalid, self.schema, self.schema)

    def test_alias_collision_and_crosswalk_drift_fail(self) -> None:
        invalid = copy.deepcopy(self.catalog)
        invalid["geography"]["provinces"][1]["aliases"].append(
            {"text": "West Sumatra", "language": "en", "status": "approved"}
        )
        with self.assertRaisesRegex(ContractValidationError, "alias collision"):
            validate_catalog(invalid, self.schema, self.provenance)

        invalid = copy.deepcopy(self.catalog)
        papua_barat = next(
            item for item in invalid["geography"]["provinces"] if item["code"] == "92"
        )
        papua_barat["code"] = "91"
        with self.assertRaisesRegex(ContractValidationError, "crosswalk"):
            validate_catalog(invalid, self.schema, self.provenance)

    def test_product_coverage_and_safe_filter_drift_fail(self) -> None:
        invalid = copy.deepcopy(self.catalog)
        invalid["coverage"]["known_unavailable_dates"] = []
        with self.assertRaisesRegex(ContractValidationError, "gap dates"):
            validate_catalog(invalid, self.schema, self.provenance)

        invalid = copy.deepcopy(self.catalog)
        invalid["safe_retrieval_filter_fields"].append(
            {
                "field": "raw_table",
                "type": "string",
                "cardinality": 1,
                "allowed_values": ["x"],
                "missing": "reject",
            }
        )
        with self.assertRaisesRegex(ContractValidationError, "allowlist"):
            validate_catalog(invalid, self.schema, self.provenance)

    def test_each_semantic_rule_has_positive_and_negative_truth(self) -> None:
        validate_fixture(self.fixture)
        invalid = copy.deepcopy(self.fixture)
        invalid["semantic_cases"] = [
            case
            for case in invalid["semantic_cases"]
            if case["id"] != "metric_identity.negative"
        ]
        with self.assertRaisesRegex(ContractValidationError, "positive and negative"):
            validate_fixture(invalid)

    def test_reference_results_reconcile_zero_tie_gap_and_null_geography(self) -> None:
        validate_results(self.catalog, self.fixture, self.results, self.d06)
        by_id = {
            item["query_id"]: item for item in self.results["synthetic_edge_results"]
        }
        self.assertEqual(by_id["highest_tie"]["cutoff_tie_count"], 2)
        self.assertEqual(by_id["covered_zero_tie"]["cutoff_tie_count"], 2)
        self.assertEqual(by_id["partial_riau_total"]["total"], 0)
        self.assertIsNone(by_id["wholly_unavailable"]["total"])
        self.assertFalse(
            by_id["national_geography_exclusion"]["included_in_province_rows"]
        )

    def test_reference_sql_is_parameterized_read_only_and_published_view_only(
        self,
    ) -> None:
        sql = SQL_PATH.read_text(encoding="utf-8")
        validate_sql(sql)
        for view in (
            "analytics_hotspot_observations_v1",
            "analytics_daily_coverage_v1",
            "analytics_provinces_v1",
        ):
            self.assertIn(view, sql)
        self.assertNotIn("de_hotspot_observations_v1", sql)

    def test_catalog_contains_no_secret_or_runtime_owned_fields(self) -> None:
        payload = CATALOG_PATH.read_text(encoding="utf-8").casefold()
        for token in (
            "access_token",
            "api_key",
            "password",
            "chain_of_thought",
            "embedding_vector",
            "runtime_prompt",
        ):
            self.assertNotIn(token, payload)

    def test_backend_handoff_exposes_known_papua_compatibility_risk(self) -> None:
        provinces = {
            item["code"]: item["canonical_name"]
            for item in self.catalog["geography"]["provinces"]
        }
        self.assertEqual(provinces["91"], "Papua")
        self.assertEqual(provinces["92"], "Papua Barat")
        self.assertEqual(provinces["96"], "Papua Barat Daya")


if __name__ == "__main__":
    unittest.main()
