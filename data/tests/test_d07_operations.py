import tempfile
import unittest
from pathlib import Path
import shutil
import subprocess
import io
import json
import os
import sys
from typing import BinaryIO
from unittest import mock

import data.scripts.operate_pipeline_v1 as operations
import data.scripts.ingest_firms_v1 as ingestion
from data.scripts.load_clickhouse_v1 import (
    LoadError,
    load_batch,
    single_writer_lock,
    verify_batch,
)
from data.scripts.operate_pipeline_v1 import (
    audit_publication,
    orphan_counts,
    preflight,
    recover_orphans,
    recover_orphans_locked,
    recovery_plan,
)
from data.tests.test_d06_clickhouse import (
    MIGRATION,
    _fixture_batch,
)
from data.scripts.ingest_firms_v1 import ingest
from data.tests.test_d05_ingestion import (
    BOUNDARY_PROVENANCE,
    SOURCE_URL,
    VALID_ROW,
    write_csv,
)
from data.tests.boundary_fixture import write_synthetic_boundary

QA_SQL = Path("data/clickhouse/qa/d07_operations.sql")


class FakeScalarClient:
    def __init__(self, values: list[str]):
        self.values = values
        self.sql: list[str] = []

    def scalar(self, sql: str) -> str:
        self.sql.append(sql)
        return self.values.pop(0)


class LocalClient:
    def __init__(self, path: Path):
        self.path = path

    def _run(self, query: str, data: bytes | None = None) -> str:
        result = subprocess.run(
            [
                "clickhouse", "local", "--path", str(self.path),
                "--database", "wildfire", "--query", query,
            ],
            input=data, capture_output=True, check=False,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.decode())
        return result.stdout.decode().strip()

    def scalar(self, sql: str) -> str:
        return self._run(sql + " FORMAT TabSeparatedRaw")

    def insert_file(self, table: str, handle: BinaryIO, size: int) -> None:
        self._run(
            f"INSERT INTO {table} SETTINGS date_time_input_format='best_effort' "
            "FORMAT JSONEachRow",
            handle.read(),
        )


