#!/usr/bin/env python3
"""Profile one FIRMS annual candidate without producing ingestion artifacts."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from data.scripts.ingest_firms_v1 import (
        EXPECTED_HEADER,
        PRODUCT_ID,
        parse_row,
        sha256_file,
        year_bounds,
    )
    from data.scripts.validate_d03_requirements import prepare_boundary_scanlines
    from data.scripts.validate_historical_sample import ProfileAccumulator, load_boundaries
except ModuleNotFoundError:  # Direct execution
    from ingest_firms_v1 import (  # type: ignore[no-redef]
        EXPECTED_HEADER,
        PRODUCT_ID,
        parse_row,
        sha256_file,
        year_bounds,
    )
    from validate_d03_requirements import prepare_boundary_scanlines
    from validate_historical_sample import ProfileAccumulator, load_boundaries


def profile_candidate(
    *, source_csv: Path, boundaries_geojson: Path, source_year: int,
    source_url: str, provider_last_modified_utc: str | None, provider_etag: str | None,
) -> dict[str, Any]:
    start, end = year_bounds(source_year)
    boundaries = load_boundaries(boundaries_geojson)
    prepared = [
        (boundary, prepare_boundary_scanlines(boundary)) for boundary in boundaries
    ]
    accumulator = ProfileAccumulator(EXPECTED_HEADER)
    geography: Counter[str] = Counter()
    province_counts: Counter[str] = Counter()
    validation_failures: Counter[str] = Counter()

    with source_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError("source CSV is empty") from exc
        if header != EXPECTED_HEADER:
            raise ValueError("source CSV does not match the approved 15-column schema")
        for row_number, values in enumerate(reader, start=1):
            if len(values) != len(EXPECTED_HEADER):
                validation_failures["column_count"] += 1
                continue
            raw = dict(zip(EXPECTED_HEADER, values, strict=True))
            accumulator.add(raw)
            try:
                observation = parse_row(
                    raw, values, row_number, "d08-profile-only", prepared, source_year
                )
            except ValueError as exc:
                validation_failures[str(exc)] += 1
                continue
            status = observation["geo_assignment_status"]
            geography[status] += 1
            if observation["province_code"] is not None:
                province_counts[observation["province_code"]] += 1

    source_profile = accumulator.result()
    return {
        "ticket": "D08",
        "classification": "read_only_full_file_profile_not_authorized_for_ingestion",
        "observed_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace(
            "+00:00", "Z"
        ),
        "source": {
            "provider": "NASA LANCE FIRMS",
            "url": source_url,
            "path": str(source_csv),
            "bytes": source_csv.stat().st_size,
            "sha256": sha256_file(source_csv),
            "provider_last_modified_utc": provider_last_modified_utc,
            "provider_etag": provider_etag,
            "product_id": PRODUCT_ID,
            "source_product": "VNP14IMG",
            "collection_version": "2",
            "processing_stream": "standard",
        },
        "requested_window": {
            "year": source_year,
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
        },
        "source_profile": source_profile,
        "province_mapping": {
            "boundary_path": str(boundaries_geojson),
            "boundary_sha256": sha256_file(boundaries_geojson),
            "boundary_features": len(boundaries),
            "status_counts": dict(sorted(geography.items())),
            "province_counts": dict(sorted(province_counts.items())),
        },
        "strict_validation": {
            "failure_count": sum(validation_failures.values()),
            "failure_reasons": dict(sorted(validation_failures.items())),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--boundaries", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--provider-last-modified-utc")
    parser.add_argument("--provider-etag")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = profile_candidate(
        source_csv=args.source,
        boundaries_geojson=args.boundaries,
        source_year=args.year,
        source_url=args.source_url,
        provider_last_modified_utc=args.provider_last_modified_utc,
        provider_etag=args.provider_etag,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "output": str(args.output),
        "rows": result["source_profile"]["shape"]["rows"],
        "sha256": result["source"]["sha256"],
        "validation_failures": result["strict_validation"]["failure_count"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
