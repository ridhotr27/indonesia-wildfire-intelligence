# D08 Initial Source Validation

**Observed:** 2026-11-21 (Asia/Jakarta)  
**Scope:** Read-only NASA headers and bounded byte ranges; repository/config audit. No annual artifact was retained, profiled in full, or ingested.

## Result

NASA FIRMS exposes public Indonesia annual files for VIIRS S-NPP 2024 and 2025:

| Year | URL suffix | HTTP | Bytes | Last-Modified (UTC) | ETag | Bounded observations |
|---|---|---:|---:|---|---|---|
| 2024 | `viirs-snpp_2024_Indonesia.csv` | 200 | 8,238,988 | 2025-06-24 16:59:24 | `a6258b2addb85f83115511f8f52a0996` | First/last sampled rows are 2024-01-01/2024-12-31 |
| 2025 | `viirs-snpp_2025_Indonesia.csv` | 200 | 7,584,099 | 2026-10-10 13:22:43 | `ab09131e698b1459baddebd2cc093533` | First/last sampled rows are 2025-01-01/2025-12-31 |

Both endpoints honored byte ranges (`206` with correct `Content-Range`). Their headers exactly match the approved 2023 15-column source schema:

`latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight,type`

Sampled boundary rows use satellite `N`, instrument `VIIRS`, and version `2`, matching the existing `VNP14IMG.002_SNPP_FIRMS_SP` parser assumptions. Coordinates and field values in those rows pass the current parser's basic ranges. This establishes endpoint availability, apparent product/schema compatibility, and inclusive annual date bounds only. It does **not** establish every date's coverage, full geographic/province coverage, duplicates, nulls, value distributions, checksums, or full-file product consistency.

For comparison, the 2023 endpoint still returns 200, 20,067,598 bytes, Last-Modified 2025-06-24 17:07:37 UTC, and ETag `b8099243f9f067d687d59927e4fb04f3`; the approved local SHA-256 remains the authoritative 2023 identity. ETags are recorded as HTTP metadata, not asserted to be checksums.

## Compatibility blockers and required changes

1. `ingest_firms_v1.py` rejects dates outside 2023, generates exactly 365 coverage rows, and hard-codes only the 2023-07-26/27 gaps. It needs explicit per-batch year bounds and an evidence-backed gap policy; missing dates must remain `unknown`, never zero.
2. Contract v1.0.0 documents calendar 2023 only. The observation shape/product ID can remain compatible, but supported-date metadata and chatbot/API behavior need an additive, reviewed contract revision before publication.
3. The ClickHouse observation table is already month-partitioned and product-compatible. Its 2023 gap constraint is harmless for later dates, but year-specific coverage and multi-batch publication/reconciliation must be verified before loading.
4. Exact source checksums, row/date counts, duplicates, schema distributions, coordinate extrema, and 38-province assigned/unassigned/multiple-match counts require the full immutable artifacts and are intentionally blocked until download approval.

## ClickHouse target

The DE loader defaults to `http://127.0.0.1:8123`, database `wildfire`; the backend example also targets `127.0.0.1`. `CLICKHOUSE_URL` is currently unset, so no remote target is selected. A read-only probe found no server listening on local port 8123. Therefore the configured target is local/development, but no running database identity or contents were verified.

## Smallest safe ingestion plan

1. Obtain Tech Lead approval to download one immutable annual file at a time, beginning with 2024; record URL, retrieval time, headers, byte count, and SHA-256.
2. Run a read-only full-file profiler before transformation: exact header/product constants, UTC date matrix, duplicates, null/type/range checks, coordinates, and province assignment reconciliation.
3. Add year parameters to the existing parser/coverage generator while retaining the product ID, row identity, boundary snapshot, manifests, quarantine, and idempotency controls. Keep 2023 behavior frozen.
4. Review an additive contract/metadata revision with BE; do not change published views unless required.
5. Start local ClickHouse, verify `hostName()`, `currentDatabase()`, version, and write/read identities; migrate only if the reviewed plan requires it.
6. Load 2024 as a new immutable batch into local development, reconcile source/canonical/daily/province counts and published queries, then repeat independently for 2025. Never combine files or publish both in one unverified step.

No ingestion, schema migration, runtime change, or tests were performed.
