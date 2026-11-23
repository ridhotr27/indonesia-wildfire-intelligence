#!/usr/bin/env python3
"""Build an immutable D05 batch for the approved FIRMS data contract v1.0.0."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import tempfile
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit

try:
    from data.scripts.validate_historical_sample import Boundary, load_boundaries
    from data.scripts.validate_d03_requirements import (
        prepare_boundary_scanlines,
        prepared_boundary_relation,
    )
    from data.scripts.validate_reusable_boundaries import (
        ODBL_URL,
        PROVINCES,
        SOURCE_COMMIT,
        SOURCE_URL as BOUNDARY_SOURCE_URL,
    )
except ModuleNotFoundError:  # Direct execution: python data/scripts/ingest_firms_v1.py
    from validate_historical_sample import Boundary, load_boundaries
    from validate_d03_requirements import prepare_boundary_scanlines, prepared_boundary_relation
    from validate_reusable_boundaries import (  # type: ignore[no-redef]
        ODBL_URL,
        PROVINCES,
        SOURCE_COMMIT,
        SOURCE_URL as BOUNDARY_SOURCE_URL,
    )


CONTRACT_VERSION = "1.0.0"
MULTI_YEAR_CONTRACT_VERSION = "1.1.0"
SUPPORTED_CONTRACT_VERSIONS = {CONTRACT_VERSION, MULTI_YEAR_CONTRACT_VERSION}
TRANSFORM_VERSION = "d05-ingestion-v1"
PRODUCT_ID = "VNP14IMG.002_SNPP_FIRMS_SP"
BOUNDARY_SOURCE_ID = "osm-idn-adm1-2026-10-10b"
BOUNDARY_SNAPSHOT = "2026-10-10b"
BOUNDARY_CANONICAL_SHA256 = "e9bd1f1fb1ba39ea0e07a7ba71cbbb2f048e64d6b49316cad7e88689aade74dd"
BOUNDARY_SOURCE_SHA256 = "9dd43439b284186c91a2443c9fb9e5eabb885f75597f1ab83221f43a7ef88de7"
BOUNDARY_LICENSE = "Open Data Commons Open Database License 1.0"
BOUNDARY_ATTRIBUTION = "© OpenStreetMap contributors"
SUPPORTED_START = date(2023, 1, 1)
SUPPORTED_END = date(2023, 12, 31)
KNOWN_GAPS = {date(2023, 7, 26), date(2023, 7, 27)}
SUPPORTED_YEARS = {2023, 2024, 2025}
GAP_EVIDENCE_URL = "https://landweb.modaps.eosdis.nasa.gov/displayissue?id=480"
EXPECTED_HEADER = [
    "latitude", "longitude", "bright_ti4", "scan", "track", "acq_date",
    "acq_time", "satellite", "instrument", "confidence", "version",
    "bright_ti5", "frp", "daynight", "type",
]
CONFIDENCE_LABELS = {"l": "low", "n": "nominal", "h": "high"}


class IngestionError(ValueError):
    """Raised when an artifact cannot be safely published."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_utc(value: str, field: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise IngestionError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise IngestionError(f"{field} must be UTC")
    return parsed.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _credential_free_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise IngestionError("source URL must be credential-free HTTPS")
    if parsed.query or parsed.fragment:
        raise IngestionError("source URL must not contain query parameters or fragments")
    return value


def _strict_float(raw: str, field: str, *, minimum: float | None = None,
                  maximum: float | None = None, positive: bool = False) -> float:
    try:
        value = float(raw)
    except ValueError as exc:
        raise IngestionError(f"{field} must be numeric") from exc
    if not (value == value and abs(value) != float("inf")):
        raise IngestionError(f"{field} must be finite")
    if minimum is not None and value < minimum:
        raise IngestionError(f"{field} is below {minimum}")
    if maximum is not None and value > maximum:
        raise IngestionError(f"{field} is above {maximum}")
    if positive and value <= 0:
        raise IngestionError(f"{field} must be positive")
    return value


def source_record_hash(raw_values: list[str]) -> str:
    return hashlib.sha256("\x1f".join(raw_values).encode("utf-8")).hexdigest()


def observation_id(record_hash: str) -> str:
    return hashlib.sha256(f"{PRODUCT_ID}\x1f{record_hash}".encode("utf-8")).hexdigest()


