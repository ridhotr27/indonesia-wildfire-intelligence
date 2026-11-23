#!/usr/bin/env python3
"""Checksum-verify and publish one immutable D05 batch to ClickHouse."""

from __future__ import annotations

import argparse
import base64
import contextlib
import fcntl
import hashlib
import json
import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Protocol

CONTRACT_VERSION = "1.0.0"
PRODUCT_ID = "VNP14IMG.002_SNPP_FIRMS_SP"
ARTIFACT_TABLES = {
    "observations.ndjson": "de_hotspot_observations_v1",
    "daily_coverage.ndjson": "de_daily_coverage_v1",
    "provinces.ndjson": "de_provinces_v1",
    "ingestion_batch.ndjson": "de_ingestion_batches_v1",
}
ALLOWED_TABLES = set(ARTIFACT_TABLES.values()) | {
    "de_hotspot_observations_v11",
    "de_daily_coverage_v11",
    "de_provinces_v11",
    "de_ingestion_batches_v11",
    "de_dataset_releases_v1",
    "de_dataset_release_batches_v1",
    "de_active_release_events_v1",
}


class LoadError(RuntimeError):
    """A batch cannot be safely loaded or reconciled."""


@contextlib.contextmanager
def single_writer_lock(lock_dir: Path, scope: str):
    """Fail fast when another same-host loader owns this credential-free scope."""
    lock_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock_dir.chmod(0o700)
    lock_name = hashlib.sha256(scope.encode("utf-8")).hexdigest() + ".lock"
    lock_path = lock_dir / lock_name
    with lock_path.open("a+b") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise LoadError("another same-host loader holds the single-writer lock") from exc
        try:
            yield lock_path
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_single_row(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    if len(rows) != 1 or not isinstance(rows[0], dict):
        raise LoadError(f"{path.name} must contain exactly one JSON object")
    return rows[0]


def _validate_rows(path: Path, *, expected_count: int, batch_id: str | None) -> None:
    count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise LoadError(f"invalid JSON in {path.name} line {line_number}") from exc
            if not isinstance(row, dict) or row.get("contract_version") != CONTRACT_VERSION:
                raise LoadError(f"invalid contract row in {path.name} line {line_number}")
            if batch_id is not None and row.get("ingestion_batch_id") != batch_id:
                raise LoadError(f"batch identity mismatch in {path.name} line {line_number}")
            count += 1
    if count != expected_count:
        raise LoadError(f"artifact row count mismatch: {path.name}")


@dataclass(frozen=True)
class VerifiedBatch:
    path: Path
    manifest: dict[str, Any]
    batch_row: dict[str, Any]

    @property
    def batch_id(self) -> str:
        return str(self.manifest["ingestion_batch_id"])


def verify_batch(batch_dir: Path) -> VerifiedBatch:
    manifest_path = batch_dir / "manifest.json"
    if not manifest_path.is_file():
        raise LoadError("manifest.json is missing")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise LoadError("manifest.json is invalid") from exc
    if not isinstance(manifest, dict):
        raise LoadError("manifest.json must be an object")
    if manifest.get("clickhouse_ingestion_authorized") is False:
        raise LoadError("candidate batch is not authorized for ClickHouse ingestion")
    required = set(ARTIFACT_TABLES)
    if (
        manifest.get("contract_version") != CONTRACT_VERSION
        or manifest.get("product_id") != PRODUCT_ID
        or manifest.get("publication") != {"atomic": True, "state": "published"}
        or manifest.get("ingestion_batch_id") != batch_dir.name
        or set(manifest.get("artifacts", {})) != required
    ):
        raise LoadError("manifest identity or artifact set is not approved")
    for name in sorted(required):
        path = batch_dir / name
        metadata = manifest["artifacts"][name]
        if not path.is_file():
            raise LoadError(f"verified artifact is missing: {name}")
        if path.stat().st_size != metadata.get("bytes"):
            raise LoadError(f"artifact byte count mismatch: {name}")
        if sha256_file(path) != metadata.get("sha256"):
            raise LoadError(f"artifact checksum mismatch: {name}")
    batch_row = _read_single_row(batch_dir / "ingestion_batch.ndjson")
    counts = manifest.get("counts", {})
    expected = {
        "contract_version": CONTRACT_VERSION,
        "ingestion_batch_id": batch_dir.name,
        "product_id": PRODUCT_ID,
        "source_artifact_sha256": manifest.get("source_artifact_sha256"),
        "canonical_row_count": counts.get("canonical_rows"),
        "source_row_count": counts.get("source_rows"),
        "duplicate_excess_rows": counts.get("duplicate_excess_rows"),
        "rejected_row_count": counts.get("rejected_rows"),
        "publication_status": "published",
    }
    for key, value in expected.items():
        if batch_row.get(key) != value:
            raise LoadError(f"batch row does not match manifest: {key}")
    _validate_rows(
        batch_dir / "observations.ndjson",
        expected_count=int(counts.get("canonical_rows", -1)),
        batch_id=batch_dir.name,
    )
    _validate_rows(
        batch_dir / "daily_coverage.ndjson",
        expected_count=int(counts.get("coverage_days", -1)),
        batch_id=None,
    )
    _validate_rows(
        batch_dir / "provinces.ndjson",
        expected_count=int(counts.get("provinces", -1)),
        batch_id=None,
    )
    return VerifiedBatch(batch_dir, manifest, batch_row)


class ClickHouse(Protocol):
    def scalar(self, sql: str) -> str: ...
    def insert_file(self, table: str, handle: BinaryIO, size: int) -> None: ...


class HttpClickHouse:
    """Minimal HTTP client; password is sourced from environment, never CLI args."""

    def __init__(self, url: str, database: str, username: str, password: str, timeout: int):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise LoadError("ClickHouse URL must be HTTP(S)")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise LoadError("ClickHouse URL must not contain credentials, query, or fragment")
        self.url = url.rstrip("/") + "/"
        self.database = database
        self.authorization = "Basic " + base64.b64encode(
            f"{username}:{password}".encode()
        ).decode()
        self.timeout = timeout

    def _request(self, query: str, body: BinaryIO | bytes = b"", size: int | None = None) -> bytes:
        target = self.url + "?" + urllib.parse.urlencode(
            {"database": self.database, "query": query, "wait_end_of_query": 1}
        )
        headers = {"Authorization": self.authorization}
        if size is not None:
            headers["Content-Length"] = str(size)
        request = urllib.request.Request(target, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise LoadError("ClickHouse request failed") from exc

    def scalar(self, sql: str) -> str:
        return self._request(sql + " FORMAT TabSeparatedRaw").decode().strip()

    def insert_file(self, table: str, handle: BinaryIO, size: int) -> None:
        if table not in ALLOWED_TABLES:
            raise LoadError("target table is not allowlisted")
        self._request(
            f"INSERT INTO {table} SETTINGS date_time_input_format='best_effort' FORMAT JSONEachRow",
            handle,
            size,
        )


def load_batch(batch: VerifiedBatch, client: ClickHouse) -> dict[str, Any]:
    escaped = batch.batch_id.replace("'", "''")
    existing = client.scalar(
        "SELECT count() FROM analytics_ingestion_batches_v1 "
        f"WHERE ingestion_batch_id = '{escaped}'"
    )
    if existing == "1":
        fingerprint = client.scalar(
            "SELECT concat(source_artifact_sha256, ':', toString(canonical_row_count)) "
            "FROM analytics_ingestion_batches_v1 "
            f"WHERE ingestion_batch_id = '{escaped}'"
        )
        expected = (
            f"{batch.batch_row['source_artifact_sha256']}:"
            f"{batch.batch_row['canonical_row_count']}"
        )
        if fingerprint != expected:
            raise LoadError("existing immutable batch fingerprint mismatch")
        return {"status": "already_loaded", "ingestion_batch_id": batch.batch_id}
    if existing != "0":
        raise LoadError("batch identity is not unique")
    orphan_count = client.scalar(
        "SELECT sum(rows) FROM ("
        f"SELECT count() rows FROM de_hotspot_observations_v1 WHERE ingestion_batch_id = '{escaped}' "
        "UNION ALL "
        f"SELECT count() rows FROM de_daily_coverage_v1 WHERE load_batch_id = '{escaped}' "
        "UNION ALL "
        f"SELECT count() rows FROM de_provinces_v1 WHERE load_batch_id = '{escaped}'"
        ")"
    )
    if orphan_count not in {"0", ""}:
        raise LoadError("unpublished partial rows exist; operator cleanup is required")

    province_count = client.scalar("SELECT count() FROM de_provinces_v1")
    ordered = ["provinces.ndjson", "observations.ndjson", "daily_coverage.ndjson"]
    for name in ordered:
        if name == "provinces.ndjson" and province_count == "38":
            continue
        if name == "provinces.ndjson" and province_count != "0":
            raise LoadError("province reference table is partial or unexpected")
        path = batch.path / name
        if name in {"provinces.ndjson", "daily_coverage.ndjson"}:
            temporary_name: str | None = None
            try:
                with tempfile.NamedTemporaryFile("wb", delete=False) as temporary:
                    temporary_name = temporary.name
                    with path.open("r", encoding="utf-8") as source:
                        for line in source:
                            row = json.loads(line)
                            row["load_batch_id"] = batch.batch_id
                            temporary.write(
                                (json.dumps(row, separators=(",", ":")) + "\n").encode()
                            )
                enriched = Path(temporary_name)
                with enriched.open("rb") as handle:
                    client.insert_file(
                        ARTIFACT_TABLES[name], handle, enriched.stat().st_size
                    )
            finally:
                if temporary_name is not None:
                    Path(temporary_name).unlink(missing_ok=True)
        else:
            with path.open("rb") as handle:
                client.insert_file(ARTIFACT_TABLES[name], handle, path.stat().st_size)
    # Visibility commit: published views cannot expose batch-owned rows before this insert.
    batch_path = batch.path / "ingestion_batch.ndjson"
    with batch_path.open("rb") as handle:
        client.insert_file(ARTIFACT_TABLES[batch_path.name], handle, batch_path.stat().st_size)

    published = client.scalar(
        "SELECT concat(toString(canonical_row_count), ':', toString(source_row_count)) "
        "FROM analytics_ingestion_batches_v1 "
        f"WHERE ingestion_batch_id = '{escaped}'"
    )
    expected_counts = (
        f"{batch.batch_row['canonical_row_count']}:{batch.batch_row['source_row_count']}"
    )
    if published != expected_counts:
        raise LoadError("published batch count reconciliation failed")
    return {"status": "loaded", "ingestion_batch_id": batch.batch_id}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-dir", type=Path, required=True)
    parser.add_argument("--url", default=os.getenv("CLICKHOUSE_URL", "http://127.0.0.1:8123"))
    parser.add_argument("--database", default=os.getenv("CLICKHOUSE_DATABASE", "wildfire"))
    parser.add_argument("--username", default=os.getenv("CLICKHOUSE_USER", "default"))
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument(
        "--lock-dir",
        type=Path,
        default=Path(os.getenv("D06_LOCK_DIR", "/tmp/indonesia-wildfire-clickhouse-locks")),
    )
    args = parser.parse_args()
    password = os.getenv("CLICKHOUSE_PASSWORD")
    if password is None:
        raise SystemExit("CLICKHOUSE_PASSWORD must be set (an empty local password is allowed)")
    verified = verify_batch(args.batch_dir.resolve())
    scope = f"{args.url}|{args.database}|{verified.batch_id}"
    with single_writer_lock(args.lock_dir.resolve(), scope):
        result = load_batch(
            verified,
            HttpClickHouse(args.url, args.database, args.username, password, args.timeout),
        )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
