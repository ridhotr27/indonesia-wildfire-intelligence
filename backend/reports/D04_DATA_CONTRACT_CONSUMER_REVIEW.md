# D04 backend consumer review

**Status:** Backend technical review passed; D04 remains unapproved  
**Date:** 2026-10-22  
**Reviewer:** Backend Engineer  
**Candidate:** DE-to-BE hotspot data contract `1.0.0`

## Review outcome

The backend can consume the committed, explicitly synthetic D04 fixture without
discarding v1 fields or coercing nullable geography and unavailable coverage. The four
published interface names, field shapes, product identity, stable map ordering and map
limits are suitable inputs for a future parameterized read-only repository.

This review does not approve D04, A01, or G2. It does not implement B02, connect to
ClickHouse, validate physical DDL/grants, or claim real NASA serving results. D06 must
create and test the physical views and grants; B02 must implement the parameterized
queries only after its dependencies are approved.

## Backend evidence added

- `wildfire_api.contracts.data_v1` contains isolated Pydantic consumer models for all
  committed fixture sections. They preserve nullable province fields, gap-aware totals,
  provenance, quality fields, and the frozen product/boundary identity.
- An exact allowlist contains only `analytics_hotspot_observations_v1`,
  `analytics_daily_coverage_v1`, `analytics_provinces_v1`, and
  `analytics_ingestion_batches_v1`. This records the future BE read boundary; it is not
  evidence that ClickHouse permissions have been deployed.
- The consumer rejects unsupported contract major versions and tolerates an additive
  field on a compatible v1 minor record, as required by the compatibility policy.
- The bounded map helper orders by `(acquired_at_utc, observation_id)`, defaults to 500,
  caps at 5,000, examines at most the effective limit plus one, and does not return the
  sentinel row.
- Consumer contract tests compare every committed v1 row's parsed field names, including
  reference-query rows, with the source fixture, preventing accidental field loss while
  still allowing future optional minor-version fields.
- Every observation and ingestion-batch timestamp is validated as timezone-aware UTC;
  naive and non-zero-offset timestamps are rejected by the BE consumer.

## Type and nullability review

The ClickHouse logical types have direct backend representations for the proposed
repository boundary: strings and fixed strings become Python `str`; `Date` becomes
`date`; UTC `DateTime64` becomes timezone-aware `datetime`; integer types become
non-negative bounded or semantic Python `int`; float types become Python `float`;
arrays become typed lists; and `Nullable(...)` becomes `T | None`. Pydantic models
enforce the documented constants, enums, numeric ranges, identifiers, URLs, and
geography/coverage cross-field rules.

The synthetic fixture proves that an unassigned observation keeps `province_code`,
`province_name`, and `boundary_source_id` null, while an assigned observation uses the
accepted OSM boundary identity. Both 2023-07-26 and 2023-07-27 remain
`known_satellite_gap` with null observation counts. The wholly unavailable reference
range retains a null total, and a mutation to numeric zero is rejected.

## Existing backend draft compatibility

The existing B01 mock foundation is contract-neutral enough to remain in place, but it
is not yet a complete public representation of D04:

- `GeoJsonQuery` already uses the required default 500 and hard maximum 5,000.
- The mock repository's point record assumes assigned geography, which is acceptable
  for the D04 map rule because map queries select assigned rows only. The new D04
  consumer model separately preserves unassigned observations for analytics/QA.
- `SummaryResponse.total` is currently a required non-null integer and has no
  `is_complete`, coverage-issue, or warning fields. It therefore cannot represent a
  wholly unavailable range or a partial range honestly.
- Current GeoJSON properties are a safe draft subset but do not yet expose the allowed
  `confidence_code`, `frp_mw`, and `daynight_code` fields.
- Existing province-code request validation is broader than the D04 two-digit canonical
  format because it also supports visibly synthetic mock codes.

These are recorded alignment requirements for A01 and B02, not defects to patch
silently during D04. A01 must approve the public coverage and nullable-total shape before
the live backend or frontend types change.

## Verification run

From `backend/`:

```bash
.venv/bin/pytest tests/contract/test_d04_data_contract_consumer.py
.venv/bin/ruff check .
.venv/bin/pytest
```

Observed results after the final consumer test addition:

- D04 backend consumer tests: **20 passed**.
- Ruff: **passed**.
- Complete backend suite: **47 passed**.

From the repository project directory:

```bash
python3 data/scripts/validate_data_contract.py \
  --schema data/contracts/hotspot_data_contract_v1.0.0.schema.json \
  --fixture data/contracts/fixtures/hotspot_data_contract_v1.0.0.fixture.json \
  --boundary-provenance data/provenance/d03b_reusable_boundary.json
python3 -m unittest discover -s data/tests -p 'test_*.py'
```

Observed results:

- DE validator returned `status=passed` with 2 synthetic observations, 3 coverage rows,
  2 fixture provinces checked against the 38-province crosswalk, 1 batch, and 2
  reference queries.
- Complete DE suite: **27 tests passed** in 3.976 seconds.

## Recommendation and remaining decisions

Backend consumer review recommends moving D04 to `IN_REVIEW`. Tech Lead approval is
still required to make D04 `DONE`. A01 and G2 remain blocked, and B02/B04 must not start.
The Tech Lead should review the v1.0.0 interface names and semantics, especially the
public representation of partial/unavailable coverage that A01 must define next.
