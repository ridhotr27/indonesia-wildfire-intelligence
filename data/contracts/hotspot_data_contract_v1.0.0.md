# DE-to-BE hotspot data contract v1.0.0

**Status:** Approved under D04 by the Tech Lead on 2026-10-22; logical contract only, not yet deployed  
**Contract version:** `1.0.0`  
**Schema:** `hotspot_data_contract_v1.0.0.schema.json`  
**Fixture:** `fixtures/hotspot_data_contract_v1.0.0.fixture.json`

This contract is the approved stable logical interface from Data Engineering to the
read-only Backend analytics layer. It incorporates the approved G1 baseline and D04
decision but does not approve G2, production ingestion, or physical ClickHouse DDL.
D05 and D06 will implement the pipeline and views only after their gates are satisfied.

Every observation is a NASA satellite active-fire/thermal-anomaly **detection**. It is
not a confirmed wildfire incident or a burned-area measurement.

## 1. Frozen dataset identity

| Property | Contract value |
|---|---|
| Product ID | `VNP14IMG.002_SNPP_FIRMS_SP` |
| NASA product | `VNP14IMG.002`, VIIRS/NPP Active Fires 6-Min L2 Swath 375 m V002 |
| FIRMS stream | VIIRS S-NPP standard processing, raw `version=2` |
| Supported dates | 2023-01-01 through 2023-12-31, UTC and inclusive |
| Known unavailable dates | 2023-07-26 and 2023-07-27 |
| Province geometry | OSM-derived snapshot `2026-10-10b`, pinned commit `c4d208a03a71553a1082f960ebdaa88c1d8e9389` |
| Boundary license | ODbL 1.0; attribution `© OpenStreetMap contributors` and applicable share-alike obligations must accompany redistribution |
| CRS | WGS84 / OGC:CRS84 longitude-latitude |

No other product, platform, latency stream, collection, year, or boundary snapshot is
compatible with this version. Adding one requires feasibility evidence and at least a
minor contract version; changing existing meaning requires a major version.

## 2. Published read-only interfaces

D06 will materialize these exact logical interfaces. D04 defines their names and
columns, not their storage engine, partitioning, or production grants.

| Interface | Grain | Purpose |
|---|---|---|
| `analytics_hotspot_observations_v1` | one canonical exact-deduplicated detection | Bounded point retrieval and approved aggregations |
| `analytics_daily_coverage_v1` | product and UTC calendar date | Distinguish observations, known gaps, verified zero, and unknown coverage |
| `analytics_provinces_v1` | one canonical province | Filter metadata and boundary provenance; geometry is not exposed to BE |
| `analytics_ingestion_batches_v1` | one immutable source batch | Dataset provenance, checksum, counts, and publication state |

The Backend serving identity receives `SELECT` only on these four interfaces. It must
not receive `INSERT`, `ALTER`, `CREATE`, `DROP`, or direct access to DE raw/staging
tables. D06 must test these grants on a fresh ClickHouse instance.

### `analytics_hotspot_observations_v1`

| Column | ClickHouse-compatible logical type | Nullable | Rule |
|---|---|---:|---|
| `contract_version` | `String` | no | Constant `1.0.0` |
| `observation_id` | `FixedString(64)` | no | Lowercase SHA-256 identity |
| `product_id` | `LowCardinality(String)` | no | Frozen product ID above |
| `source_product` | `LowCardinality(String)` | no | `VNP14IMG` |
| `collection_version` | `LowCardinality(String)` | no | `2` |
| `processing_stream` | `LowCardinality(String)` | no | `standard` |
| `satellite_code` | `LowCardinality(String)` | no | `N` |
| `satellite_name` | `LowCardinality(String)` | no | `Suomi NPP` |
| `instrument` | `LowCardinality(String)` | no | `VIIRS` |
| `acquired_at_utc` | `DateTime64(0, 'UTC')` | no | Strict date plus zero-padded time |
| `latitude` | `Float64` | no | WGS84, -90 through 90 |
| `longitude` | `Float64` | no | WGS84, -180 through 180 |
| `brightness_i4_kelvin` | `Float32` | no | Raw `bright_ti4` |
| `brightness_i5_kelvin` | `Float32` | no | Raw `bright_ti5` |
| `scan_km` | `Float32` | no | Positive raw footprint dimension |
| `track_km` | `Float32` | no | Positive raw footprint dimension |
| `frp_mw` | `Float32` | no | Non-negative; zero is retained and flagged |
| `confidence_code` | `LowCardinality(String)` | no | `l`, `n`, or `h`; never a probability |
| `confidence_label` | `LowCardinality(String)` | no | `low`, `nominal`, or `high` |
| `daynight_code` | `LowCardinality(String)` | no | `D` or `N` |
| `hotspot_type_code` | `UInt8` | no | Source category 0 through 3 |
| `province_code` | `Nullable(FixedString(2))` | yes | Set only for one unambiguous match |
| `province_name` | `Nullable(String)` | yes | Canonical Indonesian display name |
| `geo_assignment_status` | `LowCardinality(String)` | no | `assigned`, `unassigned`, or `multiple_match` |
| `geo_assignment_method` | `LowCardinality(String)` | no | `osm_snapshot_point_intersection` or `none` |
| `boundary_source_id` | `Nullable(String)` | yes | `osm-idn-adm1-2026-10-10b` when assigned |
| `ingestion_batch_id` | `String` | no | Immutable batch foreign key |
| `source_row_number` | `UInt64` | no | One-based data row in the source artifact |
| `source_record_hash` | `FixedString(64)` | no | Exact raw-row SHA-256 |
| `quality_flags` | `Array(LowCardinality(String))` | no | Unique, sorted allowed flags |

