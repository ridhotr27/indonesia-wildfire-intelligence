#!/usr/bin/env python3
"""Validate and canonicalize the D03B reusable Indonesia ADM1 candidate."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

try:
    from data.scripts.validate_d03_requirements import (
        prepare_boundary_scanlines,
        prepared_boundary_relation,
    )
    from data.scripts.validate_historical_sample import (
        Boundary,
        geometry_polygons,
        load_boundaries,
    )
except ModuleNotFoundError:  # Support direct execution from the repository root.
    from validate_d03_requirements import (  # type: ignore[no-redef]
        prepare_boundary_scanlines,
        prepared_boundary_relation,
    )
    from validate_historical_sample import (  # type: ignore[no-redef]
        Boundary,
        geometry_polygons,
        load_boundaries,
    )


SOURCE_COMMIT = "c4d208a03a71553a1082f960ebdaa88c1d8e9389"
SOURCE_URL = (
    "https://raw.githubusercontent.com/ahsa29/kpu-osm-boundaries-2026/"
    f"{SOURCE_COMMIT}/data/2026-10-10b/MapNational.geojson"
)
SOURCE_MANIFEST_URL = (
    "https://raw.githubusercontent.com/ahsa29/kpu-osm-boundaries-2026/"
    f"{SOURCE_COMMIT}/data/2026-10-10b/MapManifest.json"
)
LICENSE_URL = (
    "https://raw.githubusercontent.com/ahsa29/kpu-osm-boundaries-2026/"
    f"{SOURCE_COMMIT}/DATA_LICENSE.md"
)
ODBL_URL = "https://opendatacommons.org/licenses/odbl/1-0/"


# Stable two-digit Indonesian province identifiers used by the existing BIG
# feasibility evidence. The source OSM codes remain in every canonical feature
# so the crosswalk is reversible and versioned.
PROVINCES: dict[str, tuple[str, str]] = {
    "ID_AC": ("11", "Aceh"),
    "ID_SU": ("12", "Sumatera Utara"),
    "ID_SB": ("13", "Sumatera Barat"),
    "ID_RI": ("14", "Riau"),
    "ID_JA": ("15", "Jambi"),
    "ID_SS": ("16", "Sumatera Selatan"),
    "ID_BE": ("17", "Bengkulu"),
    "ID_LA": ("18", "Lampung"),
    "ID_BB": ("19", "Kepulauan Bangka Belitung"),
    "ID_KR": ("21", "Kepulauan Riau"),
    "ID_JK": ("31", "Daerah Khusus Jakarta"),
    "ID_JB": ("32", "Jawa Barat"),
    "ID_JT": ("33", "Jawa Tengah"),
    "ID_YO": ("34", "Daerah Istimewa Yogyakarta"),
    "ID_JI": ("35", "Jawa Timur"),
    "ID_BT": ("36", "Banten"),
    "ID_BA": ("51", "Bali"),
    "ID_NB": ("52", "Nusa Tenggara Barat"),
    "ID_NT": ("53", "Nusa Tenggara Timur"),
    "ID_KB": ("61", "Kalimantan Barat"),
    "ID_KT": ("62", "Kalimantan Tengah"),
    "ID_KS": ("63", "Kalimantan Selatan"),
    "ID_KI": ("64", "Kalimantan Timur"),
    "ID_KU": ("65", "Kalimantan Utara"),
    "ID_SA": ("71", "Sulawesi Utara"),
    "ID_ST": ("72", "Sulawesi Tengah"),
    "ID_SN": ("73", "Sulawesi Selatan"),
    "ID_SG": ("74", "Sulawesi Tenggara"),
    "ID_GO": ("75", "Gorontalo"),
    "ID_SR": ("76", "Sulawesi Barat"),
    "ID_MA": ("81", "Maluku"),
    "ID_MU": ("82", "Maluku Utara"),
    "ID_PA": ("91", "Papua"),
    "ID_PB": ("92", "Papua Barat"),
    "ID_PS": ("93", "Papua Selatan"),
    "ID_PT": ("94", "Papua Tengah"),
    "ID_PE": ("95", "Papua Pegunungan"),
    "ID_PD": ("96", "Papua Barat Daya"),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def coordinate_count(value: Any) -> int:
    if (
        isinstance(value, list)
        and len(value) >= 2
        and all(isinstance(item, (int, float)) for item in value[:2])
    ):
        return 1
    if not isinstance(value, list):
        return 0
    return sum(coordinate_count(child) for child in value)


def validate_ring(ring: list[list[float]]) -> tuple[int, tuple[float, float, float, float]]:
    if len(ring) < 4:
        raise ValueError("polygon ring must contain at least four positions")
    if ring[0][:2] != ring[-1][:2]:
        raise ValueError("polygon ring is not closed")
    longitudes: list[float] = []
    latitudes: list[float] = []
    for position in ring:
        if len(position) < 2:
            raise ValueError("GeoJSON position has fewer than two coordinates")
        longitude, latitude = position[:2]
        if not isinstance(longitude, (int, float)) or not isinstance(
            latitude, (int, float)
        ):
            raise ValueError("GeoJSON position is not numeric")
        if not math.isfinite(longitude) or not math.isfinite(latitude):
            raise ValueError("GeoJSON position is not finite")
        if not (90 <= longitude <= 145 and -15 <= latitude <= 10):
            raise ValueError(f"coordinate outside the Indonesia validation envelope: {position[:2]}")
        longitudes.append(longitude)
        latitudes.append(latitude)
    return len(ring), (
        min(longitudes),
        min(latitudes),
        max(longitudes),
        max(latitudes),
    )


def merge_bbox(
    current: tuple[float, float, float, float] | None,
    addition: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    if current is None:
        return addition
    return (
        min(current[0], addition[0]),
        min(current[1], addition[1]),
        max(current[2], addition[2]),
        max(current[3], addition[3]),
    )


def validate_geometry(geometry: dict[str, Any]) -> dict[str, Any]:
    polygons = geometry_polygons(geometry)
    if not polygons:
        raise ValueError("feature has no polygons")
    rings = 0
    positions = 0
    bbox: tuple[float, float, float, float] | None = None
    for polygon in polygons:
        if not polygon:
            raise ValueError("polygon has no exterior ring")
        for ring in polygon:
            count, ring_bbox = validate_ring(ring)
            rings += 1
            positions += count
            bbox = merge_bbox(bbox, ring_bbox)
    return {
        "geometry_type": geometry["type"],
        "polygons": len(polygons),
        "rings": rings,
        "positions": positions,
        "bbox": list(bbox or ()),
    }


def canonicalize(source: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]], dict[str, Any]]:
    if source.get("type") != "FeatureCollection":
        raise ValueError("candidate is not a GeoJSON FeatureCollection")
    features = source.get("features", [])
    if len(features) != 38:
        raise ValueError(f"expected 38 province features, found {len(features)}")

    found_codes: set[str] = set()
    found_names: set[str] = set()
    crosswalk: list[dict[str, str]] = []
    canonical_features: list[dict[str, Any]] = []
    total_polygons = total_rings = total_positions = 0
    overall_bbox: tuple[float, float, float, float] | None = None

    for feature in features:
        properties = feature.get("properties", {})
        source_code = str(properties.get("code", "")).strip()
        source_name = str(properties.get("province", "")).strip()
        if source_code not in PROVINCES:
            raise ValueError(f"unexpected source province code: {source_code!r}")
        canonical_code, expected_name = PROVINCES[source_code]
        if source_name != expected_name:
            raise ValueError(
                f"source name mismatch for {source_code}: {source_name!r} != {expected_name!r}"
            )
        if source_code in found_codes or source_name in found_names:
            raise ValueError("candidate province codes and names must be unique")
        found_codes.add(source_code)
        found_names.add(source_name)

        geometry_profile = validate_geometry(feature.get("geometry", {}))
        total_polygons += geometry_profile["polygons"]
        total_rings += geometry_profile["rings"]
        total_positions += geometry_profile["positions"]
        overall_bbox = merge_bbox(overall_bbox, tuple(geometry_profile["bbox"]))
        crosswalk.append(
            {
                "source_code": source_code,
                "source_name": source_name,
                "canonical_code": canonical_code,
                "canonical_name": expected_name,
            }
        )
        canonical_features.append(
            {
                "type": "Feature",
                "properties": {
                    "KDPPUM": canonical_code,
                    "WADMPR": expected_name,
                    "source_code": source_code,
                    "geometry_source": "OpenStreetMap contributors via pinned D03B snapshot",
                    "geometry_vintage": "2026-10-09/2026-10-10b",
                    "geometry_license": "ODbL-1.0",
                },
                "geometry": feature["geometry"],
            }
        )

    if found_codes != set(PROVINCES):
        raise ValueError("candidate does not contain the exact expected province code set")
    return (
        {
            "type": "FeatureCollection",
            "name": "idn_adm1_osm_2026-10-10b_canonical",
            "features": sorted(
                canonical_features,
                key=lambda item: item["properties"]["KDPPUM"],
            ),
        },
        sorted(crosswalk, key=lambda item: item["canonical_code"]),
        {
            "features": len(canonical_features),
            "polygons": total_polygons,
            "rings": total_rings,
            "positions": total_positions,
            "bbox": list(overall_bbox or ()),
            "structural_checks": "passed",
        },
    )


def validate_topology(feature_collection: dict[str, Any]) -> dict[str, Any]:
    try:
        from shapely.geometry import shape
        from shapely.validation import explain_validity
    except ImportError as exc:  # pragma: no cover - exercised by the validation command.
        raise RuntimeError(
            "topological validation requires Shapely; install data/requirements-validation.txt"
        ) from exc

    invalid: list[dict[str, str]] = []
    empty: list[str] = []
    for feature in feature_collection["features"]:
        code = feature["properties"]["KDPPUM"]
        geometry = shape(feature["geometry"])
        if geometry.is_empty or geometry.area <= 0:
            empty.append(code)
        if not geometry.is_valid:
            invalid.append({"province_code": code, "reason": explain_validity(geometry)})
    if empty or invalid:
        raise ValueError(
            f"topological validation failed: empty={empty}, invalid={invalid}"
        )
    return {
        "engine": "Shapely/GEOS",
        "features_checked": len(feature_collection["features"]),
        "empty_or_nonpositive_area": 0,
        "invalid": 0,
        "status": "passed",
    }


def assignment_for_point(
    longitude: float,
    latitude: float,
    boundaries: Iterable[tuple[Boundary, Any]],
) -> dict[str, Any]:
    inside: list[Boundary] = []
    exact: list[Boundary] = []
    for boundary, prepared in boundaries:
        relation = prepared_boundary_relation(longitude, latitude, boundary, prepared)
        if relation == "inside":
            inside.append(boundary)
        elif relation == "boundary":
            exact.append(boundary)
    if exact:
        return {"status": "boundary", "province_code": None, "province_name": None}
    if len(inside) == 1:
        return {
            "status": "assigned",
            "province_code": inside[0].code,
            "province_name": inside[0].name,
        }
    if len(inside) > 1:
        return {"status": "multiple", "province_code": None, "province_name": None}
    return {"status": "unassigned", "province_code": None, "province_name": None}


def compare_flagged_points(
    path: Path, boundaries: list[tuple[Boundary, Any]]
) -> dict[str, Any]:
    source = json.loads(path.read_text(encoding="utf-8"))
    records: list[dict[str, Any]] = []
    comparison_counts: Counter[str] = Counter()
    assignment_counts: Counter[str] = Counter()
    for record in source["records"]:
        candidate = assignment_for_point(
            float(record["longitude"]), float(record["latitude"]), boundaries
        )
        full_matches = record["full_resolution_matches"]
        big_code = full_matches[0]["province_code"] if len(full_matches) == 1 else None
        candidate_code = candidate["province_code"]
        if candidate["status"] == "assigned" and candidate_code == big_code:
            comparison = "same_as_big_full_resolution"
        elif candidate["status"] == "unassigned" and not full_matches:
            comparison = "both_unassigned"
        else:
            comparison = "different_from_big_full_resolution"
        comparison_counts[comparison] += 1
        assignment_counts[candidate["status"]] += 1
        records.append(
            {
                "review_index": record["review_index"],
                "longitude": record["longitude"],
                "latitude": record["latitude"],
                "big_full_resolution_matches": full_matches,
                "candidate_assignment": candidate,
                "comparison": comparison,
            }
        )
    return {
        "records_reviewed": len(records),
        "candidate_assignment_counts": dict(sorted(assignment_counts.items())),
        "comparison_counts": dict(sorted(comparison_counts.items())),
        "records": records,
        "policy": "Differences are disclosed; neither source is silently treated as ground truth.",
    }


def validate_sample(path: Path, boundaries: list[tuple[Boundary, Any]]) -> dict[str, Any]:
    status_counts: Counter[str] = Counter()
    province_counts: Counter[str] = Counter()
    rows = 0
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            rows += 1
            assignment = assignment_for_point(
                float(row["longitude"]), float(row["latitude"]), boundaries
            )
            status_counts[assignment["status"]] += 1
            if assignment["province_code"]:
                province_counts[assignment["province_code"]] += 1
    return {
        "rows": rows,
        "assignment_counts": dict(sorted(status_counts.items())),
        "province_counts": dict(sorted(province_counts.items())),
        "policy": "No nearest-province coercion; boundary, multiple, and unassigned remain null.",
    }


def write_json(path: Path, value: Any, *, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        if compact:
            json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")


def run(args: argparse.Namespace) -> dict[str, Any]:
    source = json.loads(args.source.read_text(encoding="utf-8"))
    canonical, crosswalk, geometry_profile = canonicalize(source)
    if geometry_profile["positions"] != 380_953:
        raise ValueError(
            "candidate coordinate count differs from the pinned source manifest: "
            f"{geometry_profile['positions']}"
        )
    if args.require_topology:
        geometry_profile["topological_checks"] = validate_topology(canonical)
    else:
        geometry_profile["topological_checks"] = {
            "status": "not_run",
            "reason": "--require-topology was not supplied",
        }
    write_json(args.canonical_output, canonical, compact=True)
    loaded_boundaries = load_boundaries(args.canonical_output)
    boundaries = [
        (boundary, prepare_boundary_scanlines(boundary))
        for boundary in loaded_boundaries
    ]
    flagged = compare_flagged_points(args.flagged_review, boundaries)
    sample = validate_sample(args.sample, boundaries)
    provenance = {
        "ticket": "D03B",
        "retrieved_at_utc": args.retrieved_at,
        "source": {
            "provider": "OpenStreetMap contributors via ahsa29/kpu-osm-boundaries-2026",
            "source_url": SOURCE_URL,
            "manifest_url": SOURCE_MANIFEST_URL,
            "commit": SOURCE_COMMIT,
            "snapshot": "2026-10-10b",
            "underlying_extract": "Geofabrik Indonesia OSM PBF 2026-10-09",
            "crs": "OGC:CRS84 / WGS84 longitude-latitude",
            "license": "Open Data Commons Open Database License 1.0",
            "license_url": ODBL_URL,
            "license_evidence_url": LICENSE_URL,
            "required_attribution": "© OpenStreetMap contributors",
            "redistribution": "Permitted subject to ODbL attribution and share-alike obligations.",
        },
        "artifacts": {
            "source": {
                "path": str(args.source),
                "bytes": args.source.stat().st_size,
                "sha256": sha256(args.source),
            },
            "canonical": {
                "path": str(args.canonical_output),
                "bytes": args.canonical_output.stat().st_size,
                "sha256": sha256(args.canonical_output),
            },
        },
        "geometry_profile": geometry_profile,
        "crosswalk": crosswalk,
        "limitations": [
            "This is a community-maintained OSM-derived reference, not an official BIG boundary.",
            "The national geometry is derived from district unions and simplified by at most 0.0005 degree (0.0001 for Southwest Papua).",
            "Structural GeoJSON checks and point comparisons were run locally; legal suitability and canonical adoption require Tech Lead review.",
        ],
    }
    result = {
        "ticket": "D03B",
        "status": "technical_evidence_complete_pending_tech_lead_approval",
        "provenance": provenance,
        "five_day_join": sample,
        "flagged_point_comparison": flagged,
        "recommendation": (
            "Use this pinned ODbL candidate for D04 if the Tech Lead accepts its community-maintained provenance, "
            "ODbL obligations, simplification, and observed differences from BIG."
        ),
    }
    write_json(args.provenance_output, provenance)
    write_json(args.report_output, result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--canonical-output", type=Path, required=True)
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--flagged-review", type=Path, required=True)
    parser.add_argument("--provenance-output", type=Path, required=True)
    parser.add_argument("--report-output", type=Path, required=True)
    parser.add_argument("--require-topology", action="store_true")
    parser.add_argument(
        "--retrieved-at",
        default=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    return parser.parse_args()


def main() -> None:
    result = run(parse_args())
    print(
        json.dumps(
            {
                "features": result["provenance"]["geometry_profile"]["features"],
                "five_day_join": result["five_day_join"]["assignment_counts"],
                "flagged_comparison": result["flagged_point_comparison"]["comparison_counts"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
