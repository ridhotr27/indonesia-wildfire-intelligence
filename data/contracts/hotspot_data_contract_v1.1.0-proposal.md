# DE-to-BE hotspot data contract v1.1.0

**Status:** Approved for local development on 2026-11-22  
**Base contract:** Backward-compatible additive extension of approved v1.0.0

## Additive change

Keep the v1.0.0 product, fields, types, units, identity, exact deduplication, province geometry/policy, view names, read-only grants, map limits, and hotspot-detection caveat unchanged. Extend only the supported UTC window and release provenance:

| Year | Source rows | Present dates | Coverage issues | Assignment |
|---|---:|---:|---|---|
| 2023 | 253,388 | 363/365 | `2023-07-26`, `2023-07-27`: `known_satellite_gap` | 252,582 assigned; 796 unassigned; 10 multiple-match |
| 2024 | 104,186 | 346/366 | 20 no-row dates: `unknown` | 103,697 assigned; 479 unassigned; 10 multiple-match |
| 2025 | 96,056 | 364/365 | `2025-11-12`: `unknown` | 95,597 assigned; 456 unassigned; 3 multiple-match |

Total source/canonical rows are 453,630; all three annual files have zero exact duplicates. Unknown dates have `observation_count=null`, no evidence URL, and must never become zero. The 2024 dates are May 30–June 3, July 10–15, July 24–28, September 26, and November 3–5.

## Publication and compatibility requirements

1. Produce three immutable v1.1 candidate batches from the pinned annual SHA-256 artifacts, including a freshly reproduced 2023 batch; observation IDs remain stable because identity semantics do not change.
2. Add a DE-owned active dataset-release gate. Load and reconcile all three batches while hidden, then atomically activate one release containing exactly 2023–2025. Existing v1.0 physical rows may remain for rollback but must not be duplicated in serving views.
3. Serving views keep their current names and columns and expose only the active release. Every visible row reports contract version `1.1.0`; mixed visible v1.0/v1.1 rows are prohibited.
4. Coverage must contain exactly 1,096 unique product/date rows and reconcile every `observations_present` count to visible observations. Expected issue states are two known gaps plus 21 unknown dates.
5. Published observations must reconcile to 453,630 rows: 451,876 assigned, 1,731 unassigned, and 23 multiple-match. Preserve all 38 provinces and existing boundary checksum/attribution.
6. Backend remains read-only. Candidate manifests remain `clickhouse_ingestion_authorized=false` until approval; activation requires exact checksums/counts, idempotent reruns, rollback evidence, and BE parity queries.

## Review decision

Tech Lead, DE, and BE approved v1.1 as a backward-compatible minor expansion. The authorized local-development release was activated only after compatible-minor parsing, metadata aggregation, coverage warnings, unchanged query/view fields, exact reconciliation, and rollback passed. This approval does not authorize production deployment.
