#!/usr/bin/env python3
"""Validate the D04 JSON contract fixture without third-party dependencies."""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

PRODUCT_ID = "VNP14IMG.002_SNPP_FIRMS_SP"
CONTRACT_VERSION = "1.0.0"
BOUNDARY_SOURCE_ID = "osm-idn-adm1-2026-10-10b"
KNOWN_GAPS = {"2023-07-26", "2023-07-27"}
LDOPE_ISSUE_URL = "https://landweb.modaps.eosdis.nasa.gov/displayissue?id=480"


class ContractValidationError(ValueError):
    """Raised when a schema or cross-record semantic rule fails."""


def _resolve_ref(root: dict[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise ContractValidationError(f"unsupported external schema reference: {ref}")
    value: Any = root
    for token in ref[2:].split("/"):
        value = value[token.replace("~1", "/").replace("~0", "~")]
    return value


def _is_type(value: Any, expected: str) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }[expected]


def _validate_format(value: str, format_name: str, path: str) -> None:
    try:
        if format_name == "date":
            date.fromisoformat(value)
        elif format_name == "date-time":
            if not value.endswith("Z"):
                raise ValueError("timestamp is not UTC Z")
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        elif format_name == "uri":
            parsed = urlparse(value)
            if not parsed.scheme:
                raise ValueError("URI has no scheme")
    except ValueError as exc:
        raise ContractValidationError(f"{path}: invalid {format_name}: {value}") from exc


def validate_instance(instance: Any, schema: dict[str, Any], root: dict[str, Any], path: str = "$") -> None:
    if "$ref" in schema:
        validate_instance(instance, _resolve_ref(root, schema["$ref"]), root, path)
        return
    if "anyOf" in schema:
        for candidate in schema["anyOf"]:
            try:
                validate_instance(instance, candidate, root, path)
                return
            except ContractValidationError:
                continue
        raise ContractValidationError(f"{path}: value matches no anyOf branch")

    expected = schema.get("type")
    if expected:
        allowed = [expected] if isinstance(expected, str) else expected
        if not any(_is_type(instance, item) for item in allowed):
            raise ContractValidationError(f"{path}: expected type {allowed}, got {type(instance).__name__}")
    if "const" in schema and instance != schema["const"]:
        raise ContractValidationError(f"{path}: expected constant {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        raise ContractValidationError(f"{path}: {instance!r} is outside enum")
    if instance is None:
        return
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            raise ContractValidationError(f"{path}: string is too short")
        if "pattern" in schema and re.search(schema["pattern"], instance) is None:
            raise ContractValidationError(f"{path}: string does not match {schema['pattern']}")
        if "format" in schema:
            _validate_format(instance, schema["format"], path)
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            raise ContractValidationError(f"{path}: value is below minimum")
        if "maximum" in schema and instance > schema["maximum"]:
            raise ContractValidationError(f"{path}: value is above maximum")
        if "exclusiveMinimum" in schema and instance <= schema["exclusiveMinimum"]:
            raise ContractValidationError(f"{path}: value is not above exclusive minimum")
    if isinstance(instance, list):
        if schema.get("uniqueItems"):
            serialized = [json.dumps(item, sort_keys=True) for item in instance]
            if len(serialized) != len(set(serialized)):
                raise ContractValidationError(f"{path}: array values are not unique")
        if "items" in schema:
            for index, item in enumerate(instance):
                validate_instance(item, schema["items"], root, f"{path}[{index}]")
    if isinstance(instance, dict):
        required = set(schema.get("required", []))
        missing = required - set(instance)
        if missing:
            raise ContractValidationError(f"{path}: missing keys {sorted(missing)}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extras = set(instance) - set(properties)
            if extras:
                raise ContractValidationError(f"{path}: unexpected keys {sorted(extras)}")
        for name, value in instance.items():
            if name in properties:
                validate_instance(value, properties[name], root, f"{path}.{name}")


def validate_semantics(fixture: dict[str, Any], boundary_provenance: dict[str, Any]) -> None:
    if fixture["fixture_classification"] != "synthetic_contract_example":
        raise ContractValidationError("fixture must remain visibly synthetic")

    batches = {item["ingestion_batch_id"] for item in fixture["ingestion_batches"]}
    province_lookup = {item["province_code"]: item["province_name"] for item in fixture["provinces"]}
    for observation in fixture["observations"]:
        if observation["ingestion_batch_id"] not in batches:
            raise ContractValidationError("observation references an unknown batch")
        flags = observation["quality_flags"]
        if flags != sorted(flags):
            raise ContractValidationError("quality_flags must be sorted")
        status = observation["geo_assignment_status"]
        assigned_fields = (observation["province_code"], observation["province_name"], observation["boundary_source_id"])
        if status == "assigned":
            if any(value is None for value in assigned_fields):
                raise ContractValidationError("assigned geography requires province and boundary fields")
            if observation["geo_assignment_method"] != "osm_snapshot_point_intersection":
                raise ContractValidationError("assigned geography requires the approved intersection method")
            if observation["boundary_source_id"] != BOUNDARY_SOURCE_ID:
                raise ContractValidationError("assigned geography uses an unapproved boundary source")
            if province_lookup.get(observation["province_code"]) != observation["province_name"]:
                raise ContractValidationError("observation province does not match fixture metadata")
        else:
            if any(value is not None for value in assigned_fields):
                raise ContractValidationError("non-assigned geography must retain null province/boundary fields")
            if observation["geo_assignment_method"] != "none":
                raise ContractValidationError("non-assigned geography must use method none")
        if observation["frp_mw"] == 0 and "zero_frp" not in flags:
            raise ContractValidationError("zero FRP must be retained and flagged")
        if status == "unassigned" and "geo_unassigned" not in flags:
            raise ContractValidationError("unassigned geography must be flagged")
        if status == "multiple_match" and "geo_multiple_match" not in flags:
            raise ContractValidationError("multiple-match geography must be flagged")

    coverage = {item["date_utc"]: item for item in fixture["daily_coverage"]}
    for item in fixture["daily_coverage"]:
        status = item["coverage_status"]
        count = item["observation_count"]
        if status == "observations_present" and (count is None or count <= 0):
            raise ContractValidationError("observations_present requires a positive count")
        if status in {"known_satellite_gap", "unknown"} and count is not None:
            raise ContractValidationError(f"{status} coverage must have a null count")
        if status == "zero_detections_verified" and (count != 0 or not item["evidence_url"]):
            raise ContractValidationError("verified zero requires zero count and independent evidence")
        if status == "known_satellite_gap" and not item["evidence_url"]:
            raise ContractValidationError("known gap requires evidence")
    for gap in KNOWN_GAPS:
        item = coverage.get(gap)
        if not item or item["coverage_status"] != "known_satellite_gap" or item["observation_count"] is not None:
            raise ContractValidationError(f"{gap} must be an unavailable known gap with null count")
        if item["evidence_url"] != LDOPE_ISSUE_URL:
            raise ContractValidationError(f"{gap} must cite NASA LDOPE issue 480")

    queries = {item["query_id"]: item for item in fixture["reference_queries"]}
    wholly_gap = queries["range-wholly-unavailable"]
    if wholly_gap["numeric_total_available"] or wholly_gap["available_detection_total"] is not None:
        raise ContractValidationError("a wholly unavailable range cannot expose a numeric total")
    spanning = queries["assigned-riau-spanning-known-gap"]
    if spanning["is_complete"] or spanning["available_detection_total"] != 1:
        raise ContractValidationError("gap-spanning reference query must be partial and total available rows only")

    crosswalk = {
        item["canonical_code"]: (item["canonical_name"], item["source_code"], item["source_name"])
        for item in boundary_provenance["crosswalk"]
    }
    if len(crosswalk) != 38:
        raise ContractValidationError("approved boundary crosswalk must contain exactly 38 provinces")
    for province in fixture["provinces"]:
        expected = crosswalk.get(province["province_code"])
        actual = (province["province_name"], province["source_code"], province["source_name"])
        if expected != actual:
            raise ContractValidationError("fixture province differs from the approved crosswalk")


def load_and_validate(schema_path: Path, fixture_path: Path, boundary_provenance_path: Path) -> dict[str, int]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    provenance = json.loads(boundary_provenance_path.read_text(encoding="utf-8"))
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise ContractValidationError("schema must declare JSON Schema draft 2020-12")
    validate_instance(fixture, schema, schema)
    validate_semantics(fixture, provenance)
    return {
        "observations": len(fixture["observations"]),
        "daily_coverage": len(fixture["daily_coverage"]),
        "fixture_provinces": len(fixture["provinces"]),
        "approved_crosswalk_provinces": len(provenance["crosswalk"]),
        "ingestion_batches": len(fixture["ingestion_batches"]),
        "reference_queries": len(fixture["reference_queries"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--boundary-provenance", type=Path, required=True)
    args = parser.parse_args()
    counts = load_and_validate(args.schema, args.fixture, args.boundary_provenance)
    print(json.dumps({"status": "passed", "contract_version": CONTRACT_VERSION, **counts}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
