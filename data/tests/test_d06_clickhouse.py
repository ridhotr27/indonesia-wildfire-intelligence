from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import BinaryIO

from data.scripts.load_clickhouse_v1 import (
    LoadError,
    load_batch,
    single_writer_lock,
    verify_batch,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "data/contracts/fixtures/hotspot_data_contract_v1.0.0.fixture.json"
MIGRATION = ROOT / "data/clickhouse/migrations/001_d06_physical_model.sql"
GRANTS = ROOT / "data/clickhouse/migrations/002_d06_backend_reader_role.sql"


def _fixture_batch(root: Path) -> Path:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    batch_id = fixture["ingestion_batches"][0]["ingestion_batch_id"]
    directory = root / batch_id
    directory.mkdir()
    mapping = {
        "observations.ndjson": fixture["observations"],
        "daily_coverage.ndjson": fixture["daily_coverage"],
        "provinces.ndjson": fixture["provinces"],
        "ingestion_batch.ndjson": fixture["ingestion_batches"],
    }
    artifacts = {}
    for name, rows in mapping.items():
        payload = "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows)
        path = directory / name
        path.write_text(payload, encoding="utf-8")
        artifacts[name] = {
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    batch = fixture["ingestion_batches"][0]
    manifest = {
        "contract_version": "1.0.0",
        "ticket": "D05",
        "classification": "synthetic_contract_example",
        "ingestion_batch_id": batch_id,
        "product_id": batch["product_id"],
        "transform_version": batch["transform_version"],
        "source_artifact_sha256": batch["source_artifact_sha256"],
        "source_url": batch["source_url"],
        "boundary_source_id": "osm-idn-adm1-2026-10-10b",
        "boundary_canonical_sha256": fixture["provinces"][0]["canonical_sha256"],
        "artifacts": artifacts,
        "counts": {
            "source_rows": batch["source_row_count"],
            "canonical_rows": batch["canonical_row_count"],
            "duplicate_excess_rows": batch["duplicate_excess_rows"],
            "rejected_rows": batch["rejected_row_count"],
            "coverage_days": len(fixture["daily_coverage"]),
            "provinces": len(fixture["provinces"]),
        },
        "publication": {"state": "published", "atomic": True},
    }
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return directory


class FakeClickHouse:
    def __init__(self, scalars: list[str]):
        self.scalars = scalars
        self.inserts: list[str] = []

    def scalar(self, sql: str) -> str:
        return self.scalars.pop(0)

    def insert_file(self, table: str, handle: BinaryIO, size: int) -> None:
        self.inserts.append(table)
        self.last_size = size
        handle.read()


class D06BatchValidationTests(unittest.TestCase):
    def test_single_writer_lock_contends_and_releases_after_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            lock_dir = Path(temp) / "locks"
            with single_writer_lock(lock_dir, "credential-free-scope") as path:
                self.assertNotIn("password", path.name)
                with self.assertRaisesRegex(LoadError, "single-writer lock"):
                    with single_writer_lock(lock_dir, "credential-free-scope"):
                        self.fail("contended lock was acquired")
            with single_writer_lock(lock_dir, "credential-free-scope"):
                pass

    def test_single_writer_lock_releases_after_exception(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            lock_dir = Path(temp) / "locks"
            with self.assertRaisesRegex(RuntimeError, "simulated"):
                with single_writer_lock(lock_dir, "scope"):
                    raise RuntimeError("simulated load failure")
            with single_writer_lock(lock_dir, "scope"):
                pass

    def test_checksum_tamper_fails_before_database_use(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            batch = _fixture_batch(Path(temp))
            with (batch / "observations.ndjson").open("a", encoding="utf-8") as handle:
                handle.write("{}\n")
            with self.assertRaisesRegex(LoadError, "byte count mismatch"):
                verify_batch(batch)

    def test_batch_row_must_match_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            batch = _fixture_batch(Path(temp))
            manifest = json.loads((batch / "manifest.json").read_text())
            manifest["counts"]["canonical_rows"] = 3
            (batch / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(LoadError, "canonical_row_count"):
                verify_batch(batch)

    def test_candidate_year_batch_is_blocked_before_database_use(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            batch = _fixture_batch(Path(temp))
            manifest_path = batch / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["source_year"] = 2024
            manifest["clickhouse_ingestion_authorized"] = False
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(LoadError, "not authorized"):
                verify_batch(batch)

    def test_load_publishes_batch_last_and_reconciles(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            verified = verify_batch(_fixture_batch(Path(temp)))
            client = FakeClickHouse(["0", "0", "0", "2:2"])
            result = load_batch(verified, client)
            self.assertEqual(result["status"], "loaded")
            self.assertEqual(
                client.inserts,
                [
                    "de_provinces_v1",
                    "de_hotspot_observations_v1",
                    "de_daily_coverage_v1",
                    "de_ingestion_batches_v1",
                ],
            )

    def test_idempotent_existing_batch_requires_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            verified = verify_batch(_fixture_batch(Path(temp)))
            fingerprint = verified.batch_row["source_artifact_sha256"] + ":2"
            client = FakeClickHouse(["1", fingerprint])
            self.assertEqual(load_batch(verified, client)["status"], "already_loaded")
            self.assertEqual(client.inserts, [])

    def test_orphaned_partial_load_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            verified = verify_batch(_fixture_batch(Path(temp)))
            client = FakeClickHouse(["0", "2"])
            with self.assertRaisesRegex(LoadError, "operator cleanup"):
                load_batch(verified, client)
            self.assertEqual(client.inserts, [])

    def test_grant_migration_exposes_only_contract_views(self) -> None:
        sql = GRANTS.read_text(encoding="utf-8")
        for view in (
            "analytics_hotspot_observations_v1",
            "analytics_daily_coverage_v1",
            "analytics_provinces_v1",
            "analytics_ingestion_batches_v1",
        ):
            self.assertIn(f"GRANT SELECT ON wildfire.{view}", sql)
        self.assertNotIn("GRANT INSERT", sql)
        self.assertNotIn("GRANT SELECT ON wildfire.de_", sql)
        self.assertNotIn("<secret>' TO", sql)


@unittest.skipUnless(shutil.which("clickhouse"), "clickhouse-local is unavailable")
class D06LocalClickHouseIntegrationTests(unittest.TestCase):
    class LocalClient:
        def __init__(self, path: Path):
            self.path = path

        def _run(self, query: str, data: bytes | None = None) -> str:
            result = subprocess.run(
                [
                    "clickhouse", "local", "--path", str(self.path),
                    "--database", "wildfire", "--query", query,
                ],
                input=data,
                capture_output=True,
                check=False,
            )
            if result.returncode:
                raise RuntimeError(result.stderr.decode())
            return result.stdout.decode().strip()

        def scalar(self, sql: str) -> str:
            return self._run(sql + " FORMAT TabSeparatedRaw")

        def insert_file(self, table: str, handle: BinaryIO, size: int) -> None:
            self._run(
                f"INSERT INTO {table} SETTINGS date_time_input_format='best_effort' FORMAT JSONEachRow",
                handle.read(),
            )

    def test_fresh_migration_fixture_load_contract_queries_and_constraints(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = root / "clickhouse"
            result = subprocess.run(
                ["clickhouse", "local", "--path", str(store), "--multiquery"],
                input=MIGRATION.read_bytes(),
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            client = self.LocalClient(store)
            verified = verify_batch(_fixture_batch(root))
            self.assertEqual(load_batch(verified, client)["status"], "loaded")
            self.assertEqual(load_batch(verified, client)["status"], "already_loaded")
            self.assertEqual(client.scalar("SELECT count() FROM analytics_hotspot_observations_v1"), "2")
            self.assertEqual(client.scalar("SELECT count() FROM analytics_daily_coverage_v1"), "3")
            self.assertEqual(client.scalar("SELECT count() FROM analytics_provinces_v1"), "2")
            self.assertEqual(
                client.scalar(
                    "SELECT count() FROM analytics_daily_coverage_v1 "
                    "WHERE coverage_status='known_satellite_gap' AND observation_count IS NULL"
                ),
                "2",
            )
            self.assertEqual(
                client.scalar(
                    "SELECT count() FROM analytics_hotspot_observations_v1 "
                    "WHERE province_code='14' AND toDate(acquired_at_utc) BETWEEN '2023-07-25' AND '2023-07-27'"
                ),
                "1",
            )
            self.assertEqual(
                client.scalar(
                    "SELECT count() FROM analytics_hotspot_observations_v1 "
                    "WHERE geo_assignment_status!='assigned' AND province_code IS NULL"
                ),
                "1",
            )
            with self.assertRaises(RuntimeError):
                client._run(
                    "INSERT INTO de_hotspot_observations_v1 "
                    "SELECT * REPLACE(toDateTime64('2023-07-26 00:00:00', 0, 'UTC') AS acquired_at_utc) "
                    "FROM de_hotspot_observations_v1 LIMIT 1"
                )

    def test_uncommitted_rows_are_invisible_retry_fails_then_clean_reload_is_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = root / "clickhouse"
            result = subprocess.run(
                ["clickhouse", "local", "--path", str(store), "--multiquery"],
                input=MIGRATION.read_bytes(),
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            client = self.LocalClient(store)
            verified = verify_batch(_fixture_batch(root))

            # Reproduce a crash after all data inserts but before the batch visibility commit.
            observations = (verified.path / "observations.ndjson").read_bytes()
            client._run(
                "INSERT INTO de_hotspot_observations_v1 "
                "SETTINGS date_time_input_format='best_effort' FORMAT JSONEachRow",
                observations,
            )
            for artifact, table in (
                ("daily_coverage.ndjson", "de_daily_coverage_v1"),
                ("provinces.ndjson", "de_provinces_v1"),
            ):
                rows = []
                for line in (verified.path / artifact).read_text().splitlines():
                    row = json.loads(line)
                    row["load_batch_id"] = verified.batch_id
                    rows.append(json.dumps(row, separators=(",", ":")))
                client._run(
                    f"INSERT INTO {table} "
                    "SETTINGS date_time_input_format='best_effort' FORMAT JSONEachRow",
                    ("\n".join(rows) + "\n").encode(),
                )

            for view in (
                "analytics_hotspot_observations_v1",
                "analytics_daily_coverage_v1",
                "analytics_provinces_v1",
                "analytics_ingestion_batches_v1",
            ):
                self.assertEqual(client.scalar(f"SELECT count() FROM {view}"), "0")
            with self.assertRaisesRegex(LoadError, "operator cleanup"):
                load_batch(verified, client)

            client._run("TRUNCATE TABLE de_hotspot_observations_v1")
            client._run("TRUNCATE TABLE de_daily_coverage_v1")
            client._run("TRUNCATE TABLE de_provinces_v1")
            self.assertEqual(load_batch(verified, client)["status"], "loaded")
            self.assertEqual(client.scalar("SELECT count() FROM analytics_hotspot_observations_v1"), "2")
            self.assertEqual(client.scalar("SELECT count() FROM analytics_daily_coverage_v1"), "3")
            self.assertEqual(client.scalar("SELECT count() FROM analytics_provinces_v1"), "2")
            self.assertEqual(client.scalar("SELECT uniqExact(date_utc) FROM analytics_daily_coverage_v1"), "3")


if __name__ == "__main__":
    unittest.main()
