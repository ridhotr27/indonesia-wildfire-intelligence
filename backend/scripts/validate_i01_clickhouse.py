#!/usr/bin/env python3
"""Validate I01 live parity without printing or persisting database credentials."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

import httpx
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wildfire_api.contracts.data_v1 import PRODUCT_ID  # noqa: E402
from wildfire_api.core.config import Settings  # noqa: E402
from wildfire_api.main import create_app  # noqa: E402

EXPECTED = {
    "observations": 253_388,
    "coverage_days": 365,
    "provinces": 38,
    "known_gap_null_days": 2,
    "unassigned": 796,
    "multiple_match": 10,
    "riau_september_2023": 687,
}


def clickhouse_query(
    *, url: str, database: str, username: str, password: str, sql: str
) -> httpx.Response:
    return httpx.post(
        url,
        params={"database": database, "readonly": 2},
        content=sql,
        auth=(username, password),
        timeout=10,
        headers={"Content-Type": "text/plain; charset=utf-8"},
    )


def scalar(
    *, url: str, database: str, username: str, password: str, sql: str
) -> int:
    response = clickhouse_query(
        url=url,
        database=database,
        username=username,
        password=password,
        sql=f"{sql} FORMAT TabSeparatedRaw",
    )
    response.raise_for_status()
    return int(response.text.strip())


def validate(args: argparse.Namespace) -> dict[str, Any]:
    settings = Settings(
        environment="test",
        analytics_backend="clickhouse",
        clickhouse_url=args.url,
        clickhouse_database=args.database,
        clickhouse_username=args.username,
        clickhouse_password=args.password,
        clickhouse_timeout_seconds=10,
        per_client_requests_per_minute=100,
        global_requests_per_minute=100,
    )
    started = perf_counter()
    with TestClient(create_app(settings=settings)) as client:
        metadata_response = client.get("/api/v1/metadata")
        metadata_response.raise_for_status()
        metadata = metadata_response.json()
        summary_response = client.post(
            "/api/v1/hotspots/summary",
            json={
                "product_id": PRODUCT_ID,
                "province_codes": ["14"],
                "date_from": "2023-09-01",
                "date_to": "2023-09-30",
                "group_by": "month",
            },
        )
        summary_response.raise_for_status()
        summary = summary_response.json()
        gap_response = client.post(
            "/api/v1/hotspots/summary",
            json={
                "product_id": PRODUCT_ID,
                "province_codes": ["14"],
                "date_from": "2023-07-26",
                "date_to": "2023-07-27",
                "group_by": "month",
            },
        )
        gap_response.raise_for_status()
        gap = gap_response.json()
        map_response = client.get(
            "/api/v1/hotspots/geojson",
            params={
                "product_id": PRODUCT_ID,
                "province_code": "14",
                "date_from": "2023-09-01",
                "date_to": "2023-09-30",
                "limit": 2,
            },
        )
        map_response.raise_for_status()
        geojson = map_response.json()

    observed = {
        "observations": scalar(
            url=args.url,
            database=args.database,
            username=args.username,
            password=args.password,
            sql="SELECT count() FROM analytics_hotspot_observations_v1",
        ),
        "coverage_days": scalar(
            url=args.url,
            database=args.database,
            username=args.username,
            password=args.password,
            sql="SELECT uniqExact(date_utc) FROM analytics_daily_coverage_v1",
        ),
        "provinces": scalar(
            url=args.url,
            database=args.database,
            username=args.username,
            password=args.password,
            sql="SELECT count() FROM analytics_provinces_v1",
        ),
        "known_gap_null_days": scalar(
            url=args.url,
            database=args.database,
            username=args.username,
            password=args.password,
            sql=(
                "SELECT count() FROM analytics_daily_coverage_v1 "
                "WHERE coverage_status='known_satellite_gap' AND observation_count IS NULL"
            ),
        ),
        "unassigned": scalar(
            url=args.url,
            database=args.database,
            username=args.username,
            password=args.password,
            sql=(
                "SELECT count() FROM analytics_hotspot_observations_v1 "
                "WHERE geo_assignment_status='unassigned' AND province_code IS NULL"
            ),
        ),
        "multiple_match": scalar(
            url=args.url,
            database=args.database,
            username=args.username,
            password=args.password,
            sql=(
                "SELECT count() FROM analytics_hotspot_observations_v1 "
                "WHERE geo_assignment_status='multiple_match' AND province_code IS NULL"
            ),
        ),
        "riau_september_2023": summary["total"],
    }
    if observed != EXPECTED:
        raise RuntimeError(f"DE/BE parity mismatch: expected={EXPECTED!r}, observed={observed!r}")
    if metadata["data_status"] != "verified" or metadata["products"] != [
        {"product_id": PRODUCT_ID, "display_name": "VIIRS S-NPP VNP14IMG.002 (FIRMS SP)"}
    ]:
        raise RuntimeError("real-mode metadata identity is invalid")
    if len(metadata["provinces"]) != EXPECTED["provinces"]:
        raise RuntimeError("province metadata count is invalid")
    if summary["source"]["data_status"] != "verified" or summary["total"] != 687:
        raise RuntimeError("Riau reference response is invalid")
    if gap["total"] is not None or gap["is_complete"] is not False:
        raise RuntimeError("known-gap response must remain unavailable, not zero")
    if [issue["date_utc"] for issue in gap["coverage_issues"]] != [
        "2023-07-26",
        "2023-07-27",
    ]:
        raise RuntimeError("known-gap dates did not survive end to end")
    if len(geojson["features"]) != 2 or not geojson["metadata"]["truncated"]:
        raise RuntimeError("bounded real-data map behavior is invalid")
    if any(feature["properties"]["product_id"] != PRODUCT_ID for feature in geojson["features"]):
        raise RuntimeError("synthetic or mismatched map data reached real mode")

    permission_checks = {}
    for name, sql in {
        "raw_select": "SELECT count() FROM de_hotspot_observations_v1",
        "raw_insert": (
            "INSERT INTO de_hotspot_observations_v1 "
            "SELECT * FROM de_hotspot_observations_v1 LIMIT 0"
        ),
        "ddl": "CREATE TABLE i01_forbidden (value UInt8) ENGINE=Memory",
    }.items():
        response = clickhouse_query(
            url=args.url,
            database=args.database,
            username=args.username,
            password=args.password,
            sql=sql,
        )
        if response.status_code < 400 or "ACCESS_DENIED" not in response.text:
            raise RuntimeError(f"backend permission check unexpectedly succeeded: {name}")
        permission_checks[name] = "ACCESS_DENIED"

    return {
        "ticket": "I01",
        "executed_at_utc": datetime.now(UTC).isoformat(),
        "database_version": metadata["source"]["dataset_version"],
        "api_data_status": metadata["data_status"],
        "parity": observed,
        "known_gap_total": gap["total"],
        "known_gap_dates": [issue["date_utc"] for issue in gap["coverage_issues"]],
        "map_rows_returned": len(geojson["features"]),
        "map_truncated": geojson["metadata"]["truncated"],
        "permissions": permission_checks,
        "elapsed_seconds": round(perf_counter() - started, 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--database", default="wildfire")
    parser.add_argument("--username", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    args.password = os.getenv("I01_CLICKHOUSE_PASSWORD")
    if not args.password:
        parser.error("I01_CLICKHOUSE_PASSWORD is required")
    result = validate(args)
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
