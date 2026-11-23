# D08 contract and publication gate review

**Decision:** Approved on re-review 2026-11-22; supersedes the initial changes-required decision below  
**Scope:** Local-development publication review only

## Accepted evidence

- All three artifacts are the same `VNP14IMG.002_SNPP_FIRMS_SP` product and approved 15-column schema.
- Measured rows reconcile to 453,630: 253,388 (2023), 104,186 (2024), and 96,056 (2025), with zero per-artifact exact duplicates or strict validation failures.
- Coverage semantics are correct: two documented 2023 gaps, twenty 2024 unknown dates, and one 2025 unknown date; none is converted to zero.
- Province policy and pinned geometry are unchanged. Expected totals are 451,876 assigned, 1,731 unassigned, and 23 multiple-match across 38 provinces.
- API behavior proposed for single-year filters is backward-compatible in shape and meaning.

## Blocking findings

1. The v1.1 active-release gate exists only as prose. No migration, release pointer, hidden-load path, atomic activation, rollback query, or focused failure test exists.
2. `ingest_firms_v1.py` still writes row-level `contract_version=1.0.0`; D06 physical constraints accept only `1.0.0`. Therefore the proposed requirement that every active row report `1.1.0` cannot currently be met.
3. The ClickHouse loader correctly rejects 2024–2025 candidate manifests. No reviewed authorization artifact binds the three source checksums, three batch IDs, expected counts, and one release ID.
4. Reusing current views without an active-release filter could expose partial years or duplicate a reprocessed 2023 batch. The four serving interfaces cannot be switched safely until one atomic release selector is implemented and tested.
5. The API proposal has no versioned OpenAPI/models/fixtures. `hotspot_year_comparison_v1`, its exact request/result types, bounds, query, trace semantics, and BE/FE compatibility review are incomplete.
6. Because no approved active release can be loaded, live ClickHouse/API/dashboard/map/chat verification would test an unauthorized or partial state and cannot satisfy D08.

## Smallest safe next actions

1. Implement an isolated v1.1 physical model plus one atomic active-release pointer and rollback insertion; keep current v1.0 serving state as rollback.
2. Parameterize candidate generation for contract v1.1 and create a checksum-pinned three-batch release manifest. Keep it unauthorized until focused migration/loader/crash/rollback tests pass.
3. Produce versioned API/OpenAPI/types/fixtures for multi-year metadata and the typed year comparison; obtain BE and FE reviews.
4. Re-run this gate. Only then may the Tech Lead approve local migration/load and live verification.

D08 remains `IN_PROGRESS`. No ClickHouse process was started, no migration/load ran, and no contract was approved.

## Superseding re-review

All six blocking findings were resolved: v1.1 physical support, hidden loading, an append-only atomic active-release pointer, tested rollback, checksum-bound three-batch authorization, active-release-filtered serving views, and versioned API/OpenAPI/types/fixtures with BE/FE review are implemented. The authorized local release reconciled exactly and live API, dashboard, map, charts, and chatbot verification passed. Tech Lead approves the local-development publication; no production deployment is authorized.
