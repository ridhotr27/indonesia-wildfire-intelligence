# Data operations runbook — immutable v1 snapshot

This runbook operates the approved NASA FIRMS `VNP14IMG.002` VIIRS S-NPP
standard-processing snapshot for calendar 2023 UTC. Its 253,388 rows are satellite
hotspot detections, not confirmed wildfires or burned hectares. July 26–27 are known
satellite gaps and must remain null, never zero.

## Operating model and cadence

v1 is a frozen historical snapshot, not a near-real-time feed. There is no committed
recurring refresh schedule. Run the checks below:

- before and after every migration, load, recovery, restore, credential rotation, or
  deployment;
- after a ClickHouse incident or unexpected API freshness/coverage response; and
- as a deployment-scheduler health check if R01 supplies a scheduler. D07 does not
  claim that such a scheduler or alert destination exists.

An upstream correction or new source artifact is a controlled backfill/reprocessing
event. It requires source review and a new immutable batch. A product, year, boundary,
contract, or transform-semantic change requires a reviewed new version; do not edit
published rows or silently reuse v1 tables/views.

## Identities and prerequisites

Use the DE/operator identity for migrations, ingestion, QA, and recovery. The backend
identity remains SELECT-only on the four `analytics_*_v1` views. Keep passwords in the
deployment secret manager or local environment; never put them in commands, logs,
manifests, or Git. Only one ingestion host may write because the D06 lock is host-local.

Required retained inputs:

- exact source CSV and its SHA-256;
- approved canonical boundary and D03B provenance;
- D05 batch directory with `manifest.json` plus four NDJSON artifacts;
- applied D06 migrations; and
- the code/contract/transform version used to build the batch.

## Isolated backfill and dry run

Build into a new, non-serving output root. D05 stages privately and renames only after
all rows succeed; malformed input removes staging and publishes nothing.

```bash
backend/.venv/bin/python data/scripts/ingest_firms_v1.py \
  --source-csv /retained/read-only/viirs-snpp_2023_Indonesia.csv \
  --boundary-geojson data/derived/reference/idn_adm1_osm_2026-10-10b_canonical.geojson \
  --boundary-provenance data/provenance/d03b_reusable_boundary.json \
  --output-root /isolated/d07-backfill \
  --source-url https://firms.modaps.eosdis.nasa.gov/data/country/viirs-snpp_2023_Indonesia.csv \
  --retrieved-at-utc 2026-10-21T05:00:00Z

backend/.venv/bin/python data/scripts/operate_pipeline_v1.py preflight \
  --batch-dir /isolated/d07-backfill/firms-v1-EXPECTED_ID-d05-ingestion-v1
```

Do not copy the example retrieval timestamp to a new acquisition: use the measured UTC
time from that acquisition. Preflight is offline/read-only and returns `safe_to_load`
only when identity, checksums, counts, 365 coverage records, 38 provinces, zero
rejections, and row accounting pass. Compare its source SHA, batch ID, counts, and
artifact hashes with the change record. An identical D05 rerun verifies and returns the
same manifest. Any changed source bytes produce a different batch ID.

For a database rehearsal, create an isolated database/instance, apply both D06
migrations, load with the D06 loader, run the audit below, rerun the loader and require
`already_loaded`. Never rehearse destructive recovery against the serving database.

## Publish and verify

Set `CLICKHOUSE_URL`, `CLICKHOUSE_DATABASE`, `CLICKHOUSE_USER`, and
`CLICKHOUSE_PASSWORD` through approved secret handling, then:

```bash
backend/.venv/bin/python data/scripts/load_clickhouse_v1.py \
  --batch-dir /absolute/verified/batch

backend/.venv/bin/python data/scripts/operate_pipeline_v1.py audit \
  --batch-dir /absolute/verified/batch

clickhouse-client --multiquery < data/clickhouse/qa/d07_operations.sql
```

The machine audit is pass/fail and exits nonzero on failure. The SQL workflow ends in
`throwIf`, so `clickhouse-client --multiquery` also exits nonzero when any blocking
threshold fails. Exact v1 blocking thresholds are: one expected batch,
253,388 observations (or the verified batch manifest count in the batch-scoped tool),
365 coverage days, 38 provinces, two evidenced null gap days, zero detections on gap
days, zero invalid nullable-geography rows, and zero unpublished rows. The SQL's
`failed_checks` must be zero. Any mismatch blocks release and pages/routs through the
monitoring destination configured by R01; D07 defines the condition but does not invent
an installed alert service.

