# D06 ClickHouse operator handoff

This directory implements the physical ClickHouse model for approved D04 contract
`1.0.0`. Hotspots remain satellite detections, not confirmed wildfires or burned-area
measurements.

## Apply and load

Run migrations as a ClickHouse administrator. The first migration creates the
`wildfire` database, four DE-owned MergeTree tables, and the four exact D04 published
views. The second creates a role with `SELECT` only on those views. It intentionally
does not create a user or contain a password.

```bash
clickhouse-client --multiquery < data/clickhouse/migrations/001_d06_physical_model.sql
clickhouse-client --multiquery < data/clickhouse/migrations/002_d06_backend_reader_role.sql
```

Create/rotate the backend user through the deployment secret manager, grant
`wildfire_backend_reader`, and make it the default role. Never pass a password on the
loader command line. Load only a final, checksum-verified D05 batch:

```bash
export CLICKHOUSE_URL=http://127.0.0.1:8123
export CLICKHOUSE_DATABASE=wildfire
export CLICKHOUSE_USER=wildfire_ingestor
export CLICKHOUSE_PASSWORD='set-through-local-secret-management'
backend/.venv/bin/python data/scripts/load_clickhouse_v1.py \
  --batch-dir /absolute/path/to/firms-v1-...-d05-ingestion-v1
```

The loader validates the manifest, byte counts, SHA-256 checksums, row counts,
contract/product/batch identity, and immutable batch fingerprint before publishing.
Observations, coverage (including contract-null gap records), and first-load province
rows are invisible through published views until the batch row is inserted last. The
coverage and province tables use a DE-only non-null `load_batch_id`; it is not exposed
by the D04 views. An identical rerun returns `already_loaded`. If a failed load
left unpublished physical rows, the loader fails closed and requires an operator to
inspect and remove only that exact batch's rows before retrying; it never silently
duplicates or deletes them.

The CLI also takes a fail-fast POSIX lock scoped by a SHA-256 of the credential-free
ClickHouse URL, database, and batch ID. It serializes loader processes on one host and
releases on success or failure. Only one ingestion host may operate against this
database. Multi-host writers are prohibited until a separately reviewed
ClickHouse/Keeper-backed design exists; this lock is not distributed serialization.
Database-side orphan detection remains authoritative after a crash.

Run `data/clickhouse/qa/d06_reconciliation.sql` as the DE/operator identity after a
load. The backend identity must be able to query the four `analytics_*_v1` views and
must receive `ACCESS_DENIED` for DE tables and all writes/DDL.

## Physical choices

The measured approved artifact has 253,388 observations across twelve months. The
observation table therefore partitions by acquisition month and orders by the dominant
BE filters `(product, province, timestamp, observation ID)`. Small coverage, province,
and batch tables use direct lookup order keys and no artificial partitioning. Published
views use explicit definer security so view-only grants do not imply raw-table access.

The sample contract fixture is synthetic. The real D05 batch is intentionally kept
outside Git because its generated NDJSON is approximately 241 MiB.

For preflight, publication/freshness audit, interrupted-load recovery, rollback, and
version-change procedures, follow `data/OPERATIONS_RUNBOOK.md`. The D07 controls do not
create or claim a live refresh schedule; v1 remains an immutable historical snapshot.
