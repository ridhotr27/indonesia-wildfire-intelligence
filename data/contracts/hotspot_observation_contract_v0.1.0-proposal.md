# Canonical hotspot data contract v0.1.0 — proposal

**Status:** D03 proposal for Tech Lead and Backend review; not approved or deployed  
**Product:** `VNP14IMG.002_SNPP_FIRMS_SP` only  
**Validated analytical window:** 2023-01-01 through 2023-12-31 UTC, with known missing satellite observations on 2023-07-26 and 2023-07-27  
**Contract schema:** `hotspot_observation_contract_v0.1.0-proposal.schema.json`

This proposal does not authorize production ingestion or change `docs/API_CONTRACT.md`. D04 must approve the published ClickHouse view name, physical types, fixture, and Backend compatibility.

## Product identity and semantics

- NASA product: VIIRS/NPP Active Fires 6-Min L2 Swath 375 m V002 (`VNP14IMG.002`), distributed through FIRMS as VIIRS S-NPP standard processing (`VIIRS_SNPP_SP`, CSV `version=2`).
- Satellite/platform: Suomi National Polar-orbiting Partnership (`satellite_code=N`); instrument: VIIRS.
- Processing stream: standard processing only. Do not merge NRT, RT, URT, NOAA-20, NOAA-21, MODIS, or another collection into this product ID.
- Acquisition timestamps are constructed from `acq_date` plus zero-padded `acq_time` and stored as ISO 8601 UTC (`YYYY-MM-DDTHH:MM:00Z`). Date filters use UTC unless the serving contract explicitly adds a presentation timezone.
- Every row is a satellite active-fire/thermal-anomaly **detection**, not a confirmed wildfire incident or burned-area observation.

## Observation fields

| Field | Logical type | Nullable | Source / rule |
|---|---|---:|---|
| `schema_version` | string | no | Constant `0.1.0-proposal` |
| `observation_id` | lowercase hex string, 64 chars | no | SHA-256 content identifier described below |
| `product_id` | string | no | Constant `VNP14IMG.002_SNPP_FIRMS_SP` |
| `source_product` | string | no | Constant `VNP14IMG` |
| `collection_version` | string | no | Raw FIRMS `version`; validated value `2` |
| `processing_stream` | enum | no | Constant `standard` |
| `satellite_code` | string | no | Raw `satellite`; validated value `N` |
| `satellite_name` | string | no | Normalized `Suomi NPP` |
| `instrument` | string | no | Raw `instrument`; validated value `VIIRS` |
| `acquired_at_utc` | UTC datetime string | no | Strict combination of raw date/time |
| `latitude` | float64 degrees | no | WGS84 pixel-centre latitude, `[-90,90]` |
| `longitude` | float64 degrees | no | WGS84 pixel-centre longitude, `[-180,180]` |
| `brightness_i4_kelvin` | float32 | no | Raw `bright_ti4` |
| `brightness_i5_kelvin` | float32 | no | Raw `bright_ti5` |
| `scan_km` | float32 | no | Raw positive `scan` footprint dimension |
| `track_km` | float32 | no | Raw positive `track` footprint dimension |
| `frp_mw` | float32 | no | Raw non-negative FRP; zero is valid and flagged, not removed |
| `confidence_code` | enum `l`,`n`,`h` | no | Categorical algorithm class, never a probability |
| `confidence_label` | enum | no | `low`, `nominal`, or `high` mapping of the code |
| `daynight_code` | enum `D`,`N` | no | Day/night acquisition flag |
| `hotspot_type_code` | uint8 enum `0..3` | no | 0 presumed vegetation fire; 1 volcano; 2 other static land source; 3 offshore |
| `province_code` | string | yes | BIG `KDPPUM`; null unless assignment status is `assigned` |
| `province_name` | string | yes | BIG `WADMPR`; null unless assignment status is `assigned` |
| `geo_assignment_status` | enum | no | `assigned`, `unassigned`, `ambiguous_boundary`, or `multiple_match` |
| `geo_assignment_method` | enum | no | `big_full_resolution_point_intersection`, `big_generalized_feasibility_only`, or `none` |
| `boundary_source_id` | string | yes | BIG service item/layer identifier used for assignment |
| `ingestion_batch_id` | string | no | Foreign key to immutable batch provenance |
| `source_row_number` | uint64 | no | One-based data row position in the pinned source artifact |
| `source_record_hash` | lowercase hex string, 64 chars | no | SHA-256 over the exact ordered raw row lexemes |
| `quality_flags` | unique array of enum strings | no | Zero or more flags defined below |

The JSON Schema is the logical interchange definition. ClickHouse physical types and published view names remain D04 decisions.

