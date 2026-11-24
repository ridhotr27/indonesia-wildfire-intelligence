# Local Production-Like End-to-End Validation

**Completed:** 2026-11-24 (Asia/Jakarta)

**Scope:** Isolated local Docker stack using verified VIIRS data
**Commit, push, or deployment:** None

## Outcome

The production-like path is working locally. A checksum-verified 2023 VIIRS S-NPP batch was loaded through the approved immutable ingestion pipeline into uniquely named disposable ClickHouse volumes. Metadata, analytics, bounded LangGraph routing, NASA-document RAG, the production Next.js dashboard, maps, charts, filters, chat citations, health checks, and restart persistence passed.

The earlier chat HTTP 503 was data-state related: a fresh database had no published analytics metadata. Loading the approved batch published the required metadata and resolved the 503 without weakening the backend's fail-closed behavior.

No source dataset, existing ClickHouse volume, existing vector index, release gate, API contract, LangGraph boundary, or application safety rule was modified or bypassed.

## Disposable environment

- Compose project: `iwi-e2e-20261123`
- Edge network: `iwi_e2e_edge_20261123` (`172.31.251.0/24`)
- Volumes: uniquely prefixed `iwi_e2e_*_20261123`
- Public validation bindings: `127.0.0.1:19080` and `127.0.0.1:19443` only
- Data source mounted read-only: `.local-batch/firms-v1-2dba3b772b5a3a2cc0fe-d05-ingestion-v1`
- Product: `VNP14IMG.002_SNPP_FIRMS_SP`; contract `1.0.0`; calendar 2023 UTC

## Data and integrity

| Check | Result | Evidence |
|---|---|---|
| Offline batch preflight | Pass | Checksum/identity, coverage, provinces, rejection, and row-accounting checks all true |
| Source identity | Pass | SHA-256 `2dba3b772b5a3a2cc0feed128af74637810021dd41dc34d584cb99b40411665a` |
| Approved pipeline load | Pass | Loader returned `status=loaded`; publication marker inserted last |
| Publication audit | Pass | 253,388 observations, 365 coverage days, 38 provinces, two known gap days, zero gap observations, zero invalid null geography, zero unpublished rows |
| Metadata publication | Pass | `/api/v1/metadata` returned verified status, 38 provinces, 2023 coverage, and known unavailable dates 2023-07-26/27 |
| Persistence | Pass | Data, metadata, and indexes survived service restart and a Docker Desktop daemon restart; all services recovered healthy |

An arbitrary small row slice was not created because that would fail the approved pipeline's checksum, complete-coverage, province, and immutable-publication gates. The approved 253,388-row batch was used read-only instead.

## Backend, analytics, and RAG

| Check | Result | Actual result |
|---|---|---|
| FastAPI health | Pass | HTTPS 200 |
| Two-province September summary | Pass | API total 14,178 |
| Independent ClickHouse parity | Pass | Riau (`14`) 687 + Central Kalimantan (`62`) 13,491 = 14,178 |
| LangGraph analytics route | Pass | Riau September answer 687, route `analytics`, fixed operation `hotspot_summary_v1`, zero LLM calls |
| RAG route and citation | Pass | HTTP 200, route `rag`, two approved passages retrieved, one citation accepted |
| Citation provenance | Pass | NASA FIRMS Active Fire Data Attributes URL and indexed chunk ID returned |
| Map API | Pass | 500 valid WGS84 features returned, correctly marked truncated and complete |
| Prior HTTP 503 | Resolved | Published batch metadata made analytics and chat available; fail-closed behavior remains intact for empty databases |
| Backend read boundary | Pass | Fixed typed operations and read-only analytics views retained; no arbitrary SQL or model-selected tool arguments introduced |

## Frontend and browser E2E

Headless Chromium exercised the actual production Next.js container through Caddy, not mocks. It verified:

