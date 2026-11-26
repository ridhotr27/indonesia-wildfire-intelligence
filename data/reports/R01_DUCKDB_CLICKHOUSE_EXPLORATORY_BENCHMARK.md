# R01 exploratory analytics engine comparison

**Decision:** Retain ClickHouse. This bounded scan suggests a DuckDB memory advantage, but does not establish production-query parity, steady-state memory, or latency on Linux. No backend/provider or data contract change is justified yet.

## Evidence and method

- Host: local macOS, not the 4 GiB Linux VPS. ClickHouse `local` 25.8.5.17; DuckDB Python 1.4.2 installed only in the ignored project virtual environment for this experiment. The existing ClickHouse server was not running (`clickhouse client` could not connect to `[::1]:9000`).
- Real D08 2025 `observations.ndjson` artifact: batch `firms-v11-11abffff52dedfe985a8-d08-multiyear-ingestion-v1`, 96,056 source/canonical rows, 95,984,383 bytes, manifest SHA-256 `a6ec23f0a81eb3309dc15934afc325296ac46c06ce6e2b758eb25746b8cffe18`. Its manifest labels ClickHouse ingestion unauthorized; this experiment only read the file.
- One cold process per engine, one run, scanning JSONEachRow/JSON auto from the same file. Query shape: `SELECT province_code, count(*) FROM observations WHERE product_id = 'VNP14IMG.002_SNPP_FIRMS_SP' GROUP BY province_code ORDER BY count DESC, province_code LIMIT 5`. This resembles the published province-ranking operation but does **not** exercise its coverage CTE, 38-province zero filling, null geography, release filter, or serving grants.
- Elapsed wall time came from Python `time.monotonic()` around each process/query. Peak resident bytes came from `resource.getrusage`: `RUSAGE_CHILDREN` for ClickHouse, `RUSAGE_SELF` for the Python/DuckDB process. Values include different process startup overheads and are indicative only.

| Engine | Top five `(province_code, count)` | Elapsed | Peak RSS |
|---|---|---:|---:|
| ClickHouse local | `(61,21693), (53,12830), (64,5582), (52,4294), (14,4053)` | 1.881 s | 377.3 MiB |
| DuckDB in Python | Same five tuples, exact agreement | 0.569 s | 151.7 MiB |

Observed single-scan difference: DuckDB used 225.6 MiB less peak RSS (59.8%) and completed 1.312 s sooner on this host. This is **not** a deployable stack reduction: ClickHouse local is not the persistent server, DuckDB was not tested with a persisted database, and no repeated/warm, concurrent, full three-year, or production query-catalog tests were run. Neither engine's idle memory or Linux cgroup peak was measured.

## Required before any provider switch

On an isolated Linux host with the actual approved release, compare a tuned persistent ClickHouse server and a persisted DuckDB read-only snapshot using all fixed backend analytics queries and DE reference results. Include coverage unknown/zero, null geography, ties, point limits, date/product filters, read-only behavior, refresh/atomic publication, single-writer boundaries, cold/warm p50/p95, concurrency, startup, idle/peak RSS, and disk footprint. Preserve ClickHouse as the rollback path. Backend Engineering must review the typed adapter and contract behavior before implementation; a file-scan result alone does not authorize replacing ClickHouse.
