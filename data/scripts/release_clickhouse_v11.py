#!/usr/bin/env python3
"""Verify, load, activate, audit, or roll back a checksum-bound D08 release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO, Protocol

try:
    from data.scripts.load_clickhouse_v1 import HttpClickHouse, LoadError, sha256_file, single_writer_lock
except ModuleNotFoundError:
    from load_clickhouse_v1 import HttpClickHouse, LoadError, sha256_file, single_writer_lock

CONTRACT_VERSION = "1.1.0"
PRODUCT_ID = "VNP14IMG.002_SNPP_FIRMS_SP"
YEARS = {2023, 2024, 2025}
EXPECTED_TOTAL = 453_630
EXPECTED_COVERAGE = 1_096
EXPECTED_PROVINCES = 38
EXPECTED_BY_YEAR = {2023: 253_388, 2024: 104_186, 2025: 96_056}
EXPECTED_SOURCE_SHA = {
    2023: "2dba3b772b5a3a2cc0feed128af74637810021dd41dc34d584cb99b40411665a",
    2024: "23be16b48fb6ac3a21fd2130e66149d305af71c62bbb39e76a6a0632a9dd69bd",
    2025: "11abffff52dedfe985a8f03c59b8ebff55a903bd0de07d4897f76d734788d811",
}
ARTIFACT_TABLES = {
    "observations.ndjson": "de_hotspot_observations_v11",
    "daily_coverage.ndjson": "de_daily_coverage_v11",
    "provinces.ndjson": "de_provinces_v11",
    "ingestion_batch.ndjson": "de_ingestion_batches_v11",
}
REQUIRED_APPROVALS = {"tech_lead", "data_engineer", "backend_engineer", "frontend_engineer"}


class ReleaseClient(Protocol):
    def scalar(self, sql: str) -> str: ...
    def insert_file(self, table: str, handle: BinaryIO, size: int) -> None: ...


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _canonical_sha(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LoadError(f"invalid JSON artifact: {path.name}") from exc
    if not isinstance(value, dict):
        raise LoadError(f"JSON artifact must be an object: {path.name}")
    return value


def _rows(path: Path) -> list[dict[str, Any]]:
    result = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise ValueError
                    result.append(row)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise LoadError(f"invalid NDJSON artifact: {path.name}") from exc
    return result


@dataclass(frozen=True)
class ReleaseBatch:
    year: int
    path: Path
    manifest: dict[str, Any]
    batch_row: dict[str, Any]

    @property
    def batch_id(self) -> str:
        return str(self.manifest["ingestion_batch_id"])


@dataclass(frozen=True)
class VerifiedRelease:
    manifest_path: Path
    manifest: dict[str, Any]
    authorization: dict[str, Any]
    authorization_sha256: str
    batches: tuple[ReleaseBatch, ...]

    @property
    def release_id(self) -> str:
        return str(self.manifest["release_id"])


def _verify_batch(entry: dict[str, Any], manifest_dir: Path) -> ReleaseBatch:
    year = int(entry.get("source_year", 0))
    path = (manifest_dir / str(entry.get("batch_path", ""))).resolve()
    batch_manifest_path = path / "manifest.json"
    manifest = _read_json(batch_manifest_path)
    if (
        year not in YEARS
        or manifest.get("contract_version") != CONTRACT_VERSION
        or manifest.get("product_id") != PRODUCT_ID
        or manifest.get("source_year") != year
        or manifest.get("ingestion_batch_id") != path.name
        or manifest.get("source_artifact_sha256") != EXPECTED_SOURCE_SHA[year]
        or manifest.get("counts", {}).get("canonical_rows") != EXPECTED_BY_YEAR[year]
        or manifest.get("clickhouse_ingestion_authorized") is not False
        or entry.get("ingestion_batch_id") != path.name
        or entry.get("source_artifact_sha256") != EXPECTED_SOURCE_SHA[year]
        or entry.get("expected_rows") != EXPECTED_BY_YEAR[year]
        or entry.get("batch_manifest_sha256") != sha256_file(batch_manifest_path)
    ):
        raise LoadError(f"release batch identity mismatch for {year}")
    artifacts = manifest.get("artifacts", {})
    if set(artifacts) != set(ARTIFACT_TABLES):
        raise LoadError(f"release batch artifact set mismatch for {year}")
    for name, metadata in artifacts.items():
        artifact = path / name
        if (
            not artifact.is_file()
            or artifact.stat().st_size != metadata.get("bytes")
            or sha256_file(artifact) != metadata.get("sha256")
        ):
            raise LoadError(f"release batch artifact mismatch: {year}/{name}")
        rows = _rows(artifact)
        expected = 1 if name == "ingestion_batch.ndjson" else (
            EXPECTED_BY_YEAR[year] if name == "observations.ndjson" else
            (366 if year == 2024 else 365) if name == "daily_coverage.ndjson" else 38
        )
        if len(rows) != expected:
            raise LoadError(f"release batch row count mismatch: {year}/{name}")
        if any(row.get("contract_version") != CONTRACT_VERSION for row in rows):
            raise LoadError(f"release batch contract mismatch: {year}/{name}")
    batch_rows = _rows(path / "ingestion_batch.ndjson")
    return ReleaseBatch(year, path, manifest, batch_rows[0])


def verify_release(manifest_path: Path, authorization_path: Path) -> VerifiedRelease:
    manifest_path = manifest_path.resolve()
    manifest = _read_json(manifest_path)
    entries = manifest.get("batches")
    if (
        manifest.get("schema_version") != "1.0.0"
        or manifest.get("contract_version") != CONTRACT_VERSION
        or manifest.get("product_id") != PRODUCT_ID
        or manifest.get("environment") != "local_development"
        or manifest.get("expected_observation_rows") != EXPECTED_TOTAL
        or manifest.get("expected_coverage_rows") != EXPECTED_COVERAGE
        or manifest.get("expected_provinces") != EXPECTED_PROVINCES
        or not isinstance(entries, list)
        or len(entries) != 3
    ):
        raise LoadError("release manifest identity or totals are invalid")
    batches = tuple(_verify_batch(entry, manifest_path.parent) for entry in entries)
    if {batch.year for batch in batches} != YEARS:
        raise LoadError("release must contain exactly one batch for each year 2023-2025")
    authorization = _read_json(authorization_path.resolve())
    manifest_sha = sha256_file(manifest_path)
    approvals = authorization.get("approvals")
    approved_roles = {
        item.get("role") for item in approvals or []
        if isinstance(item, dict) and item.get("decision") == "approved"
    }
    if (
        authorization.get("release_id") != manifest.get("release_id")
        or authorization.get("release_manifest_sha256") != manifest_sha
        or authorization.get("environment") != "local_development"
        or authorization.get("authorized") is not True
        or not REQUIRED_APPROVALS.issubset(approved_roles)
    ):
        raise LoadError("release authorization is missing, incomplete, or not checksum-bound")
    return VerifiedRelease(
        manifest_path, manifest, authorization, sha256_file(authorization_path), batches
    )


def build_candidate_manifest(release_id: str, batch_dirs: list[Path], output: Path) -> dict[str, Any]:
    if len(batch_dirs) != 3:
        raise LoadError("exactly three batch directories are required")
    entries = []
    for path in batch_dirs:
        path = path.resolve()
        manifest = _read_json(path / "manifest.json")
        year = int(manifest.get("source_year", 0))
        if year not in YEARS:
            raise LoadError("candidate batch year is invalid")
        entries.append({
            "source_year": year,
            "ingestion_batch_id": manifest.get("ingestion_batch_id"),
            "batch_path": os.path.relpath(path, output.resolve().parent),
            "batch_manifest_sha256": sha256_file(path / "manifest.json"),
            "source_artifact_sha256": manifest.get("source_artifact_sha256"),
            "expected_rows": manifest.get("counts", {}).get("canonical_rows"),
        })
    payload = {
        "schema_version": "1.0.0", "release_id": release_id,
        "contract_version": CONTRACT_VERSION, "product_id": PRODUCT_ID,
        "environment": "local_development", "status": "candidate",
        "expected_observation_rows": EXPECTED_TOTAL,
        "expected_coverage_rows": EXPECTED_COVERAGE,
        "expected_provinces": EXPECTED_PROVINCES,
        "batches": sorted(entries, key=lambda item: item["source_year"]),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _insert_rows(client: ReleaseClient, table: str, rows: list[dict[str, Any]]) -> None:
    payload = b"".join(
        (json.dumps(row, separators=(",", ":")) + "\n").encode() for row in rows
    )
    with tempfile.TemporaryFile() as handle:
        handle.write(payload)
        handle.seek(0)
        client.insert_file(table, handle, len(payload))


def load_hidden(release: VerifiedRelease, client: ReleaseClient) -> dict[str, Any]:
    release_id = _literal(release.release_id)
    existing_release = client.scalar(
        f"SELECT count() FROM de_dataset_releases_v1 WHERE release_id = {release_id}"
    )
    if existing_release == "1":
        mappings = client.scalar(
            f"SELECT count() FROM de_dataset_release_batches_v1 WHERE release_id = {release_id}"
        )
        if mappings != "3":
            raise LoadError("loaded release metadata is incomplete; operator recovery is required")
        return {"status": "already_loaded_hidden", "release_id": release.release_id}
    if existing_release != "0":
        raise LoadError("release identity is not unique")
    for batch in release.batches:
        bid = _literal(batch.batch_id)
        existing = client.scalar(
            f"SELECT count() FROM de_ingestion_batches_v11 WHERE ingestion_batch_id = {bid}"
        )
        if existing == "0":
            orphan_rows = client.scalar(
                "SELECT sum(rows) FROM ("
                f"SELECT count() rows FROM de_hotspot_observations_v11 WHERE ingestion_batch_id = {bid} UNION ALL "
                f"SELECT count() rows FROM de_daily_coverage_v11 WHERE load_batch_id = {bid} UNION ALL "
                f"SELECT count() rows FROM de_provinces_v11 WHERE load_batch_id = {bid})"
            )
            if orphan_rows not in {"", "0"}:
                raise LoadError("partial hidden batch rows exist; operator recovery is required")
            for name in ("observations.ndjson", "daily_coverage.ndjson", "provinces.ndjson", "ingestion_batch.ndjson"):
                rows = _rows(batch.path / name)
                if name in {"daily_coverage.ndjson", "provinces.ndjson"}:
                    for row in rows:
                        row["load_batch_id"] = batch.batch_id
                _insert_rows(client, ARTIFACT_TABLES[name], rows)
        elif existing != "1":
            raise LoadError("batch identity is not unique")
        actual = client.scalar(
            f"SELECT count() FROM de_hotspot_observations_v11 WHERE ingestion_batch_id = {bid}"
        )
        if actual != str(EXPECTED_BY_YEAR[batch.year]):
            raise LoadError(f"hidden batch reconciliation failed for {batch.year}")
    stale_mappings = client.scalar(
        f"SELECT count() FROM de_dataset_release_batches_v1 WHERE release_id = {release_id}"
    )
    if stale_mappings != "0":
        raise LoadError("partial release mappings exist; operator recovery is required")
    _insert_rows(client, "de_dataset_release_batches_v1", [{
        "release_id": release.release_id,
        "ingestion_batch_id": batch.batch_id,
        "source_year": batch.year,
        "source_artifact_sha256": EXPECTED_SOURCE_SHA[batch.year],
        "expected_rows": EXPECTED_BY_YEAR[batch.year],
    } for batch in release.batches])
    # Release row is the hidden-load metadata commit; serving views still ignore it
    # until the separate one-row activation event is inserted.
    authorized_at = release.authorization.get("authorized_at_utc")
    _insert_rows(client, "de_dataset_releases_v1", [{
        "release_id": release.release_id,
        "contract_version": CONTRACT_VERSION,
        "product_id": PRODUCT_ID,
        "release_manifest_sha256": sha256_file(release.manifest_path),
        "expected_observation_rows": EXPECTED_TOTAL,
        "expected_coverage_rows": EXPECTED_COVERAGE,
        "expected_provinces": EXPECTED_PROVINCES,
        "authorized_at_utc": authorized_at,
    }])
    return {"status": "loaded_hidden", "release_id": release.release_id}


def _next_sequence(client: ReleaseClient) -> int:
    value = client.scalar("SELECT max(activation_sequence) FROM de_active_release_events_v1")
    return int(value or 0) + 1


def activate(release: VerifiedRelease, client: ReleaseClient) -> dict[str, Any]:
    rid = _literal(release.release_id)
    checks = {
        "release": client.scalar(f"SELECT count() FROM de_dataset_releases_v1 WHERE release_id = {rid}") == "1",
        "batches": client.scalar(f"SELECT count() FROM de_dataset_release_batches_v1 WHERE release_id = {rid}") == "3",
        "observations": client.scalar(
            "SELECT count() FROM de_hotspot_observations_v11 WHERE ingestion_batch_id IN "
            f"(SELECT ingestion_batch_id FROM de_dataset_release_batches_v1 WHERE release_id = {rid})"
        ) == str(EXPECTED_TOTAL),
        "coverage": client.scalar(
            "SELECT count() FROM de_daily_coverage_v11 WHERE load_batch_id IN "
            f"(SELECT ingestion_batch_id FROM de_dataset_release_batches_v1 WHERE release_id = {rid})"
        ) == str(EXPECTED_COVERAGE),
    }
    if not all(checks.values()):
        raise LoadError(f"activation preflight failed: {checks}")
    sequence = _next_sequence(client)
    _insert_rows(client, "de_active_release_events_v1", [{
        "activation_sequence": sequence, "release_id": release.release_id,
        "contract_version": CONTRACT_VERSION, "action": "activate",
        "activated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "authorization_sha256": release.authorization_sha256,
    }])
    return {"status": "activated", "release_id": release.release_id, "activation_sequence": sequence}


def rollback(client: ReleaseClient, target_release: str, authorization_sha256: str) -> dict[str, Any]:
    if target_release == "legacy-v1.0.0":
        contract = "1.0.0"
    else:
        exists = client.scalar(
            "SELECT count() FROM de_dataset_releases_v1 WHERE release_id = " + _literal(target_release)
        )
        if exists != "1":
            raise LoadError("rollback target is not a loaded release")
        contract = CONTRACT_VERSION
    if len(authorization_sha256) != 64:
        raise LoadError("rollback requires a 64-character authorization checksum")
    sequence = _next_sequence(client)
    _insert_rows(client, "de_active_release_events_v1", [{
        "activation_sequence": sequence, "release_id": target_release,
        "contract_version": contract, "action": "rollback",
        "activated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "authorization_sha256": authorization_sha256,
    }])
    return {"status": "rolled_back", "release_id": target_release, "activation_sequence": sequence}


def audit(release: VerifiedRelease, client: ReleaseClient) -> dict[str, Any]:
    rid = _literal(release.release_id)
    actual = {
        "active_release": client.scalar("SELECT argMax(release_id, activation_sequence) FROM de_active_release_events_v1"),
        "contract_versions": client.scalar("SELECT groupUniqArray(contract_version) FROM analytics_hotspot_observations_v1"),
        "observations": client.scalar("SELECT count() FROM analytics_hotspot_observations_v1"),
        "coverage": client.scalar("SELECT count() FROM analytics_daily_coverage_v1"),
        "coverage_unique": client.scalar("SELECT uniqExact(product_id, date_utc) FROM analytics_daily_coverage_v1"),
        "provinces": client.scalar("SELECT count() FROM analytics_provinces_v1"),
        "duplicates": client.scalar("SELECT count() - uniqExact(observation_id) FROM analytics_hotspot_observations_v1"),
        "known_gaps": client.scalar("SELECT count() FROM analytics_daily_coverage_v1 WHERE coverage_status = 'known_satellite_gap' AND observation_count IS NULL"),
        "unknown_days": client.scalar("SELECT count() FROM analytics_daily_coverage_v1 WHERE coverage_status = 'unknown' AND observation_count IS NULL"),
        "release_batches": client.scalar(f"SELECT count() FROM de_dataset_release_batches_v1 WHERE release_id = {rid}"),
    }
    expected = {
        "active_release": release.release_id, "contract_versions": "['1.1.0']",
        "observations": str(EXPECTED_TOTAL), "coverage": str(EXPECTED_COVERAGE),
        "coverage_unique": str(EXPECTED_COVERAGE), "provinces": str(EXPECTED_PROVINCES),
        "duplicates": "0", "known_gaps": "2", "unknown_days": "21",
        "release_batches": "3",
    }
    checks = {key: actual[key] == value for key, value in expected.items()}
    return {"status": "pass" if all(checks.values()) else "fail", "checks": checks, "actual": actual, "expected": expected}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build-manifest", "verify", "load-hidden", "activate", "audit", "rollback"))
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--release-id")
    parser.add_argument("--batch-dir", type=Path, action="append", default=[])
    parser.add_argument("--target-release", default="legacy-v1.0.0")
    parser.add_argument("--rollback-authorization-sha256")
    parser.add_argument("--url", default=os.getenv("CLICKHOUSE_URL", "http://127.0.0.1:8123"))
    parser.add_argument("--database", default=os.getenv("CLICKHOUSE_DATABASE", "wildfire"))
    parser.add_argument("--username", default=os.getenv("CLICKHOUSE_USER", "default"))
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--lock-dir", type=Path, default=Path(os.getenv("D06_LOCK_DIR", "/tmp/indonesia-wildfire-clickhouse-locks")))
    args = parser.parse_args()
    if args.command == "build-manifest":
        if not args.manifest or not args.release_id:
            raise SystemExit("build-manifest requires --manifest and --release-id")
        result = build_candidate_manifest(args.release_id, args.batch_dir, args.manifest)
    else:
        if args.command != "rollback" and (not args.manifest or not args.authorization):
            raise SystemExit("command requires --manifest and --authorization")
        release = verify_release(args.manifest, args.authorization) if args.command != "rollback" else None
        if args.command == "verify":
            result = {"status": "verified", "release_id": release.release_id, "database_contacted": False}
        else:
            password = os.getenv("CLICKHOUSE_PASSWORD")
            if password is None:
                raise SystemExit("CLICKHOUSE_PASSWORD must be set")
            client = HttpClickHouse(args.url, args.database, args.username, password, args.timeout)
            scope = f"{args.url}|{args.database}|d08-release"
            with single_writer_lock(args.lock_dir.resolve(), scope):
                if args.command == "load-hidden": result = load_hidden(release, client)
                elif args.command == "activate": result = activate(release, client)
                elif args.command == "audit": result = audit(release, client)
                else: result = rollback(client, args.target_release, args.rollback_authorization_sha256 or "")
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.command == "audit" and result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
