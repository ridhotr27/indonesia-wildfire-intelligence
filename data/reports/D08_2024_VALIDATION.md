# D08 — 2024 Validation

**Status:** `DONE` (Tech Lead approved 2026-11-21) · **Observed:** 2026-11-21 · **Contract:** existing v1.0.0 retained; no publication approval

## Source and result

- NASA FIRMS public country artifact: `https://firms.modaps.eosdis.nasa.gov/data/country/viirs-snpp_2024_Indonesia.csv`
- Product: VIIRS S-NPP standard processing, `VNP14IMG.002_SNPP_FIRMS_SP` (`N` / `VIIRS` / version `2` on every row).
- Size: 8,238,988 bytes; SHA-256: `23be16b48fb6ac3a21fd2130e66149d305af71c62bbb39e76a6a0632a9dd69bd`.
- Provider metadata: Last-Modified `2025-06-24T16:59:24Z`; ETag `a6258b2addb85f83115511f8f52a0996` (not treated as a checksum).
- 104,186 rows and 15 columns; exact approved source schema. Zero blanks, invalid numerics/timestamps/coordinates, negative FRP, exact duplicates, identity duplicates, or strict parser failures.
- Coverage is 2024-01-01 through 2024-12-31 with rows on 346 of 366 dates. Twenty no-row dates remain `unknown`, not zero or known satellite gaps: May 30–June 3; July 10–15; July 24–28; September 26; November 3–5.
- Province mapping using the pinned 38-province OSM geometry: 103,697 assigned, 479 unassigned, 10 multiple-match; every province has observations. Non-unique assignments remain null and are not coerced.

## 2023 compatibility and implementation

The 15 source fields, types, product identity, confidence/day-night/type enums, coordinate ranges, row identity, and province-assignment policy remain compatible with v1.0.0. Differences are temporal: 2024 is a leap year, has 20 unclassified no-row dates, 104,186 rows versus 253,388 in 2023, and no zero-FRP rows versus eight in 2023.

The existing ingestion now accepts an explicit 2023–2025 source year, generates 365/366 year-specific coverage rows, retains only the documented 2023 gaps, and rejects cross-year rows. Default 2023 behavior and its transform/batch identity remain unchanged. Candidate 2024–2025 manifests use a separate transform version and are explicitly rejected by the ClickHouse loader pending contract approval.

## Verification and readiness

- Full-file profile: `data/scripts/profile_firms_annual_candidate.py ... --year 2024` — completed; machine evidence in `data/reports/d08_2024_validation_profile.json`.
- Focused tests: `python3 -m unittest data.tests.test_d05_ingestion data.tests.test_d06_clickhouse.D06BatchValidationTests` — **21 passed in 14.548s**.
- No ClickHouse ingestion/migration, production mutation, 2025 full download, or contract publication occurred.

**Readiness:** The Tech Lead accepted the 20 no-row dates as `unknown` with null counts. Source validation and year-aware processing are complete; ClickHouse ingestion remains unauthorized until an additive contract update receives Tech Lead/BE approval.
