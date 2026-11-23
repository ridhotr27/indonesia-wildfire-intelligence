# I01 — ClickHouse-to-backend integration review

**Technical status:** DONE  
**Dependencies:** D06 and B02 DONE  
**Approval:** Explicit user/Tech Lead approval recorded 2026-10-26

## Outcome

I01 rebuilt the approved D05 batch from the pinned local NASA FIRMS artifact, loaded it
into a fresh disposable ClickHouse 25.8.5.17 instance using the D06 migrations/loader,
and exercised the production-shaped B02 HTTP adapter with an ephemeral reader holding
only `wildfire_backend_reader`. The mock default remains unchanged.

The first live API run found a real integration defect: B02 encoded
`Array(String)` query parameters as JSON (`["14"]`), while ClickHouse parameter parsing
requires its quoted array literal syntax (`['14']`). Metadata succeeded but monthly
summary failed closed as a typed 503. The adapter now performs escaped ClickHouse array
encoding while keeping all values out of SQL text. The existing injection test was
updated, and the corrected live rerun passed.

## Live evidence

`backend/reports/i01_clickhouse_validation.json` records the credential-free result:

- API metadata reported `verified`, contract `1.0.0`, the real product ID, and 38
  provinces; no synthetic identity reached real mode.
- Published observations: 253,388; unique coverage days: 365; known null gap days: 2.
- Nullable geography remained exact: 796 unassigned and 10 multiple-match rows.
- FastAPI returned 687 Riau detections for September 2023, matching D06.
- July 26–27 remained incomplete with a null total, never a fabricated zero.
- A map request returned two real bounded rows and correctly reported truncation.
- The backend identity could select published views but received `ACCESS_DENIED` for
  raw-table SELECT, raw-table INSERT, and CREATE TABLE.
- Corrected validator elapsed time was 1.250 seconds on the disposable local instance;
  this is an observation, not a production latency target.

## Delivered files

- `backend/scripts/validate_i01_clickhouse.py` — reproducible API/parity/permission check.
- `backend/tests/integration/test_i01_clickhouse_live.py` — environment-gated live test.
- `backend/src/wildfire_api/repositories/clickhouse.py` — corrected safe array encoding.
- `backend/tests/unit/test_b02_clickhouse_repository.py` — encoding/injection regression.
- `backend/README.md` — operator invocation and scope.
- This report and `backend/reports/i01_clickhouse_validation.json`.

## Verification performed

```text
Full real D05 rebuild
253,388 source/canonical rows; 365 coverage days; 38 provinces; published atomically

D06 migrations + loader against fresh disposable ClickHouse
status=loaded

Initial I01 validator
failed safely: monthly query HTTP 400 -> API 503; Array(String) encoding defect found

Corrected I01 validator
passed all API, parity, nullable-geography, no-synthetic, and permission checks

I01_CLICKHOUSE_* backend/.venv/bin/python -m pytest \
  backend/tests/integration/test_i01_clickhouse_live.py -q
1 passed; one third-party LangGraph warning

backend/.venv/bin/python -m pytest backend
137 passed, 1 environment-gated live test skipped, one third-party warning

backend/.venv/bin/ruff check backend/src backend/tests backend/scripts
All checks passed

backend/.venv/bin/python -m py_compile [I01 files]
passed (no output)

backend/.venv/bin/python -m unittest discover -s data/tests -p 'test_*.py'
51 tests passed
```

## Limitations and handoff

- The database was disposable and loopback-only; this does not claim a persistent or
  public deployment. Production credentials must come from deployment secret storage.
- Live failure behavior for unavailable, timeout, and unsupported-major responses is
  retained in deterministic B02 tests; the accepted D06 views correctly expose 1.0.0,
  so this run did not corrupt live views merely to force a version mismatch.
- Timings are local observations only. Q01 owns performance evaluation.
- The temporary server, reader, and regenerated batch are not deliverables and are
  removed after verification.
- I02 is now READY following explicit Tech Lead approval of I01.
