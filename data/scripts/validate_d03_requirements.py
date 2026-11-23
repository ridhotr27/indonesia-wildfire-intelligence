#!/usr/bin/env python3
"""Reproducibly evaluate D03's ten minimum product questions."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

try:
    from data.scripts.validate_historical_sample import (
        ARCHIVE_COLUMNS,
        build_segment_grid,
        is_near_boundary,
        load_boundaries,
        point_on_segment,
    )
except ModuleNotFoundError:  # Support direct ``python data/scripts/...`` execution.
    from validate_historical_sample import (  # type: ignore[no-redef]
        ARCHIVE_COLUMNS,
        build_segment_grid,
        is_near_boundary,
        load_boundaries,
        point_on_segment,
    )


PRODUCT_ID = "VNP14IMG.002_SNPP_FIRMS_SP"
SUPPORTED_DATE_FROM = date(2023, 1, 1)
SUPPORTED_DATE_TO = date(2023, 12, 31)
KNOWN_MISSING_DATES = {date(2023, 7, 26), date(2023, 7, 27)}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def date_request_status(requested: date) -> str:
    if not SUPPORTED_DATE_FROM <= requested <= SUPPORTED_DATE_TO:
        return "unsupported_outside_validated_range"
    if requested in KNOWN_MISSING_DATES:
        return "unavailable_known_satellite_data_gap"
    return "within_validated_range"


def percent(count: int, total: int) -> float:
    return round(100.0 * count / total, 6) if total else 0.0


def prepare_boundary_scanlines(boundary: Any, cell_size: float = 0.01) -> list[list[dict[int, list[tuple[float, float, float, float]]]]]:
    """Index ring edges by latitude band for repeat point-in-polygon tests."""
    prepared = []
    for polygon in boundary.polygons:
        prepared_polygon = []
        for ring in polygon:
            bands: dict[int, list[tuple[float, float, float, float]]] = defaultdict(list)
            for index in range(len(ring)):
                x1, y1, *_ = ring[index]
                x2, y2, *_ = ring[(index + 1) % len(ring)]
                first = math.floor(min(y1, y2) / cell_size)
                last = math.floor(max(y1, y2) / cell_size)
                for band in range(first, last + 1):
                    bands[band].append((x1, y1, x2, y2))
            prepared_polygon.append(bands)
        prepared.append(prepared_polygon)
    return prepared


def scanline_ring_relation(
    x: float,
    y: float,
    bands: dict[int, list[tuple[float, float, float, float]]],
    cell_size: float = 0.01,
) -> str:
    inside = False
    for x1, y1, x2, y2 in bands.get(math.floor(y / cell_size), []):
        if point_on_segment(x, y, x1, y1, x2, y2):
            return "boundary"
        if (y1 > y) != (y2 > y):
            intersection_x = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < intersection_x:
                inside = not inside
    return "inside" if inside else "outside"


def prepared_boundary_relation(
    x: float, y: float, boundary: Any, prepared: Any
) -> str:
    west, south, east, north = boundary.bbox
    if not (west <= x <= east and south <= y <= north):
        return "outside"
    for polygon in prepared:
        exterior = scanline_ring_relation(x, y, polygon[0])
        if exterior == "boundary":
            return "boundary"
        if exterior != "inside":
            continue
        excluded_by_hole = False
        for hole in polygon[1:]:
            relation = scanline_ring_relation(x, y, hole)
            if relation == "boundary":
                return "boundary"
            if relation == "inside":
                excluded_by_hole = True
                break
        if not excluded_by_hole:
            return "inside"
    return "outside"


def validate(
    *,
    source_csv: Path,
    boundaries_geojson: Path,
    output: Path,
    boundary_warning: str = (
        "BIG geometry is generalized by 0.001 degree and has unresolved redistribution terms."
    ),
) -> dict[str, Any]:
    with source_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ARCHIVE_COLUMNS:
            raise ValueError("unexpected historical FIRMS schema")
        raw_rows = list(reader)

    boundaries = {
        boundary.code: boundary for boundary in load_boundaries(boundaries_geojson)
    }
    target_codes = ("14", "62")
    target_boundaries = {code: boundaries[code] for code in target_codes}
    boundary_grids = {
        code: build_segment_grid([boundary], cell_size=0.05, threshold=0.001)
        for code, boundary in target_boundaries.items()
    }
    boundary_scanlines = {
        code: prepare_boundary_scanlines(boundary)
        for code, boundary in target_boundaries.items()
    }

    country_months: Counter[str] = Counter()
    confidence: Counter[str] = Counter()
    province_year: Counter[str] = Counter()
    province_months: dict[str, Counter[str]] = defaultdict(Counter)
    province_near_boundary: Counter[str] = Counter()
    riau_september_1_5 = 0
    frp_zero = 0
    frp_min: float | None = None
    frp_max: float | None = None

    target_relation_counts: dict[str, Counter[str]] = {
        code: Counter() for code in target_codes
    }
    for row in raw_rows:
        month = row["acq_date"][:7]
        country_months[month] += 1
        confidence[row["confidence"]] += 1
        frp = float(row["frp"])
        frp_min = frp if frp_min is None else min(frp_min, frp)
        frp_max = frp if frp_max is None else max(frp_max, frp)
        frp_zero += int(frp == 0)
        longitude = float(row["longitude"])
        latitude = float(row["latitude"])
        for code, boundary in target_boundaries.items():
            relation = prepared_boundary_relation(
                longitude, latitude, boundary, boundary_scanlines[code]
            )
            if relation == "inside":
                target_relation_counts[code]["assigned"] += 1
                province_year[code] += 1
                province_months[code][month] += 1
                near_boundary = is_near_boundary(
                    longitude,
                    latitude,
                    boundary_grids[code],
                    cell_size=0.05,
                    threshold=0.001,
                )
                if near_boundary:
                    province_near_boundary[code] += 1
                if (
                    code == "14"
                    and "2023-09-01" <= row["acq_date"] <= "2023-09-05"
                ):
                    riau_september_1_5 += 1
            elif relation == "boundary":
                target_relation_counts[code]["exact_boundary"] += 1

    riau_sep = province_months["14"]["2023-09"]
    kalimantan_tengah_monthly = {
        f"2023-{month:02d}": province_months["62"][f"2023-{month:02d}"]
        for month in range(1, 13)
    }
    top_count = max(country_months.values())
    top_months = sorted(month for month, count in country_months.items() if count == top_count)

    confidence_result = {
        code: {"count": count, "percent": percent(count, len(raw_rows))}
        for code, count in sorted(confidence.items())
    }
    result = {
        "validation_id": "d03-ten-question-validation-v1",
        "product": {
            "product_id": PRODUCT_ID,
            "satellite": "Suomi NPP",
            "instrument": "VIIRS",
            "processing": "standard processing",
            "collection": "2",
            "source_rows": len(raw_rows),
        },
        "inputs": {
            "firms": {"path": str(source_csv), "sha256": sha256(source_csv)},
            "boundary": {
                "path": str(boundaries_geojson),
                "sha256": sha256(boundaries_geojson),
                "warning": boundary_warning,
            },
        },
        "coverage": {
            "validated_date_from": SUPPORTED_DATE_FROM.isoformat(),
            "validated_date_to": SUPPORTED_DATE_TO.isoformat(),
            "known_missing_observation_dates": sorted(
                value.isoformat() for value in KNOWN_MISSING_DATES
            ),
            "gap_classification": "missing_satellite_observations_permanent_data_gap",
            "gap_interval_utc": "2023-07-26T02:03:33Z/2023-07-27T16:50:00Z",
            "official_gap_reference": "https://landweb.modaps.eosdis.nasa.gov/displayissue?id=480",
        },
        "targeted_geographic_calculation": {
            "province_codes": list(target_codes),
            "relation_counts": {
                code: dict(sorted(counts.items()))
                for code, counts in target_relation_counts.items()
            },
            "warning": "Only the two provinces required by the minimum questions were joined across the annual file. Results are feasibility estimates until boundary terms and a production assignment method are approved.",
        },
        "questions": [
            {
                "id": 1,
                "question": "VIIRS hotspots in Riau during September 2023?",
                "support": "provisional",
                "calculation": "count rows where province_code='14' and acq_date in 2023-09",
                "result": {"detection_count": riau_sep},
                "limitations": [
                    "Uses generalized BIG geometry; near-boundary rows require full-resolution policy.",
                    "Counts satellite detections, not confirmed fires.",
                ],
            },
            {
                "id": 2,
                "question": "Monthly VIIRS detections in Central Kalimantan in 2023?",
                "support": "provisional",
                "calculation": "group province_code='62' by UTC acquisition month",
                "result": kalimantan_tengah_monthly,
                "limitations": [
                    "July includes two dates with a permanent S-NPP VIIRS data gap.",
                    "Uses generalized BIG geometry.",
                ],
            },
            {
                "id": 3,
                "question": "Compare Riau and Central Kalimantan for 2023 using the same product?",
                "support": "provisional",
                "calculation": "count assigned rows by province_code for one product and UTC year",
                "result": {
                    "Riau_14": province_year["14"],
                    "Kalimantan_Tengah_62": province_year["62"],
                    "difference_62_minus_14": province_year["62"] - province_year["14"],
                },
                "limitations": ["Same coverage and generalized-boundary limitations as questions 1-2."],
            },
            {
                "id": 4,
                "question": "Which months had the most observations in the selected dataset?",
                "support": "supported_for_country_file",
                "calculation": "group all source rows by UTC acquisition month; select maximum",
                "result": {
                    "monthly_counts": dict(sorted(country_months.items())),
                    "maximum_months": top_months,
                    "maximum_count": top_count,
                },
                "limitations": ["July is affected by the documented two-day satellite gap."],
            },
            {
                "id": 5,
                "question": "Show observation points for a specified province/date range?",
                "support": "provisional",
                "calculation": "filter assigned rows by province_code and inclusive UTC dates",
                "result": {
                    "example_filter": {
                        "province_code": "14",
                        "date_from": "2023-09-01",
                        "date_to": "2023-09-05",
                    },
                    "point_count": riau_september_1_5,
                },
                "limitations": [
                    "Map output must exclude or visibly distinguish ambiguous/unassigned points.",
                    "A bounded response must be applied by Backend.",
                ],
            },
            {
                "id": 6,
                "question": "What does FRP mean according to NASA?",
                "support": "supported_with_nasa_documentation",
                "calculation": "validate FRP field domain; retrieve meaning from NASA documentation",
                "result": {
                    "unit": "MW",
                    "meaning": "pixel-integrated fire radiative power",
                    "minimum": frp_min,
                    "maximum": frp_max,
                    "zero_value_rows": frp_zero,
                },
                "limitations": ["FRP is not burned area and zero values are retained and flagged."],
            },
            {
                "id": 7,
                "question": "What are VIIRS detection limitations?",
                "support": "supported_by_nasa_documentation_not_calculated_from_csv",
                "calculation": "none; answer through the approved NASA-document RAG corpus",
                "result": None,
                "limitations": [
                    "The detections CSV cannot quantify missed fires, cloud obscuration, or false alarms by itself."
                ],
            },
            {
                "id": 8,
                "question": "How does confidence vary by selected product?",
                "support": "supported_for_selected_product_only",
                "calculation": "group the selected product by categorical confidence code",
                "result": confidence_result,
                "limitations": [
                    "l/n/h are categorical algorithm classes, not numeric probabilities.",
                    "Cross-product comparison is unsupported because only one product is validated.",
                ],
            },
            {
                "id": 9,
                "question": "What happens when a user requests an unavailable date?",
                "support": "supported_as_validation_behavior",
                "calculation": "compare requested UTC date with validated range and known gap dates",
                "result": {
                    "2022-12-31": date_request_status(date(2022, 12, 31)),
                    "2023-07-26": date_request_status(date(2023, 7, 26)),
                    "2023-09-01": date_request_status(date(2023, 9, 1)),
                    "2024-01-01": date_request_status(date(2024, 1, 1)),
                },
                "limitations": ["Do not return a numeric zero for known missing-data dates."],
            },
            {
                "id": 10,
                "question": "Can burned hectares be inferred from these detections?",
                "support": "unsupported_must_abstain",
                "calculation": "none",
                "result": None,
                "limitations": [
                    "Point detections and FRP do not provide a burned-area estimate; use a validated burned-area product for that measure."
                ],
            },
        ],
        "province_boundary_sensitivity": {
            "near_boundary_assigned_by_province": dict(sorted(province_near_boundary.items())),
            "policy": "Generalized near-boundary assignments are not silently treated as final canonical assignments.",
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--boundaries", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--boundary-warning",
        default=(
            "BIG geometry is generalized by 0.001 degree and has unresolved redistribution terms."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = validate(
        source_csv=args.source,
        boundaries_geojson=args.boundaries,
        output=args.output,
        boundary_warning=args.boundary_warning,
    )
    print(
        json.dumps(
            {
                "questions": len(result["questions"]),
                "targeted_join": result["targeted_geographic_calculation"]["relation_counts"],
                "output": str(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
