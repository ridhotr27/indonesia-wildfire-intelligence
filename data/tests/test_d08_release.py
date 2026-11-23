from __future__ import annotations

import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any, BinaryIO

from data.scripts.load_clickhouse_v1 import LoadError
from data.scripts.release_clickhouse_v11 import (
    VerifiedRelease,
    activate,
    rollback,
    verify_release,
)

ROOT = Path(__file__).resolve().parents[2]
BASE_MIGRATION = ROOT / "data/clickhouse/migrations/001_d06_physical_model.sql"
D08_MIGRATION = ROOT / "data/clickhouse/migrations/003_d08_multiyear_release.sql"


class FakeClient:
    def __init__(self, values: list[str]):
        self.values = values
        self.inserts: list[tuple[str, list[dict[str, Any]]]] = []

    def scalar(self, sql: str) -> str:
        return self.values.pop(0)

    def insert_file(self, table: str, handle: BinaryIO, size: int) -> None:
        self.inserts.append((table, [json.loads(line) for line in handle.read().decode().splitlines()]))


class D08ReleaseTests(unittest.TestCase):
    def test_activation_is_one_atomic_pointer_insert_after_all_preflight_checks(self) -> None:
        release = VerifiedRelease(
            Path("release.json"), {"release_id": "d08-2023-2025-v1"},
            {}, "a" * 64, (),
        )
        client = FakeClient(["1", "3", "453630", "1096", "7"])
        result = activate(release, client)
        self.assertEqual(result["activation_sequence"], 8)
        self.assertEqual(len(client.inserts), 1)
        table, rows = client.inserts[0]
        self.assertEqual(table, "de_active_release_events_v1")
        self.assertEqual(rows[0]["release_id"], "d08-2023-2025-v1")
        self.assertEqual(rows[0]["contract_version"], "1.1.0")

    def test_activation_failure_never_writes_pointer(self) -> None:
        release = VerifiedRelease(
            Path("release.json"), {"release_id": "d08-2023-2025-v1"},
            {}, "a" * 64, (),
        )
        client = FakeClient(["1", "2", "453630", "1096"])
        with self.assertRaisesRegex(LoadError, "activation preflight failed"):
            activate(release, client)
        self.assertEqual(client.inserts, [])

    def test_rollback_is_append_only_and_requires_authorization_checksum(self) -> None:
        client = FakeClient(["8"])
        result = rollback(client, "legacy-v1.0.0", "b" * 64)
        self.assertEqual(result["activation_sequence"], 9)
        self.assertEqual(client.inserts[0][1][0]["action"], "rollback")
        self.assertEqual(client.inserts[0][1][0]["contract_version"], "1.0.0")
        with self.assertRaisesRegex(LoadError, "authorization checksum"):
            rollback(FakeClient([]), "legacy-v1.0.0", "unsafe")

    def test_authorization_must_be_checksum_bound_and_role_complete(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = root / "release.json"
            manifest.write_text(json.dumps({}), encoding="utf-8")
            auth = root / "authorization.json"
            auth.write_text(json.dumps({"authorized": True}), encoding="utf-8")
            with self.assertRaisesRegex(LoadError, "release manifest identity"):
                verify_release(manifest, auth)


@unittest.skipUnless(shutil.which("clickhouse"), "clickhouse-local is unavailable")
class D08MigrationTests(unittest.TestCase):
    def test_additive_migration_keeps_legacy_release_active_and_views_queryable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = Path(temp) / "clickhouse"
            for migration in (BASE_MIGRATION, D08_MIGRATION):
                result = subprocess.run(
                    ["clickhouse", "local", "--path", str(store), "--multiquery"],
                    input=migration.read_bytes(), capture_output=True, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr.decode())
            result = subprocess.run(
                ["clickhouse", "local", "--path", str(store), "--database", "wildfire", "--query",
                 "SELECT argMax(release_id, activation_sequence), argMax(contract_version, activation_sequence) FROM de_active_release_events_v1"],
                capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(result.stdout.decode().strip(), "legacy-v1.0.0\t1.0.0")
            query = subprocess.run(
                ["clickhouse", "local", "--path", str(store), "--database", "wildfire", "--query",
                 "SELECT count() FROM analytics_hotspot_observations_v1"],
                capture_output=True, check=False,
            )
            self.assertEqual(query.returncode, 0, query.stderr.decode())
            self.assertEqual(query.stdout.decode().strip(), "0")


if __name__ == "__main__":
    unittest.main()