class D07OperationsTests(unittest.TestCase):
    def test_offline_preflight_is_read_only_and_reconciles_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.csv"
            write_csv(source, [VALID_ROW])
            boundary = root / "boundary.geojson"
            boundary_sha = write_synthetic_boundary(boundary)
            provenance_payload = json.loads(
                BOUNDARY_PROVENANCE.read_text(encoding="utf-8")
            )
            provenance_payload["artifacts"]["canonical"]["sha256"] = boundary_sha
            provenance = root / "boundary-provenance.json"
            provenance.write_text(json.dumps(provenance_payload), encoding="utf-8")
            with mock.patch.object(
                ingestion, "BOUNDARY_CANONICAL_SHA256", boundary_sha
            ):
                manifest = ingest(
                    source_csv=source,
                    boundary_geojson=boundary,
                    boundary_provenance=provenance,
                    output_root=root / "published",
                    source_url=SOURCE_URL,
                    retrieved_at_utc="2026-10-26T00:00:00Z",
                )
            result = preflight(root / "published" / manifest["ingestion_batch_id"])
        self.assertTrue(result["safe_to_load"])
        self.assertFalse(result["database_contacted"])
        self.assertFalse(result["database_changed"])

    def test_offline_preflight_rejects_corrupt_input(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            batch = _fixture_batch(Path(temp))
            (batch / "observations.ndjson").write_text("corrupt\n", encoding="utf-8")
            with self.assertRaisesRegex(LoadError, "byte count mismatch"):
                preflight(batch)

    def test_publication_and_freshness_audit_passes_exact_thresholds(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            batch = verify_batch(_fixture_batch(Path(temp)))
            client = FakeScalarClient([
                "1", "1", "2", "365", "2", "0", "38", "0", "0",
                "2026-10-26T10:00:00Z",
            ])
            result = audit_publication(batch, client)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["freshness"]["coverage_end_utc"], "2023-07-25T03:21:00Z")
        self.assertIn("historical_snapshot", result["freshness"]["semantics"])
        self.assertFalse(result["database_changed"])

    def test_publication_audit_fails_on_gap_or_orphan_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            batch = verify_batch(_fixture_batch(Path(temp)))
            client = FakeScalarClient([
                "1", "1", "2", "365", "1", "1", "38", "0", "3",
                "2026-10-26T10:00:00Z",
            ])
            result = audit_publication(batch, client)
        self.assertEqual(result["status"], "fail")
        self.assertFalse(result["checks"]["known_gap_days"])
        self.assertFalse(result["checks"]["gap_observations"])
        self.assertFalse(result["checks"]["unpublished_rows"])

    def test_recovery_plan_never_mutates(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            batch = verify_batch(_fixture_batch(Path(temp)))
            client = FakeScalarClient(["0", "2", "365", "38"])
            result = recovery_plan(batch, client)
        self.assertTrue(result["action_required"])
        self.assertFalse(result["database_changed"])
        self.assertFalse(any("ALTER TABLE" in sql for sql in client.sql))

    def test_recovery_refuses_published_or_mismatched_batch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            batch = verify_batch(_fixture_batch(Path(temp)))
            with self.assertRaisesRegex(LoadError, "exactly match"):
                recover_orphans(batch, FakeScalarClient([]), confirm_batch="wrong")
            with self.assertRaisesRegex(LoadError, "already published"):
                orphan_counts(batch, FakeScalarClient(["1"]))

    def test_recovery_contends_with_exact_loader_lock_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            batch = verify_batch(_fixture_batch(root))
            lock_dir = root / "locks"
            scope = f"http://127.0.0.1:8123|wildfire|{batch.batch_id}"
            client = FakeScalarClient([])
            with single_writer_lock(lock_dir, scope):
                with self.assertRaisesRegex(LoadError, "single-writer lock"):
                    recover_orphans_locked(
                        batch,
                        client,
                        confirm_batch=batch.batch_id,
                        lock_dir=lock_dir,
                        lock_scope=scope,
                    )
            self.assertEqual(client.sql, [])

    def test_cli_audit_failure_prints_json_and_exits_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            batch_dir = _fixture_batch(Path(temp))
            client = FakeScalarClient([
                "1", "1", "1", "365", "2", "0", "38", "0", "0",
                "2026-10-26T10:00:00Z",
            ])
            argv = [
                "operate_pipeline_v1.py", "audit", "--batch-dir", str(batch_dir),
            ]
            output = io.StringIO()
            with mock.patch.object(sys, "argv", argv), \
                    mock.patch.dict(os.environ, {"CLICKHOUSE_PASSWORD": ""}), \
                    mock.patch.object(operations, "HttpClickHouse", return_value=client), \
                    mock.patch("sys.stdout", output), \
                    self.assertRaises(SystemExit) as raised:
                operations.main()
            self.assertEqual(raised.exception.code, 1)
            self.assertEqual(json.loads(output.getvalue())["status"], "fail")

    def test_confirmed_recovery_deletes_only_exact_batch_and_reconciles(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            batch = verify_batch(_fixture_batch(Path(temp)))
            client = FakeScalarClient([
                "0", "2", "365", "38",  # before
                "", "", "",             # synchronous mutations
                "0", "0", "0", "0",   # after
            ])
            result = recover_orphans(batch, client, confirm_batch=batch.batch_id)
        self.assertTrue(result["database_changed"])
        mutations = [sql for sql in client.sql if "ALTER TABLE" in sql]
        self.assertEqual(len(mutations), 3)
        self.assertTrue(all(batch.batch_id in sql for sql in mutations))
        self.assertTrue(all("mutations_sync = 2" in sql for sql in mutations))


@unittest.skipUnless(shutil.which("clickhouse"), "clickhouse-local is unavailable")
class D07LocalRecoveryIntegrationTests(unittest.TestCase):
    def test_interrupted_load_plan_cleanup_and_clean_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = root / "clickhouse"
            result = subprocess.run(
                ["clickhouse", "local", "--path", str(store), "--multiquery"],
                input=MIGRATION.read_bytes(), capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            client = LocalClient(store)
            batch = verify_batch(_fixture_batch(root))

            observations = batch.path / "observations.ndjson"
            with observations.open("rb") as handle:
                client.insert_file("de_hotspot_observations_v1", handle, observations.stat().st_size)

            plan = recovery_plan(batch, client)
            self.assertEqual(plan["orphan_rows"], {"observations": 2, "coverage": 0, "provinces": 0})
            recovered = recover_orphans(batch, client, confirm_batch=batch.batch_id)
            self.assertEqual(recovered["remaining_rows"], {"observations": 0, "coverage": 0, "provinces": 0})
            self.assertEqual(load_batch(batch, client)["status"], "loaded")
            audit = audit_publication(batch, client)
            self.assertEqual(audit["status"], "fail")  # synthetic fixture has 3, not 365 days
            with self.assertRaisesRegex(RuntimeError, "D07 publication QA failed"):
                client._run(QA_SQL.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
