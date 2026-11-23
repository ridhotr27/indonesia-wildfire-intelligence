import csv
import copy
import json
from pathlib import Path
import tempfile
import unittest

from data.scripts.ingest_firms_v1 import (
    EXPECTED_HEADER,
    GAP_EVIDENCE_URL,
    IngestionError,
    ingest,
    observation_id,
    source_record_hash,
)


BOUNDARY = Path("data/derived/reference/idn_adm1_osm_2026-10-10b_canonical.geojson")
BOUNDARY_PROVENANCE = Path("data/provenance/d03b_reusable_boundary.json")
SOURCE_URL = "https://firms.modaps.eosdis.nasa.gov/data/country/viirs-snpp_2023_Indonesia.csv"
VALID_ROW = [
    "-2.68407", "115.27225", "331.22", "0.47", "0.4", "2023-01-01",
    "0559", "N", "VIIRS", "n", "2", "286.06", "2.68", "D", "0",
]


def write_csv(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(EXPECTED_HEADER)
        writer.writerows(rows)


def load_ndjson(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class D05IngestionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_ingest(
        self, rows: list[list[str]], *, provenance: Path = BOUNDARY_PROVENANCE,
        output_name: str = "published", source_year: int = 2023,
        contract_version: str = "1.0.0",
    ) -> tuple[dict, Path]:
        source = self.root / "source.csv"
        write_csv(source, rows)
        manifest = ingest(
            source_csv=source,
            boundary_geojson=BOUNDARY,
            boundary_provenance=provenance,
            output_root=self.root / output_name,
            source_url=SOURCE_URL.replace("_2023_", f"_{source_year}_"),
            retrieved_at_utc="2026-10-21T05:00:00Z",
            source_year=source_year,
            contract_version=contract_version,
        )
        return manifest, self.root / output_name / manifest["ingestion_batch_id"]

    def test_exact_identity_is_lexeme_sensitive_and_deterministic(self) -> None:
        digest = source_record_hash(VALID_ROW)
        self.assertEqual(digest, source_record_hash(list(VALID_ROW)))
        self.assertEqual(len(digest), 64)
        self.assertEqual(len(observation_id(digest)), 64)
        changed = list(VALID_ROW)
        changed[0] = "-2.684070"
        self.assertNotEqual(digest, source_record_hash(changed))

    def test_ingestion_deduplicates_and_emits_gap_aware_contract_artifacts(self) -> None:
        manifest, directory = self.run_ingest([VALID_ROW, VALID_ROW])
        self.assertEqual(manifest["counts"]["source_rows"], 2)
        self.assertEqual(manifest["counts"]["canonical_rows"], 1)
        self.assertEqual(manifest["counts"]["duplicate_excess_rows"], 1)
        observations = load_ndjson(directory / "observations.ndjson")
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0]["source_row_number"], 1)
        self.assertEqual(observations[0]["acquired_at_utc"], "2023-01-01T05:59:00Z")
        coverage = {row["date_utc"]: row for row in load_ndjson(directory / "daily_coverage.ndjson")}
        self.assertEqual(len(coverage), 365)
        self.assertEqual(coverage["2023-01-01"]["observation_count"], 1)
        for gap in ("2023-07-26", "2023-07-27"):
            self.assertEqual(coverage[gap]["coverage_status"], "known_satellite_gap")
            self.assertIsNone(coverage[gap]["observation_count"])
            self.assertEqual(coverage[gap]["evidence_url"], GAP_EVIDENCE_URL)
        self.assertEqual(coverage["2023-01-02"]["coverage_status"], "unknown")
        self.assertIsNone(coverage["2023-01-02"]["observation_count"])
        self.assertEqual(len(load_ndjson(directory / "provinces.ndjson")), 38)

    def test_year_aware_candidate_coverage_preserves_2023_and_blocks_publication(self) -> None:
        row_2024 = list(VALID_ROW)
        row_2024[5] = "2024-02-29"
        manifest, directory = self.run_ingest(
            [row_2024], source_year=2024, output_name="candidate-2024"
        )
        coverage = load_ndjson(directory / "daily_coverage.ndjson")
        self.assertEqual(len(coverage), 366)
        self.assertEqual(coverage[0]["date_utc"], "2024-01-01")
        self.assertEqual(coverage[-1]["date_utc"], "2024-12-31")
        self.assertEqual(
            next(row for row in coverage if row["date_utc"] == "2024-02-29")
            ["coverage_status"],
            "observations_present",
        )
        self.assertFalse(any(row["coverage_status"] == "known_satellite_gap" for row in coverage))
        self.assertEqual(manifest["source_year"], 2024)
        self.assertFalse(manifest["clickhouse_ingestion_authorized"])
        self.assertEqual(manifest["transform_version"], "d08-year-aware-ingestion-v1")

        row_2025 = list(VALID_ROW)
        row_2025[5] = "2025-12-31"
        manifest_2025, directory_2025 = self.run_ingest(
            [row_2025], source_year=2025, output_name="candidate-2025"
        )
        self.assertEqual(manifest_2025["source_year"], 2025)
        self.assertEqual(
            len(load_ndjson(directory_2025 / "daily_coverage.ndjson")), 365
        )

    def test_year_aware_processing_rejects_cross_year_rows(self) -> None:
        with self.assertRaisesRegex(IngestionError, "outside requested calendar 2024"):
            self.run_ingest(
                [VALID_ROW], source_year=2024, output_name="wrong-year"
            )

    def test_v11_candidate_reproduces_2023_with_versioned_rows_and_stays_hidden(self) -> None:
        manifest, directory = self.run_ingest(
            [VALID_ROW], output_name="candidate-v11", contract_version="1.1.0"
        )
        self.assertEqual(manifest["contract_version"], "1.1.0")
        self.assertEqual(manifest["source_year"], 2023)
        self.assertEqual(manifest["transform_version"], "d08-multiyear-ingestion-v1")
        self.assertFalse(manifest["clickhouse_ingestion_authorized"])
        self.assertTrue(manifest["ingestion_batch_id"].startswith("firms-v11-"))
        for name in (
            "observations.ndjson", "daily_coverage.ndjson",
            "provinces.ndjson", "ingestion_batch.ndjson",
        ):
            self.assertTrue(all(
                row["contract_version"] == "1.1.0" for row in load_ndjson(directory / name)
            ))

    def test_rerun_is_idempotent_and_verifies_immutable_artifacts(self) -> None:
        manifest, directory = self.run_ingest([VALID_ROW])
        source = self.root / "source.csv"
        second = ingest(
            source_csv=source,
            boundary_geojson=BOUNDARY,
            boundary_provenance=BOUNDARY_PROVENANCE,
            output_root=self.root / "published",
            source_url=SOURCE_URL,
            retrieved_at_utc="2026-10-21T05:00:00Z",
        )
        self.assertEqual(second, manifest)
        self.assertEqual(len([item for item in directory.parent.iterdir() if item.is_dir()]), 1)
        (directory / "observations.ndjson").write_text("tampered\n", encoding="utf-8")
        with self.assertRaisesRegex(IngestionError, "failed verification"):
            ingest(
                source_csv=source, boundary_geojson=BOUNDARY,
                boundary_provenance=BOUNDARY_PROVENANCE,
                output_root=self.root / "published", source_url=SOURCE_URL,
                retrieved_at_utc="2026-10-21T05:00:00Z",
            )

    def test_rerun_rejects_tampered_manifest_identity(self) -> None:
        manifest, directory = self.run_ingest([VALID_ROW])
        tampered = dict(manifest)
        tampered["publication"] = {"atomic": False, "state": "published"}
        (directory / "manifest.json").write_text(
            json.dumps(tampered), encoding="utf-8"
        )
        with self.assertRaisesRegex(IngestionError, "manifest identity"):
            ingest(
                source_csv=self.root / "source.csv", boundary_geojson=BOUNDARY,
                boundary_provenance=BOUNDARY_PROVENANCE,
                output_root=self.root / "published", source_url=SOURCE_URL,
                retrieved_at_utc="2026-10-21T05:00:00Z",
            )

    def test_malformed_row_fails_without_publishing_partial_batch(self) -> None:
        malformed = list(VALID_ROW)
        malformed[0] = "not-a-number"
        source = self.root / "source.csv"
        write_csv(source, [VALID_ROW, malformed])
        output = self.root / "published"
        with self.assertRaisesRegex(IngestionError, "row 2: latitude must be numeric"):
            ingest(
                source_csv=source, boundary_geojson=BOUNDARY,
                boundary_provenance=BOUNDARY_PROVENANCE, output_root=output,
                source_url=SOURCE_URL, retrieved_at_utc="2026-10-21T05:00:00Z",
            )
        self.assertEqual(list(output.iterdir()), [])

    def test_observation_on_approved_gap_date_fails_without_publication(self) -> None:
        gap_row = list(VALID_ROW)
        gap_row[5] = "2023-07-26"
        source = self.root / "source.csv"
        write_csv(source, [gap_row])
        output = self.root / "published"
        with self.assertRaisesRegex(IngestionError, "known satellite gap date"):
            ingest(
                source_csv=source, boundary_geojson=BOUNDARY,
                boundary_provenance=BOUNDARY_PROVENANCE, output_root=output,
                source_url=SOURCE_URL, retrieved_at_utc="2026-10-21T05:00:00Z",
            )
        self.assertEqual(list(output.iterdir()), [])

    def test_tampered_boundary_provenance_is_rejected_even_when_geometry_is_unchanged(self) -> None:
        approved = json.loads(BOUNDARY_PROVENANCE.read_text(encoding="utf-8"))
        cases = []

        changed_name = copy.deepcopy(approved)
        changed_name["crosswalk"][0]["canonical_name"] = "Not Aceh"
        cases.append(("changed-name", changed_name, "crosswalk"))

        changed_commit = copy.deepcopy(approved)
        changed_commit["source"]["commit"] = "0" * 40
        cases.append(("changed-commit", changed_commit, "commit"))

        changed_license = copy.deepcopy(approved)
        changed_license["source"]["required_attribution"] = ""
        cases.append(("changed-attribution", changed_license, "required_attribution"))

        for name, payload, message in cases:
            with self.subTest(name=name):
                provenance = self.root / f"{name}.json"
                provenance.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaisesRegex(IngestionError, message):
                    self.run_ingest(
                        [VALID_ROW], provenance=provenance,
                        output_name=f"published-{name}",
                    )

    def test_approved_boundary_provenance_and_exact_crosswalk_are_accepted(self) -> None:
        manifest, directory = self.run_ingest([VALID_ROW])
        self.assertEqual(manifest["counts"]["provinces"], 38)
        provinces = load_ndjson(directory / "provinces.ndjson")
        self.assertEqual(len(provinces), 38)
        self.assertEqual(provinces[0]["province_name"], "Aceh")

    def test_idempotent_rerun_still_rejects_tampered_boundary_and_request_identity(self) -> None:
        manifest, _directory = self.run_ingest([VALID_ROW])
        approved = json.loads(BOUNDARY_PROVENANCE.read_text(encoding="utf-8"))

        changed_name = copy.deepcopy(approved)
        changed_name["crosswalk"][0]["canonical_name"] = "Not Aceh"
        changed_provenance = self.root / "changed-provenance.json"
        changed_provenance.write_text(json.dumps(changed_name), encoding="utf-8")
        with self.assertRaisesRegex(IngestionError, "crosswalk"):
            self.run_ingest([VALID_ROW], provenance=changed_provenance)

        geometry = json.loads(BOUNDARY.read_text(encoding="utf-8"))
        position = geometry["features"][0]["geometry"]["coordinates"][0][0][0]
        position[0] += 0.000001
        changed_geometry = self.root / "changed-boundary.geojson"
        changed_geometry.write_text(json.dumps(geometry), encoding="utf-8")
        with self.assertRaisesRegex(IngestionError, "approved canonical checksum"):
            ingest(
                source_csv=self.root / "source.csv",
                boundary_geojson=changed_geometry,
                boundary_provenance=BOUNDARY_PROVENANCE,
                output_root=self.root / "published", source_url=SOURCE_URL,
                retrieved_at_utc="2026-10-21T05:00:00Z",
            )

        with self.assertRaisesRegex(IngestionError, "request identity"):
            ingest(
                source_csv=self.root / "source.csv", boundary_geojson=BOUNDARY,
                boundary_provenance=BOUNDARY_PROVENANCE,
                output_root=self.root / "published",
                source_url="https://example.test/different-source.csv",
                retrieved_at_utc="2026-10-21T05:00:00Z",
            )
        self.assertEqual(manifest["source_url"], SOURCE_URL)

    def test_wrong_product_time_and_secret_bearing_url_are_rejected(self) -> None:
        wrong_product = list(VALID_ROW)
        wrong_product[7] = "J1"
        with self.assertRaisesRegex(IngestionError, "approved S-NPP"):
            self.run_ingest([wrong_product])

        source = self.root / "source.csv"
        write_csv(source, [VALID_ROW])
        with self.assertRaisesRegex(IngestionError, "query parameters"):
            ingest(
                source_csv=source, boundary_geojson=BOUNDARY,
                boundary_provenance=BOUNDARY_PROVENANCE,
                output_root=self.root / "other",
                source_url=f"{SOURCE_URL}?MAP_KEY=secret",
                retrieved_at_utc="2026-10-21T05:00:00Z",
            )


if __name__ == "__main__":
    unittest.main()
