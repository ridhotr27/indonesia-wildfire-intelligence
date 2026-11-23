# B02 — Read-only analytics services review

**Owner:** Backend Engineer agent `/root/b02_be`  
**Technical status:** `IN_REVIEW`  
**Approval status:** Not approved; only the Tech Lead may mark B02 `DONE`.  
**Date:** 2026-10-23

## Summary

B02 implements a selectable ClickHouse HTTP repository over the four approved D04
serving views while preserving the frozen A01 v1.0.0 response models. The default
remains the visibly synthetic repository. No live database, D05 internals, B04 agent
work, shared contract, or shared documentation was changed.

The adapter exposes only a static `SELECT` query catalog. Values use ClickHouse typed
query parameters; callers cannot submit identifiers or SQL. Every HTTP request asks
ClickHouse for `readonly=2`, a bounded execution time, a query-specific result-row
limit, and `result_overflow_mode=throw`. Credentials remain server-side in secret
settings.

Coverage is now read from `analytics_daily_coverage_v1`. Known gaps remain incomplete,
wholly unavailable ranges return null totals, missing coverage rows fail closed as
`unknown`, and complete covered zeroes remain numeric zeroes. Map retrieval is stable,
assigned-only, limited to 5,000, fetches at most `limit + 1`, and drops its sentinel.

## Intentional B02 files changed

- `backend/.env.example`
- `backend/README.md`
- `backend/pyproject.toml`
- `backend/src/wildfire_api/core/config.py`
- `backend/src/wildfire_api/core/errors.py`
- `backend/src/wildfire_api/main.py`
- `backend/src/wildfire_api/repositories/clickhouse.py` (new)
- `backend/src/wildfire_api/repositories/hotspots.py`
- `backend/src/wildfire_api/repositories/mock.py`
- `backend/src/wildfire_api/services/hotspots.py`
- `backend/tests/contract/test_a01_api_contract.py`
- `backend/tests/unit/test_b02_clickhouse_repository.py` (new)
- `backend/reports/B02_READ_ONLY_ANALYTICS_REVIEW.md` (new)

## Incidental formatter-only touches

An early repository-wide `ruff format .` pass mechanically touched the following
pre-existing backend files. They contain no intentional B02 behavior change and were
not reverted because this checkout has no discoverable Git baseline; rewriting them
blindly could overwrite pre-existing user work.

- `backend/src/wildfire_api/contracts/__init__.py`
- `backend/src/wildfire_api/rag/embeddings.py`
- `backend/tests/contract/test_a01_openapi_snapshot.py`
- `backend/tests/contract/test_d04_data_contract_consumer.py`
- `backend/tests/unit/test_rag_fetch.py`

Cache and bytecode files updated by test execution are not deliverables.

## Verification evidence

Commands were run from `backend/` with the existing `.venv`.

1. Baseline/regression during implementation:
   - `.venv/bin/pytest -q`
   - Result: **56 passed**.
2. First B02 suite run:
   - `.venv/bin/pytest -q && .venv/bin/ruff check .`
   - Result: **1 test failed, 61 passed**. The failure was only an invalid use of
     `pytest.raises(..., match=...)` with the structured `AppError`; the production
     fail-closed behavior was correct. The test was corrected to assert `code` and
     `message` fields.
3. Next full run:
   - `.venv/bin/pytest -q && .venv/bin/ruff check .`
   - Result: **62 passed**; Ruff found five style/import issues. They were fixed.
4. Final targeted contract/security run:
   - `.venv/bin/pytest tests/unit/test_b02_clickhouse_repository.py tests/contract/test_d04_data_contract_consumer.py tests/contract/test_a01_api_contract.py -q`
   - Result: **34 passed**.
5. Final complete regression and lint:
   - `.venv/bin/pytest -q`
   - Result: **63 passed**.
   - `.venv/bin/ruff check .`
   - Result: **All checks passed**.

### Independent-review follow-up

The review requested three fail-closed improvements. All are implemented:

1. ClickHouse JSON responses must be objects before `.get()` is used. Arrays,
   strings, and JSON null now return typed `DEPENDENCY_UNAVAILABLE` errors.
2. A01 summary requests reject duplicate `province_codes` through a model validator;
   the frozen request fields and OpenAPI shape are unchanged.
3. Query rows now receive typed validation for contract fields, dates, province codes,
   URLs, monthly counts, coverage enums/invariants, product identity, coordinates,
   confidence/day-night enums, and non-negative FRP. Malformed producer rows fail as
   redacted `DEPENDENCY_UNAVAILABLE` errors instead of escaping as raw/Pydantic 500s.

Follow-up commands and results:

- `.venv/bin/pytest tests/unit/test_b02_clickhouse_repository.py tests/contract/test_a01_api_contract.py tests/contract/test_a01_openapi_snapshot.py -q`
  - First run: **1 failed, 24 passed** because the JSON-null test constructed an
    empty HTTPX response rather than a literal JSON `null`; the fixture was corrected.
  - Rerun: **25 passed**.
- `.venv/bin/pytest -q`
  - Final result after review fixes: **72 passed**.
- `.venv/bin/ruff check .`
  - Final result after review fixes: **All checks passed**.

The B02 tests cover D04 partial and wholly unavailable reference-query semantics,
missing coverage, map sentinel truncation, static query allowlisting, adversarial
filter binding, `readonly=2`, timeout redaction/mapping, and unsupported-major
contract rejection. Existing A01 OpenAPI/fixture and D04 consumer tests remain green.

## Risks and limitations

- D05 runs independently and D06 has not published physical ClickHouse tables/views.
  Therefore no live NASA query result, latency, database grant, or write-denial test is
  claimed. The HTTP request's `readonly=2` control is verified; actual database grants
  remain D06/I01 acceptance work.
- The adapter is opt-in. `WILDFIRE_ANALYTICS_BACKEND=mock` remains the safe default,
  so the running app continues to label its default analytics as synthetic.
- Metadata currently performs four small sequential catalog queries. This is bounded
  and correct, but can be cached or parallelized later if measured latency requires it.
- Physical ClickHouse types, engines, partitions, and grant creation are intentionally
  outside B02 and remain DE-owned.
- B04 bounded LangGraph/chat integration was not started.

## Handoff

B02 is technically ready for Tech Lead review, not `DONE`. I01 remains dependent on
D06 and B02 approval; it must perform live DE/BE parity and database permission checks.
B04 may start only after the Tech Lead approves B02, because B03 and A01 are already
complete.
