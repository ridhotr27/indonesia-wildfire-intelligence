import json
import math
from pathlib import Path
import unittest

from data.scripts.validate_reusable_boundaries import (
    PROVINCES,
    canonicalize,
    coordinate_count,
    validate_ring,
)
from data.scripts.validate_historical_sample import load_boundaries


SOURCE = Path("data/raw/reference/idn_adm1_osm_2026-10-10b.geojson")
CANONICAL = Path(
    "data/derived/reference/idn_adm1_osm_2026-10-10b_canonical.geojson"
)
REPORT = Path("data/reports/d03b_reusable_boundary_validation.json")


class ReusableBoundaryTest(unittest.TestCase):
    def test_crosswalk_contains_exactly_38_unique_canonical_codes(self) -> None:
        self.assertEqual(len(PROVINCES), 38)
        codes = [canonical_code for canonical_code, _ in PROVINCES.values()]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertEqual(PROVINCES["ID_RI"], ("14", "Riau"))
        self.assertEqual(PROVINCES["ID_KT"], ("62", "Kalimantan Tengah"))

    def test_ring_validation_rejects_open_and_nonfinite_rings(self) -> None:
        with self.assertRaisesRegex(ValueError, "not closed"):
            validate_ring([[100.0, 0.0], [101.0, 0.0], [101.0, 1.0], [100.0, 1.0]])
        with self.assertRaisesRegex(ValueError, "not finite"):
            validate_ring(
                [[100.0, 0.0], [math.inf, 0.0], [101.0, 1.0], [100.0, 0.0]]
            )

    @unittest.skipUnless(SOURCE.is_file(), "pinned local boundary source is unavailable")
    def test_pinned_candidate_canonicalizes_to_expected_manifest_count(self) -> None:
        source = json.loads(SOURCE.read_text(encoding="utf-8"))
        canonical, crosswalk, profile = canonicalize(source)
        self.assertEqual(len(canonical["features"]), 38)
        self.assertEqual(len(crosswalk), 38)
        self.assertEqual(profile["positions"], 380_953)
        self.assertEqual(
            profile["positions"],
            sum(coordinate_count(item["geometry"]["coordinates"]) for item in source["features"]),
        )

    @unittest.skipUnless(
        CANONICAL.is_file(), "generated local canonical boundary is unavailable"
    )
    def test_generated_canonical_and_report_preserve_null_assignment_policy(self) -> None:
        boundaries = load_boundaries(CANONICAL)
        self.assertEqual(len(boundaries), 38)
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "technical_evidence_complete_pending_tech_lead_approval")
        self.assertEqual(report["five_day_join"]["rows"], 15_804)
        self.assertEqual(report["flagged_point_comparison"]["records_reviewed"], 45)
        self.assertIn("No nearest-province coercion", report["five_day_join"]["policy"])


if __name__ == "__main__":
    unittest.main()
