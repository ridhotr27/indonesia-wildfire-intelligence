#!/usr/bin/env python3
"""Profile the pinned NASA FIRMS CSV sample using only the Python standard library."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


EXPECTED_COLUMNS = [
    "latitude",
    "longitude",
    "bright_ti4",
    "scan",
    "track",
    "acq_date",
    "acq_time",
    "satellite",
    "instrument",
    "confidence",
    "version",
    "bright_ti5",
    "frp",
    "daynight",
]

FLOAT_COLUMNS = [
    "latitude",
    "longitude",
    "bright_ti4",
    "scan",
    "track",
    "bright_ti5",
    "frp",
]

CATEGORICAL_COLUMNS = [
    "satellite",
    "instrument",
    "confidence",
    "version",
    "daynight",
]

# Deliberately coarse screening extent, not an Indonesian boundary or a spatial join.
INDONESIA_SCREENING_BBOX = {
    "west": 95.0,
    "south": -11.0,
    "east": 141.0,
    "north": 6.0,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path, help="NASA FIRMS CSV to profile")
    parser.add_argument("--output", type=Path, help="Write JSON here; otherwise stdout")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def counter_dict(counter: Counter[str]) -> dict[str, int]:
    return dict(sorted(counter.items(), key=lambda item: item[0]))


def profile(path: Path) -> dict[str, Any]:
    blank_counts: Counter[str] = Counter()
    invalid_numeric_counts: Counter[str] = Counter()
    nonfinite_numeric_counts: Counter[str] = Counter()
    categorical_values = {column: Counter() for column in CATEGORICAL_COLUMNS}
    indonesia_categorical_values = {
        column: Counter() for column in CATEGORICAL_COLUMNS
    }
    numeric_min: dict[str, float] = {}
    numeric_max: dict[str, float] = {}
    complete_rows: Counter[tuple[str, ...]] = Counter()
    identity_rows: Counter[tuple[str, ...]] = Counter()
    invalid_dates = 0
    invalid_times = 0
    invalid_timestamps = 0
    invalid_coordinates = 0
    nonpositive_scan = 0
    nonpositive_track = 0
    negative_frp = 0
    zero_frp = 0
    zero_frp_by_version: Counter[str] = Counter()
    timestamps: list[datetime] = []
    indonesia_timestamps: list[datetime] = []
    indonesia_count = 0
    row_count = 0

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        if columns != EXPECTED_COLUMNS:
            raise ValueError(
                f"Unexpected columns: {columns!r}; expected {EXPECTED_COLUMNS!r}"
            )

        for row in reader:
            row_count += 1
            complete_rows[tuple(row[column] for column in EXPECTED_COLUMNS)] += 1
            identity_rows[
                (
                    row["latitude"],
                    row["longitude"],
                    row["acq_date"],
                    row["acq_time"],
                    row["satellite"],
                    row["instrument"],
                )
            ] += 1

            for column in EXPECTED_COLUMNS:
                if not row[column].strip():
                    blank_counts[column] += 1

            parsed_numeric: dict[str, float] = {}
            for column in FLOAT_COLUMNS:
                try:
                    value = float(row[column])
                except ValueError:
                    invalid_numeric_counts[column] += 1
                    continue
                if not math.isfinite(value):
                    nonfinite_numeric_counts[column] += 1
                    continue
                parsed_numeric[column] = value
                numeric_min[column] = min(numeric_min.get(column, value), value)
                numeric_max[column] = max(numeric_max.get(column, value), value)

            for column in CATEGORICAL_COLUMNS:
                categorical_values[column][row[column]] += 1

            try:
                parsed_date = datetime.strptime(row["acq_date"], "%Y-%m-%d").date()
            except ValueError:
                invalid_dates += 1
                parsed_date = None

            try:
                time_value = int(row["acq_time"])
                hours, minutes = divmod(time_value, 100)
                if not (0 <= time_value <= 2359 and 0 <= hours <= 23 and 0 <= minutes <= 59):
                    raise ValueError
            except ValueError:
                invalid_times += 1
                hours = minutes = None

            timestamp = None
            if parsed_date is not None and hours is not None and minutes is not None:
                timestamp = datetime(
                    parsed_date.year,
                    parsed_date.month,
                    parsed_date.day,
                    hours,
                    minutes,
                    tzinfo=UTC,
                )
                timestamps.append(timestamp)
            else:
                invalid_timestamps += 1

            latitude = parsed_numeric.get("latitude")
            longitude = parsed_numeric.get("longitude")
            if (
                latitude is None
                or longitude is None
                or not -90 <= latitude <= 90
                or not -180 <= longitude <= 180
            ):
                invalid_coordinates += 1
            elif (
                INDONESIA_SCREENING_BBOX["west"] <= longitude <= INDONESIA_SCREENING_BBOX["east"]
                and INDONESIA_SCREENING_BBOX["south"] <= latitude <= INDONESIA_SCREENING_BBOX["north"]
            ):
                indonesia_count += 1
                for column in CATEGORICAL_COLUMNS:
                    indonesia_categorical_values[column][row[column]] += 1
                if timestamp is not None:
                    indonesia_timestamps.append(timestamp)

            if "scan" in parsed_numeric and parsed_numeric["scan"] <= 0:
                nonpositive_scan += 1
            if "track" in parsed_numeric and parsed_numeric["track"] <= 0:
                nonpositive_track += 1
            if "frp" in parsed_numeric:
                if parsed_numeric["frp"] < 0:
                    negative_frp += 1
                elif parsed_numeric["frp"] == 0:
                    zero_frp += 1
                    zero_frp_by_version[row["version"]] += 1

    exact_duplicate_groups = sum(count > 1 for count in complete_rows.values())
    exact_duplicate_excess_rows = sum(count - 1 for count in complete_rows.values() if count > 1)
    identity_duplicate_groups = sum(count > 1 for count in identity_rows.values())
    identity_duplicate_excess_rows = sum(count - 1 for count in identity_rows.values() if count > 1)
    version_index = EXPECTED_COLUMNS.index("version")
    duplicate_excess_by_version: Counter[str] = Counter()
    for values, count in complete_rows.items():
        if count > 1:
            duplicate_excess_by_version[values[version_index]] += count - 1

    return {
        "file": {
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        },
        "shape": {"rows": row_count, "columns": len(EXPECTED_COLUMNS)},
        "columns": EXPECTED_COLUMNS,
        "semantic_types": {
            "latitude": "decimal degrees, float",
            "longitude": "decimal degrees, float",
            "bright_ti4": "kelvin, float",
            "scan": "kilometres, float",
            "track": "kilometres, float",
            "acq_date": "UTC date, YYYY-MM-DD",
            "acq_time": "UTC time, integer encoded HHMM; zero-pad to four digits",
            "satellite": "categorical string",
            "instrument": "categorical string",
            "confidence": "categorical string",
            "version": "categorical string",
            "bright_ti5": "kelvin, float",
            "frp": "megawatts, float",
            "daynight": "categorical string",
        },
        "coverage": {
            "timestamp_utc_min": min(timestamps).isoformat() if timestamps else None,
            "timestamp_utc_max": max(timestamps).isoformat() if timestamps else None,
            "latitude_min": numeric_min.get("latitude"),
            "latitude_max": numeric_max.get("latitude"),
            "longitude_min": numeric_min.get("longitude"),
            "longitude_max": numeric_max.get("longitude"),
            "indonesia_screening_bbox": {
                **INDONESIA_SCREENING_BBOX,
                "rows": indonesia_count,
                "timestamp_utc_min": (
                    min(indonesia_timestamps).isoformat() if indonesia_timestamps else None
                ),
                "timestamp_utc_max": (
                    max(indonesia_timestamps).isoformat() if indonesia_timestamps else None
                ),
                "warning": "Coarse rectangular screen only; includes non-Indonesian areas and is not a boundary join.",
                "categorical_counts": {
                    column: counter_dict(values)
                    for column, values in indonesia_categorical_values.items()
                },
            },
        },
        "categorical_counts": {
            column: counter_dict(values)
            for column, values in categorical_values.items()
        },
        "numeric_ranges": {
            column: {"min": numeric_min.get(column), "max": numeric_max.get(column)}
            for column in FLOAT_COLUMNS
        },
        "quality": {
            "blank_counts": {
                column: blank_counts[column] for column in EXPECTED_COLUMNS
            },
            "invalid_numeric_counts": {
                column: invalid_numeric_counts[column] for column in FLOAT_COLUMNS
            },
            "nonfinite_numeric_counts": {
                column: nonfinite_numeric_counts[column] for column in FLOAT_COLUMNS
            },
            "invalid_date_count": invalid_dates,
            "invalid_time_count": invalid_times,
            "invalid_timestamp_count": invalid_timestamps,
            "invalid_coordinate_count": invalid_coordinates,
            "nonpositive_scan_count": nonpositive_scan,
            "nonpositive_track_count": nonpositive_track,
            "negative_frp_count": negative_frp,
            "zero_frp_count": zero_frp,
            "zero_frp_by_version": counter_dict(zero_frp_by_version),
            "exact_duplicate_groups": exact_duplicate_groups,
            "exact_duplicate_excess_rows": exact_duplicate_excess_rows,
            "exact_duplicate_excess_rows_by_version": counter_dict(
                duplicate_excess_by_version
            ),
            "identity_duplicate_groups": identity_duplicate_groups,
            "identity_duplicate_excess_rows": identity_duplicate_excess_rows,
            "identity_key": [
                "latitude",
                "longitude",
                "acq_date",
                "acq_time",
                "satellite",
                "instrument",
            ],
        },
    }


def main() -> None:
    args = parse_args()
    result = profile(args.input)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