## Identity and duplicate policy

1. Compute `source_record_hash = sha256(join("\x1f", raw values in the 15-column FIRMS header order))` without float reformatting.
2. Compute `observation_id = sha256(product_id + "\x1f" + source_record_hash)`.
3. Exact repeated rows in one product therefore collide. Preserve the first row in the canonical observation set and record duplicate groups/excess rows in its ingestion batch.
4. Do not perform fuzzy coordinate/time deduplication and do not deduplicate across products or platforms. A detection from another satellite is a separate observation.
5. If NASA reprocessing changes any raw field, the content identifier changes. Batch reconciliation must retain both batch provenance records and explicitly supersede the older published batch; it must not silently mutate history.

The pinned 2023 standard-processing file has zero exact or candidate-identity duplicate excess rows. The policy is still required for idempotency and future extracts.

## Geographic assignment policy

- Province code/name may be populated only for one unambiguous point-in-polygon match using the approved boundary source and method.
- A point on or within the declared tolerance of generalized geometry is `ambiguous_boundary` with null province until reviewed against approved full-resolution geometry.
- Zero matches are `unassigned`; multiple matches are `multiple_match`. Both keep null province fields.
- Never use nearest-province assignment for offshore, coastline, gap, or overlap cases.
- D02's 34 unassigned observations remain present in the pinned enriched artifact. D03's server-side full-resolution review is evidence only and does not rewrite them.
- The BIG service exposes no explicit redistribution license. Derived province identifiers and any boundary artifact must not be published externally until the Tech Lead confirms terms with BIG or selects a clearly reusable substitute.

Allowed quality flags are: `zero_frp`, `source_exact_duplicate`, `geo_unassigned`, `geo_ambiguous_boundary`, `geo_multiple_match`, `known_coverage_gap_context`, and `source_category_unexpected`. Flags are additive and never justify silently dropping a source observation.

## Batch provenance contract

Every observation references an immutable batch record containing at least:

| Field | Type / rule |
|---|---|
| `ingestion_batch_id` | Stable string identifier |
| `product_id` | Exact product above |
| `source_url` | Public NASA object URL, excluding credentials |
| `source_artifact_sha256` | SHA-256 of downloaded bytes |
| `source_bytes` | Non-negative integer |
| `retrieved_at_utc` | UTC timestamp |
| `provider_last_modified_utc` | Nullable UTC timestamp |
| `coverage_start_utc`, `coverage_end_utc` | Observation timestamp extents, not a completeness claim |
| `source_row_count`, `canonical_row_count` | Counts before/after exact deduplication |
| `duplicate_excess_rows`, `rejected_row_count` | Measured QA counts |
| `transform_version` | Versioned code/revision identifier |
| `provenance_manifest_path` | Repository-relative manifest path |

Pinned source evidence: 20,067,598 bytes, 253,388 rows, SHA-256 `2dba3b772b5a3a2cc0feed128af74637810021dd41dc34d584cb99b40411665a`, retrieved 2026-10-21T07:15:26.716826Z from NASA FIRMS.

## Daily coverage contract

Absence of detection rows must never be interpreted automatically as zero fire activity. Publish a product/day coverage record with:

- `date_utc`;
- `product_id`;
- `coverage_status`: `observations_present`, `known_satellite_gap`, `zero_detections_verified`, or `unknown`;
- `observation_count` (nullable for gaps/unknown);
- `evidence_url` and `note`.

For 2023-07-26 and 2023-07-27 use `known_satellite_gap`, `observation_count=null`, and the NASA LDOPE issue URL. Do not emit zero. `zero_detections_verified` requires independent coverage evidence and is not established anywhere in the pinned 2023 file.

## Supported range and query behavior

- Supported proposal range: 2023-01-01 through 2023-12-31 UTC for this single product.
- Explicit exclusions: 2023-07-26 and 2023-07-27 are unavailable due to a permanent S-NPP VIIRS data gap from approximately 2023-07-26T02:03:33Z through 2023-07-27T16:50:00Z.
- Aggregates spanning the gap may be returned only with a missing-coverage warning. A request confined to either missing date returns an unavailable-data response, not count zero.
- Requests outside calendar 2023 are unsupported until another source artifact and its coverage are separately validated.
- Province outputs remain provisional until BIG reuse terms and the production geometry/assignment policy are approved.

## Required Backend handoff decisions for D04

Tech Lead and Backend must approve the view names, ClickHouse types, exposure of source/boundary fields, maximum map-point response, coverage-warning representation, and contract fixtures. The Backend must treat nullable province and coverage status explicitly and must not infer completeness from date endpoints.

