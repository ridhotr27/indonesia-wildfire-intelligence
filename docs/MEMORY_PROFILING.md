# R01 component-level memory profile

**Scope:** Local observation only, 2026-11-25. No architecture or configuration changes. Q01's no-go and R01 `BACKLOG` remain unchanged. `UNKNOWN` means unmeasured, not zero.

## Measurement boundary

Backend probes used the existing macOS Python 3.13 virtual environment, a fresh process, one FastAPI TestClient, mock analytics, disabled semantic routing, extractive generation, and the real persisted hashing RAG index where noted. `resource.getrusage(...).ru_maxrss` is a **process peak RSS high-water mark**: it includes Python, native libraries, mapped pages, and allocator retention. It cannot report current idle RSS, proportional set size (PSS), per-module ownership, or container cgroup memory. Request increments below are conditional on their order and cannot be added to each other or to index disk size.

A separate `tracemalloc` process measured Python-tracked live allocations. Instrumentation changed RSS substantially, so its figures are a separate experiment and must not be subtracted from uninstrumented RSS to calculate native memory. Local Docker, Ollama, a configured VPS SSH target, and current-RSS/PSS tooling were unavailable. An attempted local Next.js production server was denied `listen` permission by this sandbox; its failed-start peak of 69.0 MiB is not a runtime measurement.

## Component breakdown

All values are MiB unless otherwise stated. A configured cap is a ceiling, not an observed allocation. “After request” is a peak high-water mark and does **not** prove whether memory stayed resident.

| Component | Configured limit | Idle | Startup peak | Representative request peak | Remains allocated afterward? | Can reduce or unload? | Method / environment |
|---|---:|---:|---:|---:|---|---|---|
| Frontend Next.js runtime | 512 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | Possible only with reviewed runtime-config design; current `/api/runtime-config` is dynamic | macOS start blocked by sandbox `listen EPERM`; failed-start 69.0 peak excluded |
| Python/FastAPI and imported dependencies | Backend container 1,024 shared | UNKNOWN | 117.24 after `wildfire_api.main` import; 117.71 after `create_app`; 118.80 after lifespan without RAG | 119.17 after `/metadata` in no-RAG run | UNKNOWN | Dependency/import review is possible; no saving proven | Fresh macOS process, uninstrumented peak RSS; baseline interpreter 7.33 |
| Intent classification and routing | Within backend 1,024 | UNKNOWN | Not isolated; semantic mode disabled in profiled run | UNKNOWN | UNKNOWN | Semantic index can remain disabled in production baseline | Code/config inspection only; no component allocation claim |
| LangGraph | Within backend 1,024 | UNKNOWN | Included in backend import/startup peak; not isolated | Included in chat peak below; not isolated | UNKNOWN | Bounded graph is required; no measured optimization | Same process as backend; do not add another RSS value |
| RAG document storage | Within backend 1,024 | UNKNOWN | Included in +11.74 RAG startup increment below | Included in RAG chat peak | UNKNOWN | Index is built offline; document/index ownership needs heap profiling | Persisted local index, macOS; documents and index share Qdrant structures |
| RAG embedding/index storage | Within backend 1,024 | UNKNOWN | 128.86 total after opening persisted hashing index, +11.74 relative to app construction | 130.25 total after NASA RAG chat, +1.39 after startup | UNKNOWN | Versioned index may be rebuilt or disabled; no unload saving measured | Fresh macOS process; 2.4 MiB **disk** directory size is not RAM |
| Embedding model | Within backend 1,024; optional Ollama 1,024 shared | UNKNOWN | Hashing path has no learned model weights; all-minilm load UNKNOWN | UNKNOWN | UNKNOWN | Ollama model residency may be bounded later; not tested | Production Compose defaults to hashing/semantic disabled; no Ollama process |
| Analytics service | Within backend 1,024 | UNKNOWN | Mock adapter included in backend baseline | 130.31 total after mock analytics chat, +0.06 after preceding RAG request | UNKNOWN | Live ClickHouse connection/query behavior unmeasured | macOS TestClient, mock analytics only |
| ClickHouse persistent server | 3,072 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | Tuning requires server profile and exact query parity | No local server or Linux cgroup measurement |
| DuckDB experimental file scan | No production cap/provider | UNKNOWN | UNKNOWN | 151.7 peak for one Python/NDJSON scan | UNKNOWN | Candidate only; persistence/serving untested | Prior macOS one-run 96,056-row D08 scan; not a running service |
| ClickHouse local experimental file scan | No server cap; production server cap 3,072 | UNKNOWN | UNKNOWN | 377.3 peak for same scan | UNKNOWN | Does not measure persistent server tuning | Prior macOS `clickhouse local` process, same D08 file |
| Ollama runtime | Optional container 1,024 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | One loaded model/parallel request configured; actual release behavior unknown | No Ollama executable/process or Docker daemon |
| LLM weights | Within optional Ollama 1,024 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | Small quantized candidate is planned; no loaded footprint measured | No model loaded; disk size is not resident RSS |
| LLM KV cache/inference buffers | Within optional Ollama 1,024 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | Context and concurrency can be bounded, but savings unmeasured | No inference run |
| Request serialization and map payloads | Within backend/frontend caps | UNKNOWN | UNKNOWN | 130.36 total after two-feature mock GeoJSON, +0.05 after prior analytics request; 1,417 response bytes | UNKNOWN | API already bounds GeoJSON features; full 500-feature peak unmeasured | macOS TestClient; RAG response 2,880 bytes, analytics 1,739 bytes |