The API's data freshness is the published batch's `published_at_utc` and may also show
source retrieval/provider-modified/coverage timestamps. For this frozen snapshot,
elapsed age is informational, not operational lag. A null publication timestamp,
missing expected batch, failed audit, or unsupported coverage state is unhealthy.

## Failure and recovery matrix

| Symptom | Safe response |
|---|---|
| Network/acquisition failure | Keep the prior immutable source/batch; retry acquisition into a temporary path and verify checksum. Never label partial bytes as retrieved. |
| Malformed/corrupt source | Stop. D05 publishes nothing. Retain error evidence and obtain a verified source; never hand-edit observations. |
| Corrupt/tampered D05 artifact | Preflight/loader rejects it before database use. Restore from the retained source and reproduce the batch. |
| Duplicate run | Require D05 identical manifest and loader `already_loaded`; fingerprint mismatch is an incident, not an overwrite opportunity. |
| Interrupted load before batch commit | Published views remain unchanged. Use the exact-batch recovery plan below; never retry blindly. |
| Failure after batch commit | Run audit. If it passes, publication is complete; if not, stop serving/escalate and preserve evidence. Do not delete a published batch ad hoc. |
| QA/freshness mismatch | Block deployment, preserve prior serving state, inspect batch provenance and physical/published counts. |

### Interrupted-load cleanup

First use the non-mutating plan:

```bash
backend/.venv/bin/python data/scripts/operate_pipeline_v1.py recovery-plan \
  --batch-dir /absolute/verified/batch
```

It refuses a published batch and reports rows owned by the exact unpublished batch.
After peer review of the batch ID and counts, clean only those rows:

```bash
backend/.venv/bin/python data/scripts/operate_pipeline_v1.py recover-orphans \
  --batch-dir /absolute/verified/batch \
  --confirm-batch firms-v1-EXACT_ID-d05-ingestion-v1
```

The explicit confirmation must exactly match the checksum-verified directory. Recovery
uses `D06_LOCK_DIR` (or `--lock-dir`) and the loader's exact credential-free
`URL|database|batch-ID` lock scope. The lock covers the published-marker check, all
three synchronous batch-scoped deletes, and final zero reconciliation, so a same-host
loader cannot race cleanup. Then rerun the normal loader and complete the audit. The
command refuses cleanup when the batch is already visible through the published batch
view. This remains a host-local guarantee; multiple ingestion hosts are prohibited.

## Rollback and version changes

The primary rollback is forward-safe: batch-last visibility means an interrupted new
load cannot replace the currently published state. Before a migration or reprocessing
event, take a ClickHouse backup/snapshot using the deployment's reviewed R01 procedure
and record database version, migration hashes, batch manifest, and restore test.

There is no generic command here to delete a published batch. Publication rollback is
a release incident requiring Tech Lead approval, a verified backup/restore or reviewed
versioned migration, maintenance mode, and the full QA audit before traffic resumes.
Deleting the batch marker hides dependent rows but is destructive operational state,
not a normal rollback mechanism.

For corrected data or semantic changes, preserve the old manifest/source/checksums and
create a new contract/transform version and new physical/published interfaces. Current
v1 views are single-snapshot interfaces: loading overlapping replacement coverage into
them would duplicate dates/analytics. Coordinate DE/BE/FE review before switching a
view/API version. Record why, who approved, source and boundary hashes, code revision,
contract/transform versions, timestamps, counts, QA result, and rollback reference.

## Known limitations

- Coverage is calendar 2023 UTC only; 2023-07-26/27 are permanent known gaps.
- No live/near-real-time refresh, scheduler, alert destination, or production backup
  system is implemented by D07.
- Only S-NPP `VNP14IMG.002` standard processing is comparable in v1; do not mix sensors.
- Province assignment uses the pinned OSM-derived snapshot. Unassigned and
  multiple-match detections intentionally retain null province fields.
- A host-local lock does not serialize multiple ingestion hosts; multi-host writers
  remain prohibited.
- NASA may correct an archive artifact. A changed checksum triggers reviewed immutable
  reprocessing; it is never silently accepted as the old batch.
- Detection counts do not measure incidents, burned area, causes, or emergency status.