The approved OSM snapshot is used directly at its validated precision. No tolerance
classification or nearest-province coercion is applied: exactly one point-in-polygon
match is `assigned`; zero is `unassigned`; more than one is `multiple_match`.
Non-assigned rows retain null province and boundary fields. The older D03 proposal's
BIG-specific methods and `ambiguous_boundary` state are intentionally not part of
v1.0.0.

Identity remains `source_record_hash = sha256(join("\x1f", the exact 15 FIRMS raw
lexemes in source-header order))`, then `observation_id = sha256(product_id + "\x1f"
+ source_record_hash)`. Keep the first exact duplicate per product/batch, record the
excess in batch QA, and do no fuzzy or cross-product deduplication.

Allowed quality flags are `zero_frp`, `source_exact_duplicate`, `geo_unassigned`,
`geo_multiple_match`, `known_coverage_gap_context`, and
`source_category_unexpected`. A flag never silently removes an observation.

### `analytics_daily_coverage_v1`

| Column | Logical type | Nullable | Rule |
|---|---|---:|---|
| `contract_version` | `String` | no | `1.0.0` |
| `product_id` | `LowCardinality(String)` | no | Frozen product ID |
| `date_utc` | `Date` | no | Every date in the supported range |
| `coverage_status` | `LowCardinality(String)` | no | Enum below |
| `observation_count` | `Nullable(UInt64)` | yes | Non-null only for present or independently verified zero coverage |
| `evidence_url` | `Nullable(String)` | yes | Required for a known gap or verified zero |
| `note` | `Nullable(String)` | yes | Human-readable evidence context |
| `ingestion_batch_id` | `Nullable(String)` | yes | Published batch when applicable |

Coverage states:

- `observations_present`: one or more rows exist; count must be positive.
- `known_satellite_gap`: coverage is unavailable; count must be null and evidence is required.
- `zero_detections_verified`: count is zero only with independent coverage evidence. No
  2023 date currently receives this status merely because a country file has no row.
- `unknown`: completeness is unresolved; count must be null.

The two known gaps use `known_satellite_gap`, null counts, and NASA LDOPE issue 480:
`https://landweb.modaps.eosdis.nasa.gov/displayissue?id=480`.

Aggregates must left-join all requested dates to this interface. A range containing a
gap may return the sum of available detections only if it also returns
`is_complete=false`, the missing dates/statuses, and a warning. A request wholly
inside unavailable dates returns unavailable coverage and no numeric total. Neither
DE nor BE may manufacture a zero by filling null or missing coverage rows.

### `analytics_provinces_v1`

Contains all 38 unique two-digit canonical codes and names, reversible OSM source
codes/names, `boundary_source_id`, snapshot, commit, CRS, source/canonical checksums,
license name/URL, required attribution, and `is_supported=true`. Province filters use
canonical codes. Geometry stays DE-owned; BE receives detection coordinates from the
observation view and attribution metadata from this interface.

### `analytics_ingestion_batches_v1`

Contains the immutable batch ID, product ID, credential-free source URL, source SHA-256
and bytes, retrieval/provider timestamps, observed timestamp extents, source/canonical
row counts, duplicate/rejected counts, transform version, manifest path, publication
status, and publication timestamp. `published` is the only status visible through the
serving view; D05 must prevent partial batches from entering it.

## 3. Bounded map interface

The BE repository may select only assigned rows for a requested province and date
range. Results are ordered by `(acquired_at_utc, observation_id)` for stable paging or
truncation. The request default is 500 points and the hard cap is 5,000 points. The
query fetches at most `effective_limit + 1`; the extra row determines `truncated` and
is never returned. Allowed map properties are `observation_id`, `acquired_at_utc`,
`product_id`, `province_code`, `confidence_code`, `frp_mw`, and `daynight_code`.
Source-row numbers, hashes, batch internals, and boundary geometry are not browser map
properties. GeoJSON coordinates remain `[longitude, latitude]`.

## 4. Fixture classification and measured values

The fixture is explicitly `synthetic_contract_example`; its values are invented only
to exercise types and edge cases and must never be displayed as NASA observations or
used as evaluation evidence. It covers assigned and unassigned detections, zero FRP,
the two mandatory coverage gaps, one present day, two provinces, batch provenance,
and expected gap-aware aggregation behavior.

Measured D03B evidence remains separate: the real five-day sample has 15,804 rows,
15,770 assigned, 34 unassigned, and zero multiple matches under the accepted OSM
boundary. Those counts are evidence, not contract-fixture contents.

## 5. Compatibility policy

- Contract versions follow semantic versioning.
- Patch: clarification or additive evidence that changes no field, type, nullability,
  enum, view name, or behavior.
- Minor: backward-compatible optional field/interface or a separately validated
  additional product/window. Consumers must ignore unknown optional fields.
- Major: removal/rename, stricter input, changed type/nullability/enum meaning, view
  rename, product substitution, identity change, or changed coverage/geography rules.
- Approved versions are immutable. A change is proposed in a new version and requires
  DE/BE review plus Tech Lead approval. Supporting at least one migration interval is
  required before retiring a published major version.
- `contract_version` is present in every interface. BE must reject an unsupported
  major version instead of guessing compatibility.

## 6. Required review and follow-up

DE validation covers schema syntax, fixture semantics, type/precision boundaries,
known gaps, null geography, province crosswalk consistency, map caps, and deterministic
fixture aggregation. D04 consumer tests and Tech Lead approval were recorded on
2026-10-22, and approved A01 carries the coverage warning/null-total semantics to the
public API. D06 owns physical ClickHouse DDL and grant tests; none are claimed here.
