# D06 — ClickHouse model and published views review

**Owner:** Data Engineer agent `/root/d06_de`  
**Technical status:** `IN_REVIEW` candidate  
**Approval:** Pending Tech Lead review; this report does not mark D06 `DONE`

## Outcome

D06 implements the approved D04 `1.0.0` physical model without changing its logical
contract. Four DE-owned MergeTree tables feed the exact four published interfaces:
`analytics_hotspot_observations_v1`, `analytics_daily_coverage_v1`,
`analytics_provinces_v1`, and `analytics_ingestion_batches_v1`. Published views use
definer security; the backend role receives `SELECT` only on those views.

The checksum-verifying loader accepts only atomic, published D05 directories. It
validates all four artifact hashes, byte/row counts and identities before inserting.
Observations plus coverage and province rows carrying a DE-only non-null load identity
are gated by the batch record inserted last. The public D04 nullability remains
unchanged because the internal identity is projected out. The loader detects partial
rows across all three physical data tables and verifies the immutable fingerprint on
rerun.

A fail-fast POSIX lock serializes same-host loader processes using a deterministic,
credential-free hashed scope and releases on all exits. Multi-host ingestion writers
are prohibited; no distributed serialization is claimed without a future approved
ClickHouse/Keeper design. Database-side partial-load checks remain enforced.

## Measured physical choices and real-load evidence

The approved artifact contains 253,388 rows over twelve months, so observations are
partitioned monthly and ordered for B02's product/province/time queries. The small
reference tables are not partitioned. A disposable ClickHouse 25.8.5.17 instance loaded
the retained D05 batch in 9.013 seconds and returned `already_loaded` on the identical
rerun in 1.205 seconds after the atomic-gating correction (both include Python
validation and local-process overhead).

Published results reconciled to 253,388 observations, 365 coverage dates, 38 provinces,
796 unassigned points, and 10 multiple-match points. Both July 26–27 records remain
`known_satellite_gap` with null counts, and there are zero observations on those dates.
Riau September 2023 returned 687, matching approved D03B evidence. Monthly country
counts sum to 253,388 and October remains 78,784.

B02's exact monthly and bounded-observation SQL shapes were also executed against the
full loaded views without modification. The monthly query returned Riau September=687
with ClickHouse-reported engine time 23.422 ms on the corrected schema. The earlier
stable ordered point query returned two requested rows in 31.463 ms; its observation
schema was unchanged. I01 still owns HTTP adapter parity.

Representative cold `clickhouse-local` queries, each including process startup, ranged
from 654.461 ms to 707.581 ms for current-schema coverage/province metadata, monthly
aggregation, and a bounded 501-row map query. These measurements are observations, not invented
targets or production forecasts. Exact values are in `d06_clickhouse_validation.json`.

## Permission verification

A disposable server-mode instance was used for actual access-control checks. After the
role migration and assigning `wildfire_backend_reader` to a test backend user:

- `SELECT` on a published view succeeded;
- `SELECT` on a DE physical table returned `ACCESS_DENIED`;
- `INSERT` into a DE physical table returned `ACCESS_DENIED`; and
- `CREATE TABLE` returned `ACCESS_DENIED`.

The first live permission run exposed that invoker-security views also denied the valid
view query. All four views were corrected to explicit `SQL SECURITY DEFINER`, and the
complete matrix then passed. No credential was committed or printed.

## Verification actually run

```text
backend/.venv/bin/python -m unittest data.tests.test_d06_clickhouse -v
Final focused rerun: 10 tests passed in 27.679s (fresh migration, fixture load,
idempotency, same-host lock contention/release, constraints, gaps, nullable geography,
reference query, checksum failure, partial-load failure, atomic visibility, grants)

backend/.venv/bin/python -m unittest discover -s data/tests -p 'test_*.py'
Final rerun: 51 tests passed in 40.875s

backend/.venv/bin/python data/scripts/validate_data_contract.py ...
status=passed; approved 38-province crosswalk and all D04 fixture sections validated

backend/.venv/bin/python -m py_compile data/scripts/load_clickhouse_v1.py data/tests/test_d06_clickhouse.py
passed with no output

Disposable full D05 batch load, identical rerun, reference queries and timing script
passed with the measured values above.

Disposable server-mode grant/denial matrix
passed after the documented definer-security correction.

Disposable HTTP loader test
first load=loaded; second load=already_loaded; 2 observations and 2 null gap days.
```

Intermediate failures retained as evidence:

1. Initial DDL placed constraints after the engine clause; ClickHouse rejected it.
2. The nullable province key was rejected with `allow_nullable_key` disabled; the key
   now uses `ifNull(province_code, '')` without changing published nullability.
3. D05 ISO `T...Z` timestamps required explicit `date_time_input_format=best_effort`.
4. The first role test denied published views because of invoker security; explicit
   definer security fixed this while preserving raw-table and write denial.
5. Docker Desktop was not running. The installed ClickHouse binary provided both
   disposable local storage and a loopback-only server, so no image pull was required.
6. Independent review reproduced pre-commit leakage of coverage rows whose public
   `ingestion_batch_id` is null; the same audit identified province reference leakage.
   Both physical tables now carry an internal load identity, every data view is gated
   by the published batch, and regression tests prove all four interfaces remain empty
   after a simulated pre-commit crash. Retry fails cleanly on the orphaned batch;
   explicit cleanup followed by reload produces exact nonduplicated rows.

## Files and handoff

- `data/clickhouse/migrations/001_d06_physical_model.sql`
- `data/clickhouse/migrations/002_d06_backend_reader_role.sql`
- `data/clickhouse/qa/d06_reconciliation.sql`
- `data/clickhouse/README.md`
- `data/scripts/load_clickhouse_v1.py`
- `data/tests/test_d06_clickhouse.py`
- `data/reports/d06_clickhouse_validation.json`
- this review report

B02 can consume the exact unqualified view names in database `wildfire`. I01 must use
the deployed backend reader identity, rerun parity/reference queries through the actual
backend adapter, verify configured timeouts and query caps, and record deployment-sized
latency. D07 still owns backfill/refresh/recovery operations and is not implemented here.

No public or persistent service was deployed. The large D05 batch and disposable
ClickHouse stores remain outside the repository. Tech Lead approval is still required
before D06 becomes `DONE`.
