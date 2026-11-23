# D07 — backfill, refresh, freshness, QA, and recovery review

**Owner:** Data Engineering specialist `/root/d07_ops`  
**Technical status:** `IN_REVIEW` candidate  
**Approval:** Pending Tech Lead review; this report does not mark D07 `DONE`

## Outcome

D07 now supplies a reproducible operator runbook, exact v1 QA queries, and a bounded
operations CLI. The CLI provides offline checksum/identity preflight, read-only
publication and freshness audit, a non-mutating interrupted-load recovery plan, and an
explicitly confirmed cleanup limited to one verified unpublished batch.

The operating model is deliberately honest: v1 is the approved immutable calendar-2023
snapshot, not a live feed. Checks are event-driven around load/deploy/migration/incident
operations. The runbook does not invent a scheduler, alert destination, production
backup, or refresh result. It distinguishes freshness metadata (`published_at_utc`,
source retrieval/provider timestamps, and coverage end) from real-time data lag.

## Safety and QA behavior

- D05 remains the only backfill builder. It stages privately and atomically renames;
  corrupt input cannot publish a partial directory.
- Offline preflight reuses D06 verification and additionally requires 365 coverage
  rows, 38 provinces, zero rejected rows, and exact source/canonical/duplicate
  accounting.
- Publication audit requires the verified batch row count, 365 dates, 38 provinces,
  exactly two evidenced null gap dates, no observations on those dates, no invalid
  non-assigned geography, and no unpublished physical rows.
- Recovery planning never mutates. Cleanup refuses any published batch and requires
  `--confirm-batch` to exactly equal the checksum-verified directory identity. Three
  batch-scoped deletes use synchronous mutations and must reconcile to zero before the
  normal loader is retried. Cleanup holds the exact D06 loader lock scope across the
  published-marker check, all deletes, and reconciliation; contention is fail-fast.
- Both Python and SQL orphan checks use explicit `NOT EXISTS` anti-joins rather than
  relying on ClickHouse outer-join default values.
- A failed CLI audit prints its JSON evidence and exits 1. The SQL check uses
  `throwIf`, producing a nonzero ClickHouse-client result on any failed threshold.
- Duplicate normal loads retain D06 behavior: an identical fingerprint returns
  `already_loaded`; mismatch fails closed.
- Published rollback is not automated. It requires Lead approval plus an R01-reviewed
  backup/restore or versioned migration and a full audit. Corrected/changed semantics
  preserve old provenance and move to new contract/transform/interfaces; overlapping
  replacement coverage must not be loaded into the single-snapshot v1 views.

## Verification actually run

Focused D07 unit tests (final corrected run):

```text
backend/.venv/bin/python -m unittest \
  data.tests.test_d07_operations.D07OperationsTests -v
Ran 9 tests in 1.109s — OK
```

Disposable ClickHouse interrupted-load recovery:

```text
backend/.venv/bin/python -m unittest \
  data.tests.test_d07_operations.D07LocalRecoveryIntegrationTests -v
Ran 1 test in 28.337s — OK
```

That live local test applied the fresh D06 schema, inserted two observations without a
batch visibility commit, observed an exact two-row recovery plan, synchronously removed
only that unpublished batch, reconciled all orphan counts to zero, and then completed a
clean normal load. It also executed the anti-join audit and proved the SQL assertion
returns nonzero for the intentionally undersized synthetic fixture.

The retained 20,067,598-byte source with SHA-256
`2dba3b772b5a3a2cc0feed128af74637810021dd41dc34d584cb99b40411665a`
was processed into a disposable isolated D05 output. Offline preflight passed with
253,388 source/canonical rows, zero duplicates/rejections, 365 coverage rows, 38
provinces, no database contact, and no database change. The generated batch was removed
after verification; no new live download or serving publication is claimed.

The complete 61-test data inventory was run in bounded groups after corrections:

```text
41 unchanged D01–D05 tests: OK in 12.477s
8 D06 unit tests: OK in 0.034s
2 D06 clickhouse-local tests: OK in 12.152s and 15.585s
9 D07 unit tests: OK in 1.109s
1 D07 clickhouse-local recovery/audit assertion test: OK in 28.337s
Total: 61 passed, 0 failed

backend/.venv/bin/python -m py_compile \
  data/scripts/operate_pipeline_v1.py data/tests/test_d07_operations.py
passed with no output
```

An initial direct `backend/.venv/bin/pytest data/tests -q` invocation failed collection
because the console-script path omitted the repository root from `sys.path`; it did not
execute tests. Verification used the repository's established `python -m unittest`
form above. No result from the failed invocation is counted as a test failure.

## Files and handoff

- `data/OPERATIONS_RUNBOOK.md`
- `data/scripts/operate_pipeline_v1.py`
- `data/clickhouse/qa/d07_operations.sql`
- `data/tests/test_d07_operations.py`
- `data/reports/d07_operations_validation.json`
- this review report
- `data/clickhouse/README.md` links the D07 handoff

Q01 may use the exact audit thresholds as its DE data-health prerequisite. R01 must
choose and verify actual scheduling, alert routing, backup/restore, retention, and
deployment monitoring. D07 does not claim those production decisions or services.

Known source limitations remain binding: hotspots are detections rather than confirmed
fires/burned area; only S-NPP `VNP14IMG.002` standard processing and calendar 2023 UTC
are approved; July 26–27 are known gaps; province assignment uses the pinned
OSM-derived snapshot with explicit unassigned/multiple-match nulls; and NASA archive
corrections require reviewed immutable reprocessing rather than silent overwrite.
