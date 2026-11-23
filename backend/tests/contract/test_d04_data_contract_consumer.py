import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from wildfire_api.contracts.data_v1 import (
    MAP_DEFAULT_LIMIT,
    MAP_HARD_LIMIT,
    PRODUCT_ID,
    READ_ONLY_VIEWS,
    DataContractFixture,
    ObservationContract,
    bounded_map_rows,
)
from wildfire_api.schemas.hotspots import GeoJsonQuery, SummaryResponse

FIXTURE_PATH = (
    Path(__file__).parents[3] / "data/contracts/fixtures/hotspot_data_contract_v1.0.0.fixture.json"
)


@pytest.fixture(scope="module")
def fixture() -> DataContractFixture:
    return DataContractFixture.model_validate_json(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_backend_loads_synthetic_fixture_without_losing_nullable_geography(
    fixture: DataContractFixture,
) -> None:
    assert fixture.fixture_classification == "synthetic_contract_example"
    assert fixture.observations[0].province_code == "14"
    assert fixture.observations[1].province_code is None
    assert fixture.observations[1].province_name is None
    assert fixture.observations[1].boundary_source_id is None
    assert fixture.observations[1].frp_mw == 0


def test_v1_fixture_fields_are_not_silently_discarded(fixture: DataContractFixture) -> None:
    raw = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    for section in (
        "observations",
        "daily_coverage",
        "provinces",
        "ingestion_batches",
        "reference_queries",
    ):
        parsed_rows = getattr(fixture, section)
        assert len(parsed_rows) == len(raw[section])
        for raw_row, parsed_row in zip(raw[section], parsed_rows, strict=True):
            assert set(parsed_row.model_dump()) == set(raw_row)


@pytest.mark.parametrize(
    ("section", "field"),
    [
        ("observations", "acquired_at_utc"),
        ("ingestion_batches", "retrieved_at_utc"),
        ("ingestion_batches", "provider_last_modified_utc"),
        ("ingestion_batches", "coverage_start_utc"),
        ("ingestion_batches", "coverage_end_utc"),
        ("ingestion_batches", "published_at_utc"),
    ],
)
@pytest.mark.parametrize("invalid_timestamp", ["2023-07-25T03:20:00", "2023-07-25T10:20:00+07:00"])
def test_all_contract_timestamps_require_utc(
    section: str, field: str, invalid_timestamp: str
) -> None:
    raw = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    raw[section][0][field] = invalid_timestamp
    with pytest.raises(ValidationError, match="timestamp must"):
        DataContractFixture.model_validate(raw)


def test_product_and_coverage_identity_are_stable(fixture: DataContractFixture) -> None:
    assert {row.product_id for row in fixture.observations} == {PRODUCT_ID}
    assert {row.product_id for row in fixture.daily_coverage} == {PRODUCT_ID}
    coverage = {row.date_utc.isoformat(): row for row in fixture.daily_coverage}
    for gap_date in ("2023-07-26", "2023-07-27"):
        assert coverage[gap_date].coverage_status == "known_satellite_gap"
        assert coverage[gap_date].observation_count is None


def test_wholly_unavailable_range_never_becomes_zero(fixture: DataContractFixture) -> None:
    queries = {row.query_id: row for row in fixture.reference_queries}
    unavailable = queries["range-wholly-unavailable"]
    assert unavailable.available_detection_total is None
    assert unavailable.numeric_total_available is False
    assert unavailable.is_complete is False

    raw = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    raw["reference_queries"][1]["available_detection_total"] = 0
    with pytest.raises(ValidationError, match="unavailable numeric total must be null"):
        DataContractFixture.model_validate(raw)


def test_backend_rejects_unsupported_major_but_tolerates_additive_minor_field(
    fixture: DataContractFixture,
) -> None:
    row = fixture.observations[0].model_dump(mode="json")
    row["contract_version"] = "2.0.0"
    with pytest.raises(ValidationError, match="unsupported data contract version"):
        ObservationContract.model_validate(row)

    row["contract_version"] = "1.1.0"
    row["future_optional_field"] = "ignored by a v1 consumer"
    assert ObservationContract.model_validate(row).contract_version == "1.1.0"


def test_read_only_view_allowlist_is_exact() -> None:
    assert READ_ONLY_VIEWS == {
        "analytics_hotspot_observations_v1",
        "analytics_daily_coverage_v1",
        "analytics_provinces_v1",
        "analytics_ingestion_batches_v1",
    }
    assert all(name.startswith("analytics_") and name.endswith("_v1") for name in READ_ONLY_VIEWS)


def test_map_default_cap_and_order_are_deterministic(fixture: DataContractFixture) -> None:
    assert MAP_DEFAULT_LIMIT == 500
    assert MAP_HARD_LIMIT == 5_000
    later, earlier = fixture.observations
    rows, truncated = bounded_map_rows([later, earlier], requested_limit=1)
    assert [row.observation_id for row in rows] == [later.observation_id]
    assert truncated is True

    many = [later] * (MAP_HARD_LIMIT + 1)
    rows, truncated = bounded_map_rows(many, requested_limit=MAP_HARD_LIMIT + 100)
    assert len(rows) == MAP_HARD_LIMIT
    assert truncated is True


def test_a01_candidate_exposes_map_bounds_and_d04_coverage_semantics() -> None:
    assert GeoJsonQuery.model_fields["limit"].default == MAP_DEFAULT_LIMIT
    assert GeoJsonQuery.model_fields["limit"].metadata[1].le == MAP_HARD_LIMIT
    assert SummaryResponse.model_fields["total"].default is None
    assert "is_complete" in SummaryResponse.model_fields
    assert "coverage_issues" in SummaryResponse.model_fields
