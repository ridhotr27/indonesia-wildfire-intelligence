import json
from pathlib import Path
import unittest

from data.scripts.validate_historical_sample import (
    Boundary,
    boundary_relation,
    join_rows,
    load_boundaries,
    polygon_bbox,
)


BOUNDARIES = Path("data/raw/reference/idn_adm1_big_2026_generalized.geojson")
PROFILE = Path("data/reports/d02_historical_validation_profile.json")


def square(west: float, south: float, east: float, north: float):
    return [
        [west, south],
        [east, south],
        [east, north],
        [west, north],
        [west, south],
    ]


class HistoricalGeometryTest(unittest.TestCase):
    def test_polygon_relation_handles_boundary_and_hole(self) -> None:
        polygon = [square(0, 0, 10, 10), square(4, 4, 6, 6)]
        boundary = Boundary("A", "Alpha", [polygon], polygon_bbox([polygon]))

        self.assertEqual(boundary_relation(2, 2, boundary), "inside")
        self.assertEqual(boundary_relation(0, 2, boundary), "boundary")
        self.assertEqual(boundary_relation(5, 5, boundary), "outside")
        self.assertEqual(boundary_relation(4, 5, boundary), "boundary")
        self.assertEqual(boundary_relation(12, 5, boundary), "outside")

    def test_join_assigns_unique_polygons_and_flags_near_boundary(self) -> None:
        alpha_polygon = [square(0, 0, 1, 1)]
        beta_polygon = [square(1, 0, 2, 1)]
        boundaries = [
            Boundary("A", "Alpha", [alpha_polygon], polygon_bbox([alpha_polygon])),
            Boundary("B", "Beta", [beta_polygon], polygon_bbox([beta_polygon])),
        ]
        rows = [
            {"longitude": "0.5", "latitude": "0.5", "type": "0"},
            {"longitude": "1.0005", "latitude": "0.5", "type": "0"},
            {"longitude": "3", "latitude": "3", "type": "3"},
        ]

        enriched, profile = join_rows(
            rows, boundaries, ambiguity_threshold_degrees=0.001
        )

        self.assertEqual(enriched[0]["province_code"], "A")
        self.assertEqual(enriched[1]["province_code"], "B")
        self.assertEqual(enriched[1]["boundary_near_0_001deg"], "true")
        self.assertEqual(enriched[2]["join_status"], "unassigned")
        self.assertEqual(profile["status_counts"], {"assigned": 2, "unassigned": 1})

    def test_pinned_big_boundary_has_current_38_province_codes(self) -> None:
        boundaries = load_boundaries(BOUNDARIES)
        self.assertEqual(len(boundaries), 38)
        self.assertIn(("14", "Riau"), {(item.code, item.name) for item in boundaries})
        self.assertIn(
            ("96", "Papua Barat Daya"),
            {(item.code, item.name) for item in boundaries},
        )

    def test_generated_d02_profile_matches_pinned_evidence(self) -> None:
        result = json.loads(PROFILE.read_text(encoding="utf-8"))
        source = result["historical_source_profile"]
        sample = result["bounded_sample"]

        self.assertEqual(source["shape"], {"rows": 253_388, "columns": 15})
        self.assertEqual(
            source["coverage"]["missing_dates_between_min_and_max"],
            ["2023-07-26", "2023-07-27"],
        )
        self.assertEqual(sample["profile"]["shape"]["rows"], 15_804)
        self.assertEqual(
            sample["join"]["status_counts"],
            {"assigned": 15_770, "unassigned": 34},
        )
        self.assertEqual(sample["join"]["near_generalized_boundary_count"], 45)


if __name__ == "__main__":
    unittest.main()
