# D04 — DE-to-BE data contract handoff

**Status:** DE technical implementation complete; D04 remains `IN_PROGRESS` pending
Backend consumer verification and Tech Lead approval  
**Date:** 2026-10-22  
**Handoff owner:** Data Engineer  
**Required reviewer:** Backend Engineer

## Outcome

The D03 proposal has been replaced for future implementation by a versioned `1.0.0`
review candidate that incorporates the approved G1 product, date window, coverage gaps,
and OSM-derived 38-province baseline. The older `0.1.0-proposal` files are retained as
historical evidence and are not modified or represented as approved.

D04 does not implement ingestion, ClickHouse DDL, grants, or backend endpoints. It does
not approve D04, A01, or G2. Hotspots remain satellite detections, not confirmed fires
or burned-area measurements.

## Delivered artifacts

- `data/contracts/hotspot_data_contract_v1.0.0.md`: four stable published interface
  names, logical/ClickHouse-compatible types, nullability, identity and deduplication,
  coverage and geography rules, read-only boundary, map limits, and semantic-versioning
  policy.
- `data/contracts/hotspot_data_contract_v1.0.0.schema.json`: JSON Schema draft 2020-12
  definition for observations, daily coverage, province metadata, immutable batches,
  and gap-aware reference-query outcomes.
- `data/contracts/fixtures/hotspot_data_contract_v1.0.0.fixture.json`: explicitly
  synthetic fixture covering assigned/unassigned geography, zero FRP, present coverage,
  both known gap dates, province attribution, provenance, partial aggregates, and a
  wholly unavailable request.
- `data/scripts/validate_data_contract.py`: dependency-free schema-subset and semantic
  validator for the committed fixture and approved D03B crosswalk.
- `data/tests/test_d04_data_contract.py`: automated schema, type/range, nullable
  geography, coverage-gap, reference-query, crosswalk, map-limit, and read-only tests.

## Contract decisions encoded

1. Product `VNP14IMG.002_SNPP_FIRMS_SP` only, calendar 2023 UTC only.
2. Dates 2023-07-26 and 2023-07-27 are `known_satellite_gap` with null counts and NASA
   LDOPE issue 480 evidence; they can never be converted to zero.
3. Province assignment uses pinned boundary ID `osm-idn-adm1-2026-10-10b`. Exactly one
   point-in-polygon match is assigned; zero or multiple matches retain null province
   fields. There is no nearest-province coercion.
4. The serving identity is limited to `SELECT` on four future published interfaces.
   D06 must implement and test actual ClickHouse grants.
5. Map retrieval is stable-ordered, defaults to 500, is hard-capped at 5,000, and uses
   an `effective_limit + 1` truncation check.
6. Approved versions are immutable. Breaking semantics require a major version and
   coordinated DE/BE/Tech Lead review.
7. ODbL 1.0 attribution (`© OpenStreetMap contributors`) and applicable share-alike
   obligations remain binding for redistributed geometry/database artifacts.

## Verification actually run

From the repository root:

```bash
python3 -m json.tool data/contracts/hotspot_data_contract_v1.0.0.schema.json >/dev/null
python3 -m json.tool data/contracts/fixtures/hotspot_data_contract_v1.0.0.fixture.json >/dev/null
python3 data/scripts/validate_data_contract.py \
  --schema data/contracts/hotspot_data_contract_v1.0.0.schema.json \
  --fixture data/contracts/fixtures/hotspot_data_contract_v1.0.0.fixture.json \
  --boundary-provenance data/provenance/d03b_reusable_boundary.json
python3 -m unittest discover -s data/tests -p 'test_*.py'
```

Observed results:

- Both JSON documents parsed successfully.
- Contract validation returned `status=passed`: 2 synthetic observations, 3 daily
  coverage records, 2 representative fixture provinces checked against all 38 approved
  crosswalk entries, 1 synthetic batch, and 2 reference queries.
- Complete DE suite: **27 tests passed** in 4.597 seconds.

## Backend handoff requirements

The Backend reviewer must still:

1. Run a consumer contract test that loads the committed fixture through BE-side
   repository/domain models without silently discarding coverage or nullable geography.
2. Confirm the four view names and physical-type mappings are consumable by parameterized,
   read-only queries.
3. Confirm aggregate responses can represent `is_complete`, coverage issues, and no
   numeric total for a wholly unavailable range. The current mock API does not expose
   these fields; alignment belongs to A01/B02 and must not be silently patched here.
4. Confirm the 500 default / 5,000 hard map cap and stable truncation ordering.
5. Record exact commands/results and any requested contract change.

Only after that review is evidenced may the implementation state move to `IN_REVIEW`.
Only the Tech Lead may approve D04 and move it to `DONE`. Until then A01, D05, B02, and
G2 remain blocked according to the canonical backlog.

## Known limitations

- The committed fixture is intentionally synthetic and is not NASA analytical evidence.
- No ClickHouse instance, DDL, view, grant, or real ingestion path was created or tested;
  those belong to D05/D06 after approvals.
- The existing API contract and mock backend cannot yet express all coverage outcomes.
  D04 defines the required data semantics; A01 must approve their public representation.
- Community OSM provenance, simplification differences, and ODbL obligations accepted at
  G1 remain visible and unchanged.