The RAG chat question was “What does VIIRS confidence mean?” All three profiled responses returned HTTP 200. In the no-RAG run, `/health` was 89 bytes and `/metadata` 688 bytes; peak RSS moved from 118.80 after startup to 118.98 and 119.17 respectively. These small fixtures do not represent live data, concurrent users, or the maximum map payload.

## Incremental import and allocation observations

An independent `tracemalloc` run, with its own higher observer overhead, recorded: interpreter 9.33 RSS / 0 Python-tracked live; after FastAPI import 50.82 RSS / 16.86 Python live; after `qdrant_client` import 117.16 RSS / 44.74 Python live; after `wildfire_api.main` import 178.46 RSS / 73.00 Python live; after startup 180.55 RSS / 74.12 Python live; after metadata 181.02 RSS / 74.27 Python live. These sequential import deltas depend on import order and shared dependencies. They identify a **profiling target**, not attributable per-component memory. Native allocations and allocator overhead are included in RSS but not independently measured. PSS and container memory are UNKNOWN.

## Ranked bottlenecks and next measurement opportunities

1. **Unknown production workloads dominate risk:** persistent ClickHouse, Ollama weights/KV cache, portfolio/Caddy, and Linux container peaks have no observed idle or request profile. Their configured caps alone total 5,632 MiB for Wildfire with Ollama, before the portfolio and OS. Obtain isolated Linux cgroup and read-only VPS observations before setting lower limits.
2. **Backend dependency/import footprint:** uninstrumented import peak 117.24 MiB versus 7.33 MiB interpreter baseline; traced import order points to Qdrant and transitive dependencies. Profile current RSS/PSS and import timing on Linux, then assess whether lazy loading reduces *measured* steady-state memory without breaking startup readiness.
3. **Persistent hashing RAG:** opening the existing index raised process peak by 11.74 MiB in this one macOS run. Repeat with approved semantic/all-minilm index, representative corpus, and concurrent requests before deciding cache/index changes. No duplicate embedding-model load was observed in the hashing path.
4. **Frontend runtime:** startup and request memory remain UNKNOWN because the sandbox denied listening. Measure a production build in an isolated Linux container with dynamic runtime config and representative page/API traffic; a 50 MiB target is unverified.
5. **Analytics engine candidate:** prior DuckDB scan peak was 225.6 MiB lower than ClickHouse local, but neither idle server footprint nor full typed-query, coverage, release, privilege, and concurrency parity was measured. Continue only with persistent serving comparison; retain ClickHouse until then.
6. **Serialization and LangGraph:** tiny mock requests caused at most 1.50 MiB additional process high-water after RAG startup, with no independent allocation attribution. Profile maximum bounded GeoJSON, real analytics rows, NASA passages, concurrency, and model-backed generation before changing budgets.

## Reproduction and limits

Backend specialist ran fresh Python processes using `resource.getrusage(RUSAGE_SELF).ru_maxrss`; one with `tracemalloc` around import/startup, another using TestClient lifespan and RAG/analytics/map requests against the existing local index. The frontend probe invoked `node node_modules/next/dist/bin/next start -p 3107` and attempted localhost requests; startup failed with `listen EPERM`. Prior database figures are documented in `data/reports/R01_DUCKDB_CLICKHOUSE_EXPLORATORY_BENCHMARK.md`. No Docker/VPS/Ollama test was run. These results do not establish a safe 4 GiB deployment budget or change any release gate.
