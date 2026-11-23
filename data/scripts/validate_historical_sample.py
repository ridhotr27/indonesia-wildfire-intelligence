#!/usr/bin/env python3
"""Profile a historical FIRMS extract and validate an Indonesia ADM1 join."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable


ARCHIVE_COLUMNS = [
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
    "type",
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
    "type",
]

IDENTITY_COLUMNS = [
    "latitude",
    "longitude",
    "acq_date",
    "acq_time",
    "satellite",
    "instrument",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iso_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def inclusive_dates(start: date, end: date) -> list[date]:
    if end < start:
        raise ValueError("date_to must be on or after date_from")
    values: list[date] = []
    current = start
    while current <= end:
        values.append(current)
        current += timedelta(days=1)
    return values


class ProfileAccumulator:
    def __init__(self, columns: list[str]) -> None:
        self.columns = columns
        self.rows = 0
        self.blanks: Counter[str] = Counter()
        self.invalid_numeric: Counter[str] = Counter()
        self.nonfinite_numeric: Counter[str] = Counter()
        self.categories = {column: Counter() for column in CATEGORICAL_COLUMNS}
        self.numeric_min: dict[str, float] = {}
        self.numeric_max: dict[str, float] = {}
        self.day_counts: Counter[str] = Counter()
        self.month_counts: Counter[str] = Counter()
        self.full_rows: Counter[tuple[str, ...]] = Counter()
        self.identity_rows: Counter[tuple[str, ...]] = Counter()
        self.invalid_dates = 0
        self.invalid_times = 0
        self.invalid_timestamps = 0
        self.invalid_coordinates = 0
        self.negative_frp = 0
        self.zero_frp = 0
        self.timestamp_min: datetime | None = None
        self.timestamp_max: datetime | None = None

    def add(self, row: dict[str, str]) -> None:
        self.rows += 1
        self.full_rows[tuple(row[column] for column in self.columns)] += 1
        self.identity_rows[tuple(row[column] for column in IDENTITY_COLUMNS)] += 1
        for column in self.columns:
            if not row[column].strip():
                self.blanks[column] += 1

        parsed_numeric: dict[str, float] = {}
        for column in FLOAT_COLUMNS:
            try:
                value = float(row[column])
            except ValueError:
                self.invalid_numeric[column] += 1
                continue
            if not math.isfinite(value):
                self.nonfinite_numeric[column] += 1
                continue
            parsed_numeric[column] = value
            self.numeric_min[column] = min(self.numeric_min.get(column, value), value)
            self.numeric_max[column] = max(self.numeric_max.get(column, value), value)

        for column in CATEGORICAL_COLUMNS:
            self.categories[column][row[column]] += 1

        parsed_date: date | None
        try:
            parsed_date = iso_date(row["acq_date"])
            self.day_counts[parsed_date.isoformat()] += 1
            self.month_counts[parsed_date.strftime("%Y-%m")] += 1
        except ValueError:
            parsed_date = None
            self.invalid_dates += 1

        try:
            raw_time = int(row["acq_time"])
            hours, minutes = divmod(raw_time, 100)
            if not (0 <= raw_time <= 2359 and 0 <= hours <= 23 and 0 <= minutes <= 59):
                raise ValueError
        except ValueError:
            hours = minutes = None
            self.invalid_times += 1

        if parsed_date is not None and hours is not None and minutes is not None:
            timestamp = datetime(
                parsed_date.year,
                parsed_date.month,
                parsed_date.day,
                hours,
                minutes,
                tzinfo=UTC,
            )
            self.timestamp_min = min(self.timestamp_min or timestamp, timestamp)
            self.timestamp_max = max(self.timestamp_max or timestamp, timestamp)
        else:
            self.invalid_timestamps += 1

        latitude = parsed_numeric.get("latitude")
        longitude = parsed_numeric.get("longitude")
        if (
            latitude is None
            or longitude is None
            or not -90 <= latitude <= 90
            or not -180 <= longitude <= 180
        ):
            self.invalid_coordinates += 1

        frp = parsed_numeric.get("frp")
        if frp is not None:
            if frp < 0:
                self.negative_frp += 1
            elif frp == 0:
                self.zero_frp += 1

    def result(self) -> dict[str, Any]:
        duplicate_groups = sum(count > 1 for count in self.full_rows.values())
        duplicate_excess = sum(
            count - 1 for count in self.full_rows.values() if count > 1
        )
        identity_groups = sum(count > 1 for count in self.identity_rows.values())
        identity_excess = sum(
            count - 1 for count in self.identity_rows.values() if count > 1
        )
        present_dates = sorted(self.day_counts)
        missing_dates: list[str] = []
        if present_dates:
            for value in inclusive_dates(iso_date(present_dates[0]), iso_date(present_dates[-1])):
                if value.isoformat() not in self.day_counts:
                    missing_dates.append(value.isoformat())
        return {
            "shape": {"rows": self.rows, "columns": len(self.columns)},
            "columns": self.columns,
            "coverage": {
                "date_min": present_dates[0] if present_dates else None,
                "date_max": present_dates[-1] if present_dates else None,
                "dates_present": len(present_dates),
                "missing_dates_between_min_and_max": missing_dates,
                "timestamp_utc_min": (
                    self.timestamp_min.isoformat() if self.timestamp_min else None
                ),
                "timestamp_utc_max": (
                    self.timestamp_max.isoformat() if self.timestamp_max else None
                ),
                "daily_counts": dict(sorted(self.day_counts.items())),
                "monthly_counts": dict(sorted(self.month_counts.items())),
            },
            "categorical_counts": {
                column: dict(sorted(values.items()))
                for column, values in self.categories.items()
            },
            "numeric_ranges": {
                column: {
                    "min": self.numeric_min.get(column),
                    "max": self.numeric_max.get(column),
                }
                for column in FLOAT_COLUMNS
            },
            "quality": {
                "blank_counts": {
                    column: self.blanks[column] for column in self.columns
                },
                "invalid_numeric_counts": {
                    column: self.invalid_numeric[column] for column in FLOAT_COLUMNS
                },
                "nonfinite_numeric_counts": {
                    column: self.nonfinite_numeric[column] for column in FLOAT_COLUMNS
                },
                "invalid_date_count": self.invalid_dates,
                "invalid_time_count": self.invalid_times,
                "invalid_timestamp_count": self.invalid_timestamps,
                "invalid_coordinate_count": self.invalid_coordinates,
                "negative_frp_count": self.negative_frp,
                "zero_frp_count": self.zero_frp,
                "exact_duplicate_groups": duplicate_groups,
                "exact_duplicate_excess_rows": duplicate_excess,
                "identity_duplicate_groups": identity_groups,
                "identity_duplicate_excess_rows": identity_excess,
                "identity_key": IDENTITY_COLUMNS,
            },
        }


Coordinates = list[Any]
Polygon = list[list[list[float]]]


@dataclass(frozen=True)
class Boundary:
    code: str
    name: str
    polygons: list[Polygon]
    bbox: tuple[float, float, float, float]


def geometry_polygons(geometry: dict[str, Any]) -> list[Polygon]:
    geometry_type = geometry.get("type")
    coordinates: Coordinates = geometry.get("coordinates", [])
    if geometry_type == "Polygon":
        return [coordinates]
    if geometry_type == "MultiPolygon":
        return coordinates
    raise ValueError(f"unsupported boundary geometry type: {geometry_type}")


def polygon_bbox(polygons: list[Polygon]) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for polygon in polygons:
        for ring in polygon:
            for longitude, latitude, *_ in ring:
                xs.append(longitude)
                ys.append(latitude)
    if not xs:
        raise ValueError("boundary geometry has no coordinates")
    return min(xs), min(ys), max(xs), max(ys)


def load_boundaries(path: Path) -> list[Boundary]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection":
        raise ValueError("boundary file is not a GeoJSON FeatureCollection")
    boundaries: list[Boundary] = []
    seen_codes: set[str] = set()
    for feature in payload.get("features", []):
        properties = feature.get("properties", {})
        code = str(properties.get("KDPPUM", "")).strip()
        name = str(properties.get("WADMPR", "")).strip()
        if not code or not name or code in seen_codes:
            raise ValueError("boundary codes and names must be unique and non-empty")
        polygons = geometry_polygons(feature.get("geometry", {}))
        boundaries.append(Boundary(code, name, polygons, polygon_bbox(polygons)))
        seen_codes.add(code)
    if len(boundaries) != 38:
        raise ValueError(f"expected 38 Indonesian ADM1 features, found {len(boundaries)}")
    return sorted(boundaries, key=lambda boundary: boundary.code)


def point_on_segment(
    x: float,
    y: float,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    epsilon: float = 1e-12,
) -> bool:
    cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
    scale = max(1.0, abs(x2 - x1), abs(y2 - y1))
    if abs(cross) > epsilon * scale:
        return False
    return (
        min(x1, x2) - epsilon <= x <= max(x1, x2) + epsilon
        and min(y1, y2) - epsilon <= y <= max(y1, y2) + epsilon
    )


def ring_relation(x: float, y: float, ring: list[list[float]]) -> str:
    inside = False
    for index in range(len(ring)):
        x1, y1, *_ = ring[index]
        x2, y2, *_ = ring[(index + 1) % len(ring)]
        if point_on_segment(x, y, x1, y1, x2, y2):
            return "boundary"
        crosses = (y1 > y) != (y2 > y)
        if crosses:
            intersection_x = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < intersection_x:
                inside = not inside
    return "inside" if inside else "outside"


def polygon_relation(x: float, y: float, polygon: Polygon) -> str:
    if not polygon:
        return "outside"
    exterior = ring_relation(x, y, polygon[0])
    if exterior != "inside":
        return exterior
    for hole in polygon[1:]:
        relation = ring_relation(x, y, hole)
        if relation == "boundary":
            return "boundary"
        if relation == "inside":
            return "outside"
    return "inside"


def boundary_relation(x: float, y: float, boundary: Boundary) -> str:
    west, south, east, north = boundary.bbox
    if not (west <= x <= east and south <= y <= north):
        return "outside"
    found_inside = False
    for polygon in boundary.polygons:
        relation = polygon_relation(x, y, polygon)
        if relation == "boundary":
            return "boundary"
        if relation == "inside":
            found_inside = True
    return "inside" if found_inside else "outside"


Segment = tuple[float, float, float, float]


def build_segment_grid(
    boundaries: list[Boundary], *, cell_size: float, threshold: float
) -> dict[tuple[int, int], list[Segment]]:
    grid: dict[tuple[int, int], list[Segment]] = defaultdict(list)
    for boundary in boundaries:
        for polygon in boundary.polygons:
            for ring in polygon:
                for index in range(len(ring)):
                    x1, y1, *_ = ring[index]
                    x2, y2, *_ = ring[(index + 1) % len(ring)]
                    segment = (x1, y1, x2, y2)
                    x_start = math.floor((min(x1, x2) - threshold) / cell_size)
                    x_end = math.floor((max(x1, x2) + threshold) / cell_size)
                    y_start = math.floor((min(y1, y2) - threshold) / cell_size)
                    y_end = math.floor((max(y1, y2) + threshold) / cell_size)
                    for x_cell in range(x_start, x_end + 1):
                        for y_cell in range(y_start, y_end + 1):
                            grid[(x_cell, y_cell)].append(segment)
    return grid


def point_segment_distance(x: float, y: float, segment: Segment) -> float:
    x1, y1, x2, y2 = segment
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(x - x1, y - y1)
    projection = ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)
    projection = max(0.0, min(1.0, projection))
    return math.hypot(x - (x1 + projection * dx), y - (y1 + projection * dy))


def is_near_boundary(
    x: float,
    y: float,
    grid: dict[tuple[int, int], list[Segment]],
    *,
    cell_size: float,
    threshold: float,
) -> bool:
    cell = (math.floor(x / cell_size), math.floor(y / cell_size))
    return any(
        point_segment_distance(x, y, segment) <= threshold
        for segment in grid.get(cell, [])
    )


def join_rows(
    rows: list[dict[str, str]],
    boundaries: list[Boundary],
    *,
    ambiguity_threshold_degrees: float,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    cell_size = 0.05
    segment_grid = build_segment_grid(
        boundaries, cell_size=cell_size, threshold=ambiguity_threshold_degrees
    )
    enriched: list[dict[str, str]] = []
    status_counts: Counter[str] = Counter()
    province_counts: Counter[str] = Counter()
    province_names: dict[str, str] = {}
    status_by_type: dict[str, Counter[str]] = defaultdict(Counter)
    near_boundary_count = 0

    for row in rows:
        longitude = float(row["longitude"])
        latitude = float(row["latitude"])
        inside: list[Boundary] = []
        exact_boundary: list[Boundary] = []
        for boundary in boundaries:
            relation = boundary_relation(longitude, latitude, boundary)
            if relation == "inside":
                inside.append(boundary)
            elif relation == "boundary":
                exact_boundary.append(boundary)

        if exact_boundary:
            status = "boundary"
            match = None
        elif len(inside) == 1:
            status = "assigned"
            match = inside[0]
        elif len(inside) > 1:
            status = "multiple"
            match = None
        else:
            status = "unassigned"
            match = None

        near_boundary = is_near_boundary(
            longitude,
            latitude,
            segment_grid,
            cell_size=cell_size,
            threshold=ambiguity_threshold_degrees,
        )
        near_boundary_count += int(near_boundary)
        status_counts[status] += 1
        status_by_type[row["type"]][status] += 1
        output = dict(row)
        if match is None:
            output["province_code"] = ""
            output["province_name"] = ""
        else:
            output["province_code"] = match.code
            output["province_name"] = match.name
            province_counts[match.code] += 1
            province_names[match.code] = match.name
        output["join_status"] = status
        output["boundary_near_0_001deg"] = "true" if near_boundary else "false"
        enriched.append(output)

    return enriched, {
        "boundary_features": len(boundaries),
        "status_counts": dict(sorted(status_counts.items())),
        "status_by_type": {
            anomaly_type: dict(sorted(counts.items()))
            for anomaly_type, counts in sorted(status_by_type.items())
        },
        "near_generalized_boundary_count": near_boundary_count,
        "ambiguity_threshold_degrees": ambiguity_threshold_degrees,
        "ambiguity_threshold_note": (
            "0.001 degree is approximately 109-111 metres at Indonesian latitudes; "
            "near-boundary assignments require review against full-resolution geometry."
        ),
        "province_counts": {
            code: {"name": province_names[code], "count": count}
            for code, count in sorted(province_counts.items())
        },
    }


def write_csv(path: Path, rows: Iterable[dict[str, str]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def analyze(
    *,
    source_csv: Path,
    boundaries_geojson: Path,
    date_from: date,
    date_to: date,
    sample_output: Path,
    enriched_output: Path,
    profile_output: Path,
) -> dict[str, Any]:
    requested_dates = {value.isoformat() for value in inclusive_dates(date_from, date_to)}
    full_profile = ProfileAccumulator(ARCHIVE_COLUMNS)
    sample_rows: list[dict[str, str]] = []
    with source_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ARCHIVE_COLUMNS:
            raise ValueError(
                f"unexpected historical schema: {reader.fieldnames!r}; "
                f"expected {ARCHIVE_COLUMNS!r}"
            )
        for row in reader:
            full_profile.add(row)
            if row["acq_date"] in requested_dates:
                sample_rows.append(row)

    present_sample_dates = {row["acq_date"] for row in sample_rows}
    missing_requested = sorted(requested_dates - present_sample_dates)
    if missing_requested:
        raise ValueError(f"requested dates have no rows: {missing_requested}")
    if len(requested_dates) < 2:
        raise ValueError("historical feasibility sample must cover multiple dates")

    sample_profile = ProfileAccumulator(ARCHIVE_COLUMNS)
    for row in sample_rows:
        sample_profile.add(row)
    write_csv(sample_output, sample_rows, ARCHIVE_COLUMNS)

    boundaries = load_boundaries(boundaries_geojson)
    enriched_rows, join_profile = join_rows(
        sample_rows, boundaries, ambiguity_threshold_degrees=0.001
    )
    enriched_columns = ARCHIVE_COLUMNS + [
        "province_code",
        "province_name",
        "join_status",
        "boundary_near_0_001deg",
    ]
    write_csv(enriched_output, enriched_rows, enriched_columns)

    result = {
        "source": {
            "path": str(source_csv),
            "bytes": source_csv.stat().st_size,
            "sha256": sha256(source_csv),
        },
        "boundary": {
            "path": str(boundaries_geojson),
            "bytes": boundaries_geojson.stat().st_size,
            "sha256": sha256(boundaries_geojson),
            "feature_count": len(boundaries),
            "province_codes": [boundary.code for boundary in boundaries],
            "province_names": [boundary.name for boundary in boundaries],
            "crs": "EPSG:4326",
            "server_generalization_degrees": 0.001,
        },
        "historical_source_profile": full_profile.result(),
        "bounded_sample": {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "requested_calendar_days": len(requested_dates),
            "all_requested_dates_present": True,
            "raw_output": {
                "path": str(sample_output),
                "bytes": sample_output.stat().st_size,
                "sha256": sha256(sample_output),
            },
            "enriched_output": {
                "path": str(enriched_output),
                "bytes": enriched_output.stat().st_size,
                "sha256": sha256(enriched_output),
            },
            "profile": sample_profile.result(),
            "join": join_profile,
        },
    }
    profile_output.parent.mkdir(parents=True, exist_ok=True)
    profile_output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--boundaries", type=Path, required=True)
    parser.add_argument("--date-from", required=True)
    parser.add_argument("--date-to", required=True)
    parser.add_argument("--sample-output", type=Path, required=True)
    parser.add_argument("--enriched-output", type=Path, required=True)
    parser.add_argument("--profile-output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = analyze(
        source_csv=args.source,
        boundaries_geojson=args.boundaries,
        date_from=iso_date(args.date_from),
        date_to=iso_date(args.date_to),
        sample_output=args.sample_output,
        enriched_output=args.enriched_output,
        profile_output=args.profile_output,
    )
    print(
        json.dumps(
            {
                "rows": result["bounded_sample"]["profile"]["shape"]["rows"],
                "join": result["bounded_sample"]["join"]["status_counts"],
                "profile_output": str(args.profile_output),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
