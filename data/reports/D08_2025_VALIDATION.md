# D08 — 2025 Validation

**Status:** Technical validation complete; D08 remains `IN_PROGRESS` pending contract approval and live publication verification.  
**Observed:** 2026-11-21 · **Classification:** Official source artifact, not ingested

## Results

- Source: `https://firms.modaps.eosdis.nasa.gov/data/country/viirs-snpp_2025_Indonesia.csv`
- Product: `VNP14IMG.002_SNPP_FIRMS_SP` (`N` / `VIIRS` / standard-processing version `2` on every row).
- Size: 7,584,099 bytes; SHA-256: `11abffff52dedfe985a8f03c59b8ebff55a903bd0de07d4897f76d734788d811`.
- Provider metadata: Last-Modified `2026-10-10T13:22:43Z`; ETag `ab09131e698b1459baddebd2cc093533` (not treated as a checksum).
- Shape: 96,056 rows, exact approved 15-column schema.
- Coverage: 2025-01-01 through 2025-12-31; rows on 364/365 dates. `2025-11-12` has no rows and remains `unknown` with a null count, not zero.
- Quality: zero blanks, invalid numerics/dates/times/timestamps/coordinates, negative FRP, exact duplicates, identity duplicates, or strict parser failures.
- Province mapping with the pinned 38-province geometry: 95,597 assigned, 456 unassigned, 3 multiple-match; every province has observations. No nearest-province coercion was applied.

Machine evidence: `data/reports/d08_2025_validation_profile.json`.

## Compatibility

The source schema, product identity, enums, units, coordinate/FRP constraints, exact-row identity, and province policy match 2023–2024. Across the three artifacts there are 453,630 source rows and 1,096 calendar coverage rows: two documented 2023 known gaps, twenty 2024 unknown dates, and one 2025 unknown date. Publication requires the proposed v1.1 contract and an atomic active-release strategy so mixed contract versions or partially loaded years cannot leak through current views.

No ClickHouse load/migration, approved-contract edit, backend/frontend mutation, or deployment occurred.