- runtime configuration and metadata requests returned 200;
- verified-data badge rendered;
- initial dashboard, monthly chart, and MapLibre map rendered;
- selecting Riau and 2023-09-01 through 2023-09-30 displayed 687 detections;
- the filtered summary and GeoJSON requests returned 200;
- chat displayed the RAG answer, limitations, and a working NASA citation;
- the assistant loading indicator cleared after completion;
- no browser console errors or page errors occurred.

The existing frontend suite covers loading, typed HTTP failures, timeout/rate-limit/dependency messages, retry behavior, map source/basemap errors, chart/map contracts, citations, and unsafe trace rejection. A separate browser-level request-abort experiment did not match its expected alert within 30 seconds and is not counted as passed; automated component/API error-state coverage remains the evidence for those states.

## Security and dependency remediation

Initial `npm audit` reported 11 findings: 9 moderate and 2 critical. The critical findings were in dev-only Vitest/Tinypool; deployed Next.js also had seven framework advisories.

Minimal remediation applied:

- Next.js `16.4.2` → `16.4.5` (patched production framework)
- Vitest `3.2.4` → `4.1.12` (first tested fixed Vitest 4 patch line)
- non-breaking transitive `npm audit fix` updates for TypeScript ESLint/minimatch tooling

Final `npm audit`: **0 vulnerabilities** across 664 dependencies. No `--force`, dependency override, lint-rule disablement, or unrelated package was added.

Network exposure remained bounded: ClickHouse has no published port; backend and frontend expose only container ports; Caddy validation ports bind only to loopback. Runtime credentials were safe disposable values and were not baked into images or browser output.

## Configuration defects fixed

1. ClickHouse startup PID ceiling: increased the bounded limit from 512 to 1024 because ClickHouse 25.8 creates a 512-thread startup pool and aborted at the previous ceiling.
2. Loader mount identity: Compose previously mounted a verified batch directory as generic `/app/ingest`, causing the loader's immutable directory-name identity check to reject it. Compose now mounts and addresses it as `/app/ingest/${DATA_BATCH_ID}`. `.env` templates document `DATA_BATCH_ID`.
3. Frontend dependency advisories: patched versions and lockfile updates described above.

## Tests and builds actually run

| Validation | Result |
|---|---|
| Data full suite | 80 passed |
| Backend focused API/LangGraph suite | 71 passed |
| Backend full suite, sequential rerun | 514 passed, 1 skipped |
| Backend Ruff | Pass |
| Frontend tests | 16 files, 89 tests passed |
| Frontend lint | Pass |
| Frontend typecheck | Pass |
| Frontend host production build | Pass, Next.js 16.4.5 |
| Frontend Docker production build | Pass; `npm ci` found 0 vulnerabilities |
| Compose/Caddy validation | Pass |
| Container health | ClickHouse, backend, frontend, and Caddy healthy |
| Patched-image browser E2E | Pass |

The first broad backend run was executed concurrently with the data suite and Docker build and had one 100 ms timeout-sensitive combined-recovery test fail under contention. That exact test passed immediately when rerun alone, and the entire backend suite then passed sequentially. No timeout or safety limit was relaxed.

## Remaining blockers and risks

- This validates the approved 2023 contract, not the larger three-year v1.1 release. No D08 release gate was changed.
- The browser run used the locally installed Chromium/Playwright version and a disposable locally trusted Caddy certificate; cross-browser/device and manual screen-reader checks remain open release evidence.
- Map basemap availability still depends on the external OpenStreetMap tile service and its production usage policy.
- The existing LangGraph third-party deprecation warning about `allowed_objects` remains; it did not affect results but should be handled before the upstream default changes.
- Q01's recorded no-go recommendation and lack of production release approval remain authoritative.

All evidence above is local validation evidence only and does not imply production approval or deployment.

## 2023–2025 approved-release extension — 2026-11-24

