# R01 low-memory feasibility evidence

**Decision:** NO-GO for private deployment with local Ollama on the existing 4 GiB host. This is an evidence decision, not a claim that the target is impossible. Q01's no-go and R01's `BACKLOG` remain unchanged.

## Measurements and limits

| Component | Before / existing evidence | After / new local evidence | Production implication |
|---|---|---|---|
| Backend with hashing RAG | Not previously measured in this task | macOS Python 3.13 process peak RSS: 117.3 MiB after app creation, 128.3 MiB after persistent index startup, using mock analytics and extractive generation | No Linux/container request-load peak; 1 GiB Compose cap is a ceiling, not usage. No measured bottleneck justified a code change. |
| ClickHouse versus DuckDB | ClickHouse production cap 3 GiB; no running local ClickHouse server | Exploratory scan on actual 2025 D08 96,056-row NDJSON: ClickHouse local 1.881 s / 377.3 MiB peak RSS; DuckDB Python 0.569 s / 151.7 MiB, top-five rank parity | One macOS file scan does not establish persistent serving, full query, coverage, release, concurrency, or privilege parity. See `data/reports/R01_DUCKDB_CLICKHOUSE_EXPLORATORY_BENCHMARK.md`. No DuckDB provider adopted. |
| Frontend | 512 MiB Compose cap | Not measured | Dynamic `/api/runtime-config` route reads environment at request time; a static export needs a separately reviewed configuration/contract design. A 50 MiB target is unproven. |
| Ollama Qwen3 0.6B | 1 GiB optional Compose cap; no baseline | Not measured: Ollama executable absent locally | Model latency, quality, loaded RSS, context and concurrency budget unknown. Existing `local_grounded` profile pins `qwen2.5:1.5b` and `all-minilm`; a model switch needs BE validation. |
| Complete stack and portfolio | Existing Compose caps: 4.5 GiB without Ollama, 5.5 GiB with it, before OS/portfolio/Caddy | Not measured: local Docker Desktop daemon/socket unavailable, host is macOS, VPS SSH target unavailable | No constrained Linux benchmark, swap/OOM data, or portfolio isolation evidence. |

There is **no defensible before/after stack reduction** or minimum viable VPS RAM estimate from these measurements. The 400 MiB portfolio/Caddy, 450 MiB OS, 50 MiB frontend, 850 MiB API/database/RAG, and 1,100 MiB Ollama values are user targets, not observed usage. Even their 2,850 MiB subtotal leaves 1,246 MiB of a nominal 4 GiB before filesystem cache, request peaks, ClickHouse merges, image pulls, and backups; actual margin is unknown. Swap is not working RAM for predictable inference latency.

## Design decisions

- Keep ClickHouse and its existing rollback/data-release path. Do not introduce DuckDB until the actual approved analytics query catalog passes result, null/coverage, release-visibility, privilege, concurrency, restart, memory, and latency parity on persistent data under a constrained Linux environment.
- Keep the existing single FastAPI worker, offline RAG index build, extractive/hashing default, and opt-in Ollama profile. Do not reduce limits or cache semantics without isolated measured peaks and quality regressions.
- Do not remove the Next.js runtime while its dynamic runtime configuration route is needed. A static alternative would require an approved strategy for runtime API origin and real/mock mode without exposing secrets or changing the public contract.
- Do not alter CI/CD gates for an unvalidated low-memory profile. Preserve the existing tests, GHCR immutable image flow, staging controls, and explicit production approval.

## Required next evidence

1. Obtain a configured VPS SSH target or redacted read-only measurements in `docs/VPS_CAPACITY_AUDIT.md`; measure portfolio/Caddy and host idle and peak usage, disk, swap, CPU, networks, and port ownership. No production mutation is authorized.
2. Provide an isolated constrained Linux Docker environment and Ollama model access to benchmark the complete stack and approved queries without production access. Measure per-service idle/peak RSS, cgroup OOM counters, swap, CPU, request p50/p95, and portfolio-simulated headroom. Preserve the actual dataset and release semantics.
3. Run Qwen3 0.6B as a candidate against the reviewed NASA grounding and unsupported-request corpus, compare with the approved baseline, and establish digest/license, loaded RSS, context/concurrency, answer/citation quality, and latency. Keep local inference disabled if it misses quality or resource gates.
4. Only then propose a low-memory Compose profile with measured service limits and rollback to the existing profile, and seek Tech Lead review before private deployment.

The exact next external dependency is a usable read-only VPS alias or redacted host measurements. A private deployment remains a separate approval after the evidence and release blockers are resolved.
