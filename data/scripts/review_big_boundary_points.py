#!/usr/bin/env python3
"""Review D02 near-boundary points against BIG's full-resolution service.

The script asks the official ArcGIS service to evaluate each point against its
source geometry. It requests attributes only (``returnGeometry=false``), so it
does not download or redistribute BIG boundary geometry.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BIG_QUERY_URL = (
    "https://geoservices.big.go.id/gis/rest/services/"
    "STIG/Batas_Provinsi/MapServer/0/query"
)


class BoundaryReviewError(RuntimeError):
    """Raised when a BIG response cannot be safely interpreted."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_point_query_url(longitude: str, latitude: str) -> str:
    params = {
        "geometry": f"{float(longitude):.8f},{float(latitude):.8f}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "KDPPUM,WADMPR",
        "returnGeometry": "false",
        "returnZ": "false",
        "returnM": "false",
        "f": "json",
    }
    return f"{BIG_QUERY_URL}?{urlencode(params)}"


def query_point_membership(
    longitude: str,
    latitude: str,
    *,
    opener: Callable[..., Any] = urlopen,
    timeout: float = 60.0,
) -> list[dict[str, str]]:
    request = Request(
        build_point_query_url(longitude, latitude),
        headers={"User-Agent": "indonesia-wildfire-feasibility/1.0"},
    )
    try:
        with opener(request, timeout=timeout) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise BoundaryReviewError(
            f"BIG point query failed without usable metadata: {type(exc).__name__}"
        ) from exc
    if "error" in payload:
        raise BoundaryReviewError("BIG point query returned an ArcGIS error")
    features = payload.get("features")
    if not isinstance(features, list):
        raise BoundaryReviewError("BIG point query omitted a feature list")
    matches: list[dict[str, str]] = []
    for feature in features:
        attributes = feature.get("attributes", {})
        code = str(attributes.get("KDPPUM", "")).strip()
        name = str(attributes.get("WADMPR", "")).strip()
        if not code or not name:
            raise BoundaryReviewError("BIG point query returned blank province metadata")
        matches.append({"province_code": code, "province_name": name})
    return sorted(matches, key=lambda item: item["province_code"])


def classify_review(generalized_code: str, matches: list[dict[str, str]]) -> str:
    if len(matches) > 1:
        return "full_resolution_multiple"
    if not matches:
        return (
            "unchanged_unassigned"
            if not generalized_code
            else "full_resolution_unassigned"
        )
    if not generalized_code:
        return "full_resolution_new_assignment"
    if matches[0]["province_code"] == generalized_code:
        return "assignment_confirmed"
    return "assignment_changed"


def review(
    *,
    enriched_csv: Path,
    output: Path,
    opener: Callable[..., Any] = urlopen,
    delay_seconds: float = 0.1,
    max_workers: int = 1,
) -> dict[str, Any]:
    with enriched_csv.open("r", encoding="utf-8", newline="") as handle:
        rows = [
            row
            for row in csv.DictReader(handle)
            if row.get("boundary_near_0_001deg") == "true"
        ]
    if len(rows) != 45:
        raise ValueError(f"expected 45 D02 near-boundary rows, found {len(rows)}")

    outcomes: Counter[str] = Counter()
    records: list[dict[str, Any]] = []
    if max_workers < 1 or max_workers > 8:
        raise ValueError("max_workers must be between 1 and 8")

    def point_matches(row: dict[str, str]) -> list[dict[str, str]]:
        return query_point_membership(
            row["longitude"], row["latitude"], opener=opener, timeout=30.0
        )

    if max_workers == 1:
        matches_by_row = []
        for index, row in enumerate(rows):
            matches_by_row.append(point_matches(row))
            if delay_seconds and index + 1 < len(rows):
                time.sleep(delay_seconds)
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            matches_by_row = list(executor.map(point_matches, rows))

    for index, (row, matches) in enumerate(zip(rows, matches_by_row), start=1):
        outcome = classify_review(row["province_code"], matches)
        outcomes[outcome] += 1
        records.append(
            {
                "review_index": index,
                "acquired_at_utc": (
                    f"{row['acq_date']}T{row['acq_time'][:2]}:"
                    f"{row['acq_time'][2:]}:00Z"
                ),
                "latitude": float(row["latitude"]),
                "longitude": float(row["longitude"]),
                "source_type": int(row["type"]),
                "generalized_assignment": {
                    "status": row["join_status"],
                    "province_code": row["province_code"] or None,
                    "province_name": row["province_name"] or None,
                },
                "full_resolution_matches": matches,
                "review_outcome": outcome,
            }
        )
    result = {
        "reviewed_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "method": (
            "Server-side point intersection against the official BIG source geometry; "
            "attributes only, returnGeometry=false"
        ),
        "service_url": BIG_QUERY_URL.rsplit("/query", 1)[0],
        "source": {
            "path": str(enriched_csv),
            "sha256": sha256(enriched_csv),
            "near_boundary_rows": len(rows),
        },
        "outcome_counts": dict(sorted(outcomes.items())),
        "preservation_policy": (
            "This review does not rewrite the D02 enriched artifact. All 34 original "
            "unassigned observations remain preserved, and no ambiguous point is "
            "silently forced into a province."
        ),
        "redistribution_note": (
            "No boundary geometry was downloaded. Public service access is not treated "
            "as evidence of a redistribution license."
        ),
        "records": records,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--enriched", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--delay-seconds", type=float, default=0.1)
    parser.add_argument("--max-workers", type=int, default=1)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = review(
        enriched_csv=args.enriched,
        output=args.output,
        delay_seconds=max(0.0, args.delay_seconds),
        max_workers=args.max_workers,
    )
    print(json.dumps({"outcomes": result["outcome_counts"]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