The same production-like path was extended to the checksum-bound, locally authorized
D08 release `d08-viirs-snpp-2023-2025-v1`. The original batch directories and release
manifests were mounted read-only. Only fresh `iwi_d08_*_20261124` volumes and the
isolated `iwi-d08-20261124` Compose project were mutated.

### Release publication and integrity

| Check | Result | Actual evidence |
|---|---|---|
| Offline release verification | Pass | Authorization checksum, four required approval roles, three batch manifest hashes, artifact byte counts/checksums, product, years, and contract identities verified without database contact |
| Hidden load | Pass after configuration fix | All three batches loaded while invisible to serving views; activation occurred only after hidden reconciliation |
| Activation | Pass | Activation sequence 1 selected `d08-viirs-snpp-2023-2025-v1` |
| Release audit | Pass | 453,630 observations; 1,096 unique coverage rows; 38 provinces; three release mappings; zero duplicate observation IDs |
| Coverage semantics | Pass | Two 2023 known-gap dates and 21 unknown dates retained as unavailable/unknown, never converted to zero |
| Contract visibility | Pass | Serving views expose only contract `1.1.0` and the active release |

Independent serving-view counts matched the authorized release exactly:

| Year | Expected | Actual |
|---|---:|---:|
| 2023 | 253,388 | 253,388 |
| 2024 | 104,186 | 104,186 |
| 2025 | 96,056 | 96,056 |
| **Total** | **453,630** | **453,630** |

### Analytics and LangGraph parity

Riau was used as the independent cross-year reference case. Direct ClickHouse counts,
the typed year-comparison endpoint, the bounded LangGraph analytics operation, and the
browser UI all agreed:

| Year | Direct ClickHouse | API/chat/UI |
|---|---:|---:|
| 2023 | 3,327 | 3,327 |
| 2024 | 2,666 | 2,666 |
| 2025 | 4,053 | 4,053 |

`POST /api/v1/hotspots/year-comparison` returned HTTP 200 with operation
`hotspot_year_comparison_v1`. The natural-language request “Compare Riau hotspot
detections in 2023, 2024, and 2025” also returned HTTP 200, route `analytics`, one
allowlisted read-only tool call, and zero LLM calls. It correctly declined to calculate
a percentage or directional comparison because one or more years contain unknown or
unavailable dates.

### Targeted browser validation

Headless Chromium exercised the production Next.js image through Caddy and verified:

- metadata coverage spans 2023-01-01 through 2025-12-31;
- the Riau year filter displays 3,327, 2,666, and 4,053 for 2023, 2024, and 2025;
- each selection loads its backend-supplied monthly chart and verified MapLibre data;
- incomplete-coverage warnings remain visible for affected years;
- chat renders the three year-comparison values and the unknown-date limitation;
- all targeted metadata, summary, GeoJSON, and chat requests returned HTTP 200;
- the loading indicator cleared, with no console or page errors.

### Configuration defect found and fixed

The approved D08 loader serializes its largest annual NDJSON insert into a temporary
file. The production Compose ingestion job allowed only a 64 MiB `/tmp`, so the first
hidden load failed closed with `ENOSPC` before activation. The disposable partial
volume was removed, and only the `data-loader` tmpfs ceiling was raised to a bounded
512 MiB. A clean hidden load, activation, and audit then passed. The application
containers' tmpfs settings were unchanged.

### Targeted regression results

- Data D05/D08 modules: **18 passed**.
- Backend multi-year/repository/API tests: **35 passed**; the existing third-party
  LangGraph `allowed_objects` deprecation warning remains.
- Frontend year-comparison/client/filter tests: **4 files, 16 tests passed**.
- Frontend ESLint and TypeScript: **passed**.
- Compose rendering, `git diff --check`, and all four container health checks: **passed**.
- Unrelated full suites and image builds were not repeated because the application
  images were unchanged from the immediately preceding successful validation.

This extension validates the existing approved local-development release only. It does
not change Q01's no-go recommendation, approve production release, or authorize public
deployment.
