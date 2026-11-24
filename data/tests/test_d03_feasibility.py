import io
import json
from datetime import date
from pathlib import Path
import tempfile
import unittest

from data.tests.boundary_fixture import write_synthetic_boundary

from data.scripts.review_big_boundary_points import (
    build_point_query_url,
    classify_review,
    query_point_membership,
)
from data.scripts.validate_d03_requirements import (
    date_request_status,
    prepare_boundary_scanlines,
    prepared_boundary_relation,
)
from data.scripts.validate_historical_sample import (
    boundary_relation,
    load_boundaries,
)


D03_QUESTIONS = Path("data/reports/d03_ten_question_validation.json")
D03_BOUNDARY_REVIEW = Path("data/reports/d03_big_full_resolution_point_review.json")
D03_SCHEMA = Path(
    "data/contracts/hotspot_observation_contract_v0.1.0-proposal.schema.json"
)
class D03FeasibilityTest(unittest.TestCase):
    def test_date_validation_distinguishes_gap_from_zero(self) -> None:
        self.assertEqual(
            date_request_status(date(2023, 7, 26)),
            "unavailable_known_satellite_data_gap",
        )
        self.assertEqual(
            date_request_status(date(2022, 12, 31)),
            "unsupported_outside_validated_range",
        )
        self.assertEqual(
            date_request_status(date(2023, 9, 1)), "within_validated_range"
        )

    def test_scanline_index_matches_reference_geometry_function(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary) / "boundary.geojson"
            write_synthetic_boundary(fixture)
            boundaries = {item.code: item for item in load_boundaries(fixture)}
        cases = {
            "14": [(101.45, 0.5), (105.0, 0.5), (100.0, -5.0)],
            "62": [(113.9, -2.2), (117.0, -2.2), (110.0, -8.0)],
        }
        for code, points in cases.items():
            boundary = boundaries[code]
            prepared = prepare_boundary_scanlines(boundary)
            for longitude, latitude in points:
                self.assertEqual(
                    prepared_boundary_relation(
                        longitude, latitude, boundary, prepared
                    ),
                    boundary_relation(longitude, latitude, boundary),
                )

    def test_big_point_query_requests_no_geometry_and_parses_attributes(self) -> None:
        url = build_point_query_url("118.14832", "-8.17152")
        self.assertIn("returnGeometry=false", url)
        self.assertIn("geometryType=esriGeometryPoint", url)

        payload = {
            "features": [
                {"attributes": {"KDPPUM": "52", "WADMPR": "Nusa Tenggara Barat"}}
            ]
        }

        def opener(request, *, timeout):
            self.assertGreater(timeout, 0)
            self.assertIn("returnGeometry=false", request.full_url)
            return io.BytesIO(json.dumps(payload).encode("utf-8"))

        self.assertEqual(
            query_point_membership("118.14832", "-8.17152", opener=opener),
            [{"province_code": "52", "province_name": "Nusa Tenggara Barat"}],
        )
        self.assertEqual(classify_review("", []), "unchanged_unassigned")
        self.assertEqual(
            classify_review("33", [{"province_code": "35"}]),
            "assignment_changed",
        )

    def test_recorded_ten_question_results_match_pinned_evidence(self) -> None:
        report = json.loads(D03_QUESTIONS.read_text(encoding="utf-8"))
        questions = {item["id"]: item for item in report["questions"]}
        self.assertEqual(len(questions), 10)
        self.assertEqual(questions[1]["result"]["detection_count"], 690)
        self.assertEqual(questions[2]["result"]["2023-09"], 13_487)
        self.assertEqual(questions[3]["result"]["Riau_14"], 3_329)
        self.assertEqual(
            questions[3]["result"]["Kalimantan_Tengah_62"], 33_357
        )
        self.assertEqual(questions[4]["result"]["maximum_months"], ["2023-10"])
        self.assertEqual(questions[5]["result"]["point_count"], 62)
        self.assertEqual(questions[10]["support"], "unsupported_must_abstain")

    def test_recorded_full_resolution_review_preserves_d02_artifact(self) -> None:
        report = json.loads(D03_BOUNDARY_REVIEW.read_text(encoding="utf-8"))
        self.assertEqual(len(report["records"]), 45)
        self.assertEqual(
            report["outcome_counts"],
            {
                "assignment_changed": 1,
                "assignment_confirmed": 30,
                "full_resolution_new_assignment": 3,
                "full_resolution_unassigned": 2,
                "unchanged_unassigned": 9,
            },
        )
        self.assertIn("does not rewrite", report["preservation_policy"])

    def test_contract_schema_requires_provenance_and_geographic_status(self) -> None:
        schema = json.loads(D03_SCHEMA.read_text(encoding="utf-8"))
        required = set(schema["required"])
        self.assertTrue(
            {
                "observation_id",
                "product_id",
                "acquired_at_utc",
                "frp_mw",
                "confidence_code",
                "province_code",
                "geo_assignment_status",
                "ingestion_batch_id",
                "quality_flags",
            }.issubset(required)
        )


if __name__ == "__main__":
    unittest.main()