def _assign(longitude: float, latitude: float,
            boundaries: list[tuple[Boundary, Any]]) -> tuple[str, Boundary | None]:
    matches = [
        boundary for boundary, prepared in boundaries
        if prepared_boundary_relation(longitude, latitude, boundary, prepared)
        in {"inside", "boundary"}
    ]
    if len(matches) == 1:
        return "assigned", matches[0]
    if len(matches) > 1:
        return "multiple_match", None
    return "unassigned", None


def year_bounds(source_year: int) -> tuple[date, date]:
    if source_year not in SUPPORTED_YEARS:
        raise IngestionError("source year must be between 2023 and 2025")
    return date(source_year, 1, 1), date(source_year, 12, 31)


def known_gaps(source_year: int) -> set[date]:
    year_bounds(source_year)
    return KNOWN_GAPS if source_year == 2023 else set()


def transform_version(source_year: int, contract_version: str = CONTRACT_VERSION) -> str:
    year_bounds(source_year)
    if contract_version not in SUPPORTED_CONTRACT_VERSIONS:
        raise IngestionError("contract version must be 1.0.0 or 1.1.0")
    if contract_version == MULTI_YEAR_CONTRACT_VERSION:
        return "d08-multiyear-ingestion-v1"
    return TRANSFORM_VERSION if source_year == 2023 else "d08-year-aware-ingestion-v1"


def parse_row(raw: dict[str, str], raw_values: list[str], row_number: int,
              batch_id: str, boundaries: list[tuple[Boundary, Any]],
              source_year: int = 2023,
              contract_version: str = CONTRACT_VERSION) -> dict[str, Any]:
    try:
        acquired_date = date.fromisoformat(raw["acq_date"])
    except ValueError as exc:
        raise IngestionError("acq_date must use YYYY-MM-DD") from exc
    supported_start, supported_end = year_bounds(source_year)
    if not supported_start <= acquired_date <= supported_end:
        raise IngestionError(f"acq_date is outside requested calendar {source_year}")
    if acquired_date in known_gaps(source_year):
        raise IngestionError(
            "observation falls on approved known satellite gap date"
        )
    if len(raw["acq_time"]) != 4 or not raw["acq_time"].isdigit():
        raise IngestionError("acq_time must be zero-padded HHMM")
    try:
        acquired = datetime.strptime(
            f"{raw['acq_date']} {raw['acq_time']}", "%Y-%m-%d %H%M"
        ).replace(tzinfo=UTC)
    except ValueError as exc:
        raise IngestionError("acquisition date/time is invalid") from exc
    if raw["satellite"] != "N" or raw["instrument"] != "VIIRS" or raw["version"] != "2":
        raise IngestionError("row does not match approved S-NPP VIIRS standard product")
    if raw["confidence"] not in CONFIDENCE_LABELS:
        raise IngestionError("confidence must be l, n, or h")
    if raw["daynight"] not in {"D", "N"}:
        raise IngestionError("daynight must be D or N")
    try:
        hotspot_type = int(raw["type"])
    except ValueError as exc:
        raise IngestionError("type must be an integer") from exc
    if not 0 <= hotspot_type <= 3:
        raise IngestionError("type must be between 0 and 3")

    latitude = _strict_float(raw["latitude"], "latitude", minimum=-90, maximum=90)
    longitude = _strict_float(raw["longitude"], "longitude", minimum=-180, maximum=180)
    frp = _strict_float(raw["frp"], "frp", minimum=0)
    status, province = _assign(longitude, latitude, boundaries)
    flags: set[str] = set()
    if frp == 0:
        flags.add("zero_frp")
    if status == "unassigned":
        flags.add("geo_unassigned")
    elif status == "multiple_match":
        flags.add("geo_multiple_match")
    record_hash = source_record_hash(raw_values)
    return {
        "contract_version": contract_version,
        "observation_id": observation_id(record_hash),
        "product_id": PRODUCT_ID,
        "source_product": "VNP14IMG",
        "collection_version": "2",
        "processing_stream": "standard",
        "satellite_code": "N",
        "satellite_name": "Suomi NPP",
        "instrument": "VIIRS",
        "acquired_at_utc": acquired.isoformat().replace("+00:00", "Z"),
        "latitude": latitude,
        "longitude": longitude,
        "brightness_i4_kelvin": _strict_float(raw["bright_ti4"], "bright_ti4"),
        "brightness_i5_kelvin": _strict_float(raw["bright_ti5"], "bright_ti5"),
        "scan_km": _strict_float(raw["scan"], "scan", positive=True),
        "track_km": _strict_float(raw["track"], "track", positive=True),
        "frp_mw": frp,
        "confidence_code": raw["confidence"],
        "confidence_label": CONFIDENCE_LABELS[raw["confidence"]],
        "daynight_code": raw["daynight"],
        "hotspot_type_code": hotspot_type,
        "province_code": province.code if province else None,
        "province_name": province.name if province else None,
        "geo_assignment_status": status,
        "geo_assignment_method": "osm_snapshot_point_intersection" if province else "none",
        "boundary_source_id": BOUNDARY_SOURCE_ID if province else None,
        "ingestion_batch_id": batch_id,
        "source_row_number": row_number,
        "source_record_hash": record_hash,
        "quality_flags": sorted(flags),
    }


