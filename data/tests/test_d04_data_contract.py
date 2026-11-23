import copy
import json
from pathlib import Path
import unittest

from data.scripts.validate_data_contract import (
    ContractValidationError,
    KNOWN_GAPS,
    load_and_validate,
    validate_instance,
    validate_semantics,
)


SCHEMA_PATH = Path("data/contracts/hotspot_data_contract_v1.0.0.schema.json")
FIXTURE_PATH = Path("data/contracts/fixtures/hotspot_data_contract_v1.0.0.fixture.json")
BOUNDARY_PROVENANCE_PATH = Path("data/provenance/d03b_reusable_boundary.json")
CONTRACT_PATH = Path("data/contracts/hotspot_data_contract_v1.0.0.md")


class D04DataContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.provenance = json.loads(BOUNDARY_PROVENANCE_PATH.read_text(encoding="utf-8"))

    def test_fixture_validates_against_schema_and_semantics(self) -> None:
        counts = load_and_validate(SCHEMA_PATH, FIXTURE_PATH, BOUNDARY_PROVENANCE_PATH)
        self.assertEqual(counts["observations"], 2)
        self.assertEqual(counts["approved_crosswalk_provinces"], 38)
        self.assertEqual(counts["reference_queries"], 2)

    def test_fixture_is_unmistakably_synthetic(self) -> None:
        self.assertEqual(self.fixture["fixture_classification"], "synthetic_contract_example")
        batch = self.fixture["ingestion_batches"][0]
        self.assertEqual(batch["transform_version"], "synthetic-fixture-only")
        self.assertIn("example.invalid", batch["source_url"])

    def test_schema_rejects_precision_and_type_boundary_violations(self) -> None:
        invalid = copy.deepcopy(self.fixture)
        invalid["observations"][0]["latitude"] = 90.000001
        with self.assertRaises(ContractValidationError):
            validate_instance(invalid, self.schema, self.schema)

        invalid = copy.deepcopy(self.fixture)
        invalid["observations"][0]["frp_mw"] = -0.01
        with self.assertRaises(ContractValidationError):
            validate_instance(invalid, self.schema, self.schema)

        invalid = copy.deepcopy(self.fixture)
        invalid["observations"][0]["source_row_number"] = 1.5
        with self.assertRaises(ContractValidationError):
            validate_instance(invalid, self.schema, self.schema)

    def test_nullable_geography_semantics_are_enforced(self) -> None:
        invalid = copy.deepcopy(self.fixture)
        invalid["observations"][1]["province_code"] = "14"
        with self.assertRaisesRegex(ContractValidationError, "non-assigned geography"):
            validate_semantics(invalid, self.provenance)

        invalid = copy.deepcopy(self.fixture)
        invalid["observations"][0]["boundary_source_id"] = None
        with self.assertRaisesRegex(ContractValidationError, "assigned geography"):
            validate_semantics(invalid, self.provenance)

    def test_known_gap_cannot_be_coerced_to_zero(self) -> None:
        coverage = {item["date_utc"]: item for item in self.fixture["daily_coverage"]}
        self.assertEqual(KNOWN_GAPS, {"2023-07-26", "2023-07-27"})
        for gap in KNOWN_GAPS:
            self.assertEqual(coverage[gap]["coverage_status"], "known_satellite_gap")
            self.assertIsNone(coverage[gap]["observation_count"])

        invalid = copy.deepcopy(self.fixture)
        next(item for item in invalid["daily_coverage"] if item["date_utc"] == "2023-07-26")[
            "observation_count"
        ] = 0
        with self.assertRaisesRegex(ContractValidationError, "null count"):
            validate_semantics(invalid, self.provenance)

    def test_gap_aware_reference_queries_distinguish_partial_and_unavailable(self) -> None:
        queries = {item["query_id"]: item for item in self.fixture["reference_queries"]}
        partial = queries["assigned-riau-spanning-known-gap"]
        self.assertEqual(partial["available_detection_total"], 1)
        self.assertTrue(partial["numeric_total_available"])
        self.assertFalse(partial["is_complete"])

        unavailable = queries["range-wholly-unavailable"]
        self.assertIsNone(unavailable["available_detection_total"])
        self.assertFalse(unavailable["numeric_total_available"])
        self.assertFalse(unavailable["is_complete"])

    def test_fixture_provinces_match_approved_38_province_crosswalk(self) -> None:
        crosswalk = {
            item["canonical_code"]: item for item in self.provenance["crosswalk"]
        }
        self.assertEqual(len(crosswalk), 38)
        for province in self.fixture["provinces"]:
            approved = crosswalk[province["province_code"]]
            self.assertEqual(province["province_name"], approved["canonical_name"])
            self.assertEqual(province["source_code"], approved["source_code"])

    def test_interface_names_map_cap_and_read_only_boundary_are_documented(self) -> None:
        contract = CONTRACT_PATH.read_text(encoding="utf-8")
        for interface in (
            "analytics_hotspot_observations_v1",
            "analytics_daily_coverage_v1",
            "analytics_provinces_v1",
            "analytics_ingestion_batches_v1",
        ):
            self.assertIn(interface, contract)
        self.assertIn("hard cap is 5,000 points", contract)
        self.assertIn("`SELECT` only", contract)
        self.assertIn("not a confirmed wildfire incident", contract)


if __name__ == "__main__":
    unittest.main()
