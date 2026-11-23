#!/usr/bin/env python3
"""Preflight, audit, and safely recover the immutable v1 ClickHouse pipeline."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

try:
    from data.scripts.load_clickhouse_v1 import (
        HttpClickHouse,
        LoadError,
        VerifiedBatch,
        single_writer_lock,
        verify_batch,
    )
except ModuleNotFoundError:  # Direct execution
    from load_clickhouse_v1 import (
        HttpClickHouse, LoadError, VerifiedBatch, single_writer_lock, verify_batch,
    )


EXPECTED_COVERAGE_DAYS = 365
EXPECTED_PROVINCES = 38
EXPECTED_GAP_DAYS = 2


class ScalarClient(Protocol):
    def scalar(self, sql: str) -> str: ...


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def preflight(batch_dir: Path) -> dict[str, Any]:
    """Verify a batch without contacting or changing ClickHouse."""
    batch = verify_batch(batch_dir.resolve())
    counts = batch.manifest["counts"]
    checks = {
        "checksums_and_identity": True,
        "coverage_days": counts["coverage_days"] == EXPECTED_COVERAGE_DAYS,
        "province_count": counts["provinces"] == EXPECTED_PROVINCES,
        "no_rejected_rows": counts["rejected_rows"] == 0,
        "row_accounting": (
            counts["canonical_rows"] + counts["duplicate_excess_rows"]
            == counts["source_rows"]
        ),
    }
    return {
        "mode": "offline_preflight",
        "safe_to_load": all(checks.values()),
        "ingestion_batch_id": batch.batch_id,
        "contract_version": batch.manifest["contract_version"],
        "transform_version": batch.manifest["transform_version"],
        "source_artifact_sha256": batch.manifest["source_artifact_sha256"],
        "counts": counts,
        "checks": checks,
        "database_contacted": False,
        "database_changed": False,
    }


def audit_publication(batch: VerifiedBatch, client: ScalarClient) -> dict[str, Any]:
    """Run bounded, deterministic publication/freshness checks."""
    batch_id = _sql_literal(batch.batch_id)
    expected_rows = int(batch.batch_row["canonical_row_count"])
    raw = {
        "published_batches": client.scalar(
            "SELECT count() FROM analytics_ingestion_batches_v1"
        ),
        "published_batch_rows": client.scalar(
            "SELECT count() FROM analytics_ingestion_batches_v1 "
            f"WHERE ingestion_batch_id = {batch_id}"
        ),
        "published_observations": client.scalar(
            "SELECT count() FROM analytics_hotspot_observations_v1 "
            f"WHERE ingestion_batch_id = {batch_id}"
        ),
        "coverage_days": client.scalar("SELECT count() FROM analytics_daily_coverage_v1"),
        "known_gap_days": client.scalar(
            "SELECT count() FROM analytics_daily_coverage_v1 "
            "WHERE coverage_status = 'known_satellite_gap' "
            "AND observation_count IS NULL AND evidence_url IS NOT NULL"
        ),
        "gap_observations": client.scalar(
            "SELECT count() FROM analytics_hotspot_observations_v1 "
            "WHERE toDate(acquired_at_utc) IN ('2023-07-26', '2023-07-27')"
        ),
        "provinces": client.scalar("SELECT count() FROM analytics_provinces_v1"),
        "invalid_null_geography": client.scalar(
            "SELECT count() FROM analytics_hotspot_observations_v1 "
            "WHERE geo_assignment_status != 'assigned' AND "
            "(province_code IS NOT NULL OR province_name IS NOT NULL "
            "OR boundary_source_id IS NOT NULL)"
        ),
        "unpublished_rows": client.scalar(
            "SELECT sum(rows) FROM ("
            "SELECT count() rows FROM de_hotspot_observations_v1 o WHERE NOT EXISTS "
            "(SELECT 1 FROM de_ingestion_batches_v1 b WHERE "
            "b.ingestion_batch_id = o.ingestion_batch_id) UNION ALL "
            "SELECT count() rows FROM de_daily_coverage_v1 c WHERE NOT EXISTS "
            "(SELECT 1 FROM de_ingestion_batches_v1 b WHERE "
            "b.ingestion_batch_id = c.load_batch_id) UNION ALL "
            "SELECT count() rows FROM de_provinces_v1 p WHERE NOT EXISTS "
            "(SELECT 1 FROM de_ingestion_batches_v1 b WHERE "
            "b.ingestion_batch_id = p.load_batch_id))"
        ),
        "published_at_utc": client.scalar(
            "SELECT formatDateTime(published_at_utc, '%FT%TZ', 'UTC') "
            "FROM analytics_ingestion_batches_v1 "
            f"WHERE ingestion_batch_id = {batch_id}"
        ),
    }
    expected = {
        "published_batches": 1,
        "published_batch_rows": 1,
        "published_observations": expected_rows,
        "coverage_days": EXPECTED_COVERAGE_DAYS,
        "known_gap_days": EXPECTED_GAP_DAYS,
        "gap_observations": 0,
        "provinces": EXPECTED_PROVINCES,
        "invalid_null_geography": 0,
        "unpublished_rows": 0,
    }
    checks = {name: raw[name] == str(value) for name, value in expected.items()}
    published_at = raw["published_at_utc"] or None
    return {
        "mode": "database_audit",
        "status": "pass" if all(checks.values()) and published_at else "fail",
        "ingestion_batch_id": batch.batch_id,
        "checked_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace(
            "+00:00", "Z"
        ),
        "freshness": {
            "published_at_utc": published_at,
            "source_retrieved_at_utc": batch.batch_row["retrieved_at_utc"],
            "provider_last_modified_utc": batch.batch_row["provider_last_modified_utc"],
            "coverage_end_utc": batch.batch_row["coverage_end_utc"],
            "semantics": "immutable_historical_snapshot; age is informational, not live-data lag",
        },
        "expected": expected,
        "actual": raw,
        "checks": checks,
        "database_changed": False,
    }


def orphan_counts(batch: VerifiedBatch, client: ScalarClient) -> dict[str, int]:
    batch_id = _sql_literal(batch.batch_id)
    published = int(client.scalar(
        "SELECT count() FROM analytics_ingestion_batches_v1 "
        f"WHERE ingestion_batch_id = {batch_id}"
    ))
    if published:
        raise LoadError("refusing recovery: batch is already published")
    return {
        "observations": int(client.scalar(
            "SELECT count() FROM de_hotspot_observations_v1 "
            f"WHERE ingestion_batch_id = {batch_id}"
        )),
        "coverage": int(client.scalar(
            "SELECT count() FROM de_daily_coverage_v1 "
            f"WHERE load_batch_id = {batch_id}"
        )),
        "provinces": int(client.scalar(
            "SELECT count() FROM de_provinces_v1 "
            f"WHERE load_batch_id = {batch_id}"
        )),
    }


def recovery_plan(batch: VerifiedBatch, client: ScalarClient) -> dict[str, Any]:
    counts = orphan_counts(batch, client)
    return {
        "mode": "recovery_plan",
        "ingestion_batch_id": batch.batch_id,
        "orphan_rows": counts,
        "action_required": any(counts.values()),
        "database_changed": False,
        "next_step": (
            "review counts, then rerun recover-orphans with the exact --confirm-batch value"
            if any(counts.values()) else "no cleanup needed; retry the normal loader"
        ),
    }


def recover_orphans(
    batch: VerifiedBatch, client: ScalarClient, *, confirm_batch: str
) -> dict[str, Any]:
    """Delete only unpublished rows owned by an exactly confirmed batch."""
    if confirm_batch != batch.batch_id:
        raise LoadError("--confirm-batch must exactly match the verified batch ID")
    before = orphan_counts(batch, client)
    batch_id = _sql_literal(batch.batch_id)
    if any(before.values()):
        client.scalar(
            "ALTER TABLE de_hotspot_observations_v1 DELETE WHERE "
            f"ingestion_batch_id = {batch_id} SETTINGS mutations_sync = 2"
        )
        client.scalar(
            "ALTER TABLE de_daily_coverage_v1 DELETE WHERE "
            f"load_batch_id = {batch_id} SETTINGS mutations_sync = 2"
        )
        client.scalar(
            "ALTER TABLE de_provinces_v1 DELETE WHERE "
            f"load_batch_id = {batch_id} SETTINGS mutations_sync = 2"
        )
    after = orphan_counts(batch, client)
    if any(after.values()):
        raise LoadError("orphan cleanup did not reconcile to zero")
    return {
        "mode": "recover_orphans",
        "ingestion_batch_id": batch.batch_id,
        "removed_rows": before,
        "remaining_rows": after,
        "database_changed": any(before.values()),
        "next_step": "rerun the normal checksum-verifying loader",
    }


def recover_orphans_locked(
    batch: VerifiedBatch,
    client: ScalarClient,
    *,
    confirm_batch: str,
    lock_dir: Path,
    lock_scope: str,
) -> dict[str, Any]:
    """Serialize recovery with the normal same-host loader for the complete operation."""
    with single_writer_lock(lock_dir.resolve(), lock_scope):
        return recover_orphans(batch, client, confirm_batch=confirm_batch)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("preflight", "audit", "recovery-plan", "recover-orphans")
    )
    parser.add_argument("--batch-dir", type=Path, required=True)
    parser.add_argument("--url", default=os.getenv("CLICKHOUSE_URL", "http://127.0.0.1:8123"))
    parser.add_argument("--database", default=os.getenv("CLICKHOUSE_DATABASE", "wildfire"))
    parser.add_argument("--username", default=os.getenv("CLICKHOUSE_USER", "default"))
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--confirm-batch")
    parser.add_argument(
        "--lock-dir",
        type=Path,
        default=Path(os.getenv("D06_LOCK_DIR", "/tmp/indonesia-wildfire-clickhouse-locks")),
    )
    args = parser.parse_args()
    batch = verify_batch(args.batch_dir.resolve())
    if args.command == "preflight":
        result = preflight(args.batch_dir)
    else:
        password = os.getenv("CLICKHOUSE_PASSWORD")
        if password is None:
            raise SystemExit("CLICKHOUSE_PASSWORD must be set")
        client = HttpClickHouse(args.url, args.database, args.username, password, args.timeout)
        if args.command == "audit":
            result = audit_publication(batch, client)
        elif args.command == "recovery-plan":
            result = recovery_plan(batch, client)
        else:
            scope = f"{args.url}|{args.database}|{batch.batch_id}"
            result = recover_orphans_locked(
                batch,
                client,
                confirm_batch=args.confirm_batch or "",
                lock_dir=args.lock_dir,
                lock_scope=scope,
            )
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.command == "audit" and result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