def _dates(source_year: int = 2023) -> Iterable[date]:
    current, supported_end = year_bounds(source_year)
    while current <= supported_end:
        yield current
        current += timedelta(days=1)


def _write_ndjson(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
            count += 1
    return count


def _approved_crosswalk() -> list[dict[str, str]]:
    return sorted(
        (
            {
                "source_code": source_code,
                "source_name": canonical_name,
                "canonical_code": canonical_code,
                "canonical_name": canonical_name,
            }
            for source_code, (canonical_code, canonical_name) in PROVINCES.items()
        ),
        key=lambda item: item["canonical_code"],
    )


def _validate_boundary_provenance(
    provenance: dict[str, Any], boundary_geojson: Path
) -> list[dict[str, str]]:
    expected_crosswalk = _approved_crosswalk()
    source = provenance.get("source", {})
    artifacts = provenance.get("artifacts", {})
    source_artifact = artifacts.get("source", {})
    canonical_artifact = artifacts.get("canonical", {})
    expected_source = {
        "commit": SOURCE_COMMIT,
        "snapshot": BOUNDARY_SNAPSHOT,
        "source_url": BOUNDARY_SOURCE_URL,
        "license": BOUNDARY_LICENSE,
        "license_url": ODBL_URL,
        "required_attribution": BOUNDARY_ATTRIBUTION,
        "crs": "OGC:CRS84 / WGS84 longitude-latitude",
    }
    for field, expected in expected_source.items():
        if source.get(field) != expected:
            raise IngestionError(
                f"boundary provenance {field} does not match approved value"
            )
    if source_artifact.get("sha256") != BOUNDARY_SOURCE_SHA256:
        raise IngestionError("boundary provenance source checksum is not approved")
    if canonical_artifact.get("sha256") != BOUNDARY_CANONICAL_SHA256:
        raise IngestionError("boundary provenance canonical checksum is not approved")
    if provenance.get("crosswalk") != expected_crosswalk:
        raise IngestionError("boundary provenance crosswalk is not the approved 38-province mapping")
    if sha256_file(boundary_geojson) != BOUNDARY_CANONICAL_SHA256:
        raise IngestionError("boundary artifact checksum is not the approved canonical checksum")
    return expected_crosswalk


def _province_rows(
    provenance: dict[str, Any], crosswalk: list[dict[str, str]],
    contract_version: str = CONTRACT_VERSION,
) -> list[dict[str, Any]]:
    artifacts = provenance["artifacts"]
    source = provenance["source"]
    return [{
        "contract_version": contract_version,
        "province_code": item["canonical_code"],
        "province_name": item["canonical_name"],
        "source_code": item["source_code"],
        "source_name": item["source_name"],
        "boundary_source_id": BOUNDARY_SOURCE_ID,
        "snapshot": source["snapshot"],
        "commit": source["commit"],
        "crs": "OGC:CRS84",
        "source_sha256": artifacts["source"]["sha256"],
        "canonical_sha256": artifacts["canonical"]["sha256"],
        "license": "ODbL-1.0",
        "license_url": source["license_url"],
        "required_attribution": source["required_attribution"],
        "is_supported": True,
    } for item in crosswalk]


def _verify_existing(
    destination: Path, source_sha: str, source_url: str, source_year: int,
    expected_transform_version: str, contract_version: str,
) -> dict[str, Any]:
    manifest_path = destination / "manifest.json"
    if not manifest_path.is_file():
        raise IngestionError("existing batch is incomplete: manifest missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("source_artifact_sha256") != source_sha:
        raise IngestionError("existing batch source checksum mismatch")
    if manifest.get("source_url") != source_url:
        raise IngestionError("existing batch source request identity mismatch")
    if (
        manifest.get("ingestion_batch_id") != destination.name
        or manifest.get("contract_version") != contract_version
        or manifest.get("product_id") != PRODUCT_ID
        or manifest.get("transform_version") != expected_transform_version
        or manifest.get("source_year", 2023) != source_year
        or manifest.get("boundary_source_id") != BOUNDARY_SOURCE_ID
        or manifest.get("publication") != {"atomic": True, "state": "published"}
    ):
        raise IngestionError("existing batch manifest identity is invalid")
    required_artifacts = {
        "observations.ndjson", "daily_coverage.ndjson", "provinces.ndjson",
        "ingestion_batch.ndjson",
    }
    if set(manifest.get("artifacts", {})) != required_artifacts:
        raise IngestionError("existing batch manifest artifact set is invalid")
    for name, metadata in manifest["artifacts"].items():
        artifact = destination / name
        if not artifact.is_file() or sha256_file(artifact) != metadata["sha256"]:
            raise IngestionError(f"existing immutable artifact failed verification: {name}")
    return manifest


def ingest(*, source_csv: Path, boundary_geojson: Path, boundary_provenance: Path,
           output_root: Path, source_url: str, retrieved_at_utc: str,
           provider_last_modified_utc: str | None = None,
           source_year: int = 2023,
           contract_version: str = CONTRACT_VERSION) -> dict[str, Any]:
    source_url = _credential_free_url(source_url)
    retrieved_at_utc = _parse_utc(retrieved_at_utc, "retrieved_at_utc")
    if provider_last_modified_utc:
        provider_last_modified_utc = _parse_utc(
            provider_last_modified_utc, "provider_last_modified_utc"
        )
    expected_transform_version = transform_version(source_year, contract_version)
    source_sha = sha256_file(source_csv)
    batch_prefix = "firms-v11" if contract_version == MULTI_YEAR_CONTRACT_VERSION else "firms-v1"
    batch_id = f"{batch_prefix}-{source_sha[:20]}-{expected_transform_version}"
    destination = output_root / batch_id
    provenance = json.loads(boundary_provenance.read_text(encoding="utf-8"))
    approved_crosswalk = _validate_boundary_provenance(provenance, boundary_geojson)
    if destination.exists():
        return _verify_existing(
            destination, source_sha, source_url, source_year,
            expected_transform_version, contract_version,
        )
    boundaries = [
        (boundary, prepare_boundary_scanlines(boundary))
        for boundary in load_boundaries(boundary_geojson)
    ]
    output_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{batch_id}-", dir=output_root))
    try:
        observations_path = staging / "observations.ndjson"
        seen: set[str] = set()
        daily: Counter[date] = Counter()
        source_count = canonical_count = duplicate_count = 0
        first_timestamp: str | None = None
        last_timestamp: str | None = None
        with source_csv.open("r", encoding="utf-8", newline="") as source_handle, \
                observations_path.open("w", encoding="utf-8", newline="\n") as output_handle:
            reader = csv.reader(source_handle)
            try:
                header = next(reader)
            except StopIteration as exc:
                raise IngestionError("source CSV is empty") from exc
            if header != EXPECTED_HEADER:
                raise IngestionError("source CSV header does not match approved 15-column schema")
            for row_number, values in enumerate(reader, start=1):
                source_count += 1
                if len(values) != len(EXPECTED_HEADER):
                    raise IngestionError(f"row {row_number}: expected 15 columns")
                raw = dict(zip(EXPECTED_HEADER, values, strict=True))
                try:
                    observation = parse_row(
                        raw, values, row_number, batch_id, boundaries, source_year,
                        contract_version,
                    )
                except IngestionError as exc:
                    raise IngestionError(f"row {row_number}: {exc}") from exc
                record_hash = observation["source_record_hash"]
                if record_hash in seen:
                    duplicate_count += 1
                    continue
                seen.add(record_hash)
                canonical_count += 1
                acquired = observation["acquired_at_utc"]
                first_timestamp = acquired if first_timestamp is None else min(first_timestamp, acquired)
                last_timestamp = acquired if last_timestamp is None else max(last_timestamp, acquired)
                daily[date.fromisoformat(acquired[:10])] += 1
                output_handle.write(json.dumps(observation, sort_keys=True, separators=(",", ":")) + "\n")
        if not canonical_count or first_timestamp is None or last_timestamp is None:
            raise IngestionError("source contains no publishable observations")

        coverage_rows = []
        for day in _dates(source_year):
            if day in known_gaps(source_year):
                status, count, evidence, batch, note = (
                    "known_satellite_gap", None, GAP_EVIDENCE_URL, None,
                    "Permanent S-NPP VIIRS observation gap; never interpret as zero detections.",
                )
            elif daily[day] > 0:
                status, count, evidence, batch, note = (
                    "observations_present", daily[day], None, batch_id, None,
                )
            else:
                status, count, evidence, batch, note = (
                    "unknown", None, None, None,
                    "No source rows; completeness has not been independently established.",
                )
            coverage_rows.append({
                "contract_version": contract_version, "product_id": PRODUCT_ID,
                "date_utc": day.isoformat(), "coverage_status": status,
                "observation_count": count, "evidence_url": evidence, "note": note,
                "ingestion_batch_id": batch,
            })
        _write_ndjson(staging / "daily_coverage.ndjson", coverage_rows)
        _write_ndjson(
            staging / "provinces.ndjson",
            _province_rows(provenance, approved_crosswalk, contract_version),
        )

        batch = {
            "contract_version": contract_version, "ingestion_batch_id": batch_id,
            "product_id": PRODUCT_ID, "source_url": source_url,
            "source_artifact_sha256": source_sha, "source_bytes": source_csv.stat().st_size,
            "retrieved_at_utc": retrieved_at_utc,
            "provider_last_modified_utc": provider_last_modified_utc,
            "coverage_start_utc": first_timestamp, "coverage_end_utc": last_timestamp,
            "source_row_count": source_count, "canonical_row_count": canonical_count,
            "duplicate_excess_rows": duplicate_count, "rejected_row_count": 0,
            "transform_version": expected_transform_version,
            "provenance_manifest_path": f"{batch_id}/manifest.json",
            "publication_status": "published",
            "published_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace(
                "+00:00", "Z"
            ),
        }
        _write_ndjson(staging / "ingestion_batch.ndjson", [batch])
        artifacts = {}
        for path in sorted(staging.glob("*.ndjson")):
            artifacts[path.name] = {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
        manifest = {
            "contract_version": contract_version, "ticket": "D05",
            "classification": "pipeline_output_from_supplied_source_artifact",
            "ingestion_batch_id": batch_id, "product_id": PRODUCT_ID,
            "transform_version": expected_transform_version,
            "source_artifact_sha256": source_sha, "source_url": source_url,
            "boundary_source_id": BOUNDARY_SOURCE_ID,
            "boundary_canonical_sha256": BOUNDARY_CANONICAL_SHA256,
            "artifacts": artifacts, "counts": {
                "source_rows": source_count, "canonical_rows": canonical_count,
                "duplicate_excess_rows": duplicate_count, "rejected_rows": 0,
                "coverage_days": len(coverage_rows),
                "provinces": len(approved_crosswalk),
            },
            "publication": {"state": "published", "atomic": True},
        }
        if contract_version == MULTI_YEAR_CONTRACT_VERSION:
            manifest.update({
                "source_year": source_year,
                "ticket": "D08",
                "clickhouse_ingestion_authorized": False,
                "authorization_note": (
                    "Candidate v1.1 artifact; authorization is release-scoped and "
                    "requires a checksum-bound approved release manifest."
                ),
            })
        elif source_year != 2023:
            manifest.update({
                "source_year": source_year,
                "ticket": "D08",
                "clickhouse_ingestion_authorized": False,
                "authorization_note": (
                    "Candidate year-aware artifact; contract publication and "
                    "ClickHouse ingestion require separate approval."
                ),
            })
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(staging, destination)
        return manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-csv", type=Path, required=True)
    parser.add_argument("--boundary-geojson", type=Path, required=True)
    parser.add_argument("--boundary-provenance", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--retrieved-at-utc", required=True)
    parser.add_argument("--provider-last-modified-utc")
    parser.add_argument("--source-year", type=int, choices=sorted(SUPPORTED_YEARS), default=2023)
    parser.add_argument(
        "--contract-version", choices=sorted(SUPPORTED_CONTRACT_VERSIONS),
        default=CONTRACT_VERSION,
    )
    args = parser.parse_args()
    manifest = ingest(**vars(args))
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
