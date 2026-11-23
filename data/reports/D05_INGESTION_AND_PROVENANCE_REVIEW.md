# D05 ingestion and provenance review

**Ticket:** D05 — Implement idempotent ingestion and provenance pipeline  
**Owner:** Data Engineer agent `/root/d05_de`  
**Technical status:** `IN_REVIEW` candidate  
**Approval:** Pending Tech Lead review; this report does not mark D05 `DONE`

## Outcome

The pipeline implements the approved D04 v1.0.0 logical contract for the pinned NASA
FIRMS VIIRS S-NPP standard-processing 2023 artifact and OSM-derived province snapshot.
It performs strict parsing, UTC normalization, exact-lexeme identity, exact duplicate
removal, direct point-in-polygon enrichment, complete calendar coverage publication,
immutable provenance, bounded acquisition retries, and atomic publication. It pins
and validates the approved boundary source identity, checksums, license, attribution,
and exact crosswalk. It does not create ClickHouse DDL or serving views; those remain
D06.

Pinned boundary and source-request identity validation runs before the idempotent
existing-batch path. A valid prior batch therefore cannot cause changed provenance,
geometry, attribution, crosswalk, or source URL to bypass validation.

Hotspots remain satellite detections, not confirmed wildfire incidents or burned-area
estimates.

## Deliverables

- `data/scripts/ingest_firms_v1.py` — dependency-light CLI and reusable ingestion API.
- `data/tests/test_d05_ingestion.py` — identity, deduplication, gap, malformed input,
  boundary-provenance tamper, secret-bearing URL, idempotency, and failure-safe tests.
- `data/scripts/firms_historical_access.py` — existing secure acquisition path extended
  with bounded transient retries and per-attempt temporary-file cleanup.
- `data/tests/test_firms_historical_access.py` — deterministic transient-success and
  retry-exhaustion/no-overwrite coverage.
- `data/reports/d05_full_run_validation.json` — measured full-artifact QA evidence.
- This runbook and review record.

Each published batch contains `observations.ndjson`, `daily_coverage.ndjson`,
`provinces.ndjson`, `ingestion_batch.ndjson`, and `manifest.json`. Publication first
writes a private staging directory and only then atomically renames it to the
deterministic batch path. A rerun verifies every recorded checksum and reuses the
batch. It refuses a missing, modified, or incomplete existing batch.

## Full-artifact evidence

The final implementation was executed against the already-inspected repository
artifact, not a fabricated or newly downloaded source:

- Source SHA-256: `2dba3b772b5a3a2cc0feed128af74637810021dd41dc34d584cb99b40411665a`
- Source bytes/rows: 20,067,598 / 253,388
- Canonical rows: 253,388
- Exact duplicate excess/rejected: 0 / 0
- Assignment: 252,582 assigned, 796 unassigned, 10 multiple-match
- Quality flags: 8 zero-FRP, 796 geo-unassigned, 10 geo-multiple-match
- Coverage: 365 calendar rows; July 26–27 are `known_satellite_gap` with null counts
  and NASA LDOPE issue 480 evidence
- Generated output: approximately 241 MiB under `/tmp`; intentionally not committed
- A second identical invocation verified artifact checksums and returned the same
deterministic batch without creating another batch
- The final full run also proved there are no observations on either approved known-gap
  date; the parser now independently fails closed if a future artifact introduces one

The machine-readable report records output checksums. Its ingestion-batch checksum
includes the actual publication timestamp and is evidence for this run, not a promise
that a newly generated batch file has an identical checksum.

## Operator runbook fragment

Acquire the approved public artifact with the existing failure-safe downloader, or
use a previously verified local artifact. Never embed `NASA_FIRMS_MAP_KEY` in a URL,
filename, log, manifest, or command history. Then run:

```bash
backend/.venv/bin/python data/scripts/ingest_firms_v1.py \
  --source-csv data/raw/nasa_firms/viirs-snpp_2023_Indonesia.csv \
  --boundary-geojson data/derived/reference/idn_adm1_osm_2026-10-10b_canonical.geojson \
  --boundary-provenance data/provenance/d03b_reusable_boundary.json \
  --output-root /path/to/immutable/d05-batches \
  --source-url https://firms.modaps.eosdis.nasa.gov/data/country/viirs-snpp_2023_Indonesia.csv \
  --retrieved-at-utc 2026-10-21T07:15:26.716826Z \
  --provider-last-modified-utc 2025-06-24T17:07:37Z
```

The retrieval and provider timestamps above are the recorded evidence for the pinned
repository artifact. Operators must use actual evidence for another artifact and must
not copy these values blindly. `--source-url` accepts credential-free HTTPS with no
query string or fragment.

Do not copy a staging directory into a serving location. Only a final batch directory
with a valid `manifest.json` and `publication.state=published` is eligible for D06.
D06 must independently verify the manifest and all artifact checksums before loading.

## Verification performed

Successful checks:

```text
backend/.venv/bin/python -m unittest data.tests.test_d05_ingestion -v
Superseded by the combined focused rerun below after independent-review fixes

backend/.venv/bin/python -m unittest data.tests.test_d05_ingestion data.tests.test_firms_historical_access -v
Final second re-review rerun: 18 tests in 9.808s — OK

backend/.venv/bin/python -m unittest discover -s data/tests -p 'test_*.py'
Final second re-review rerun: 41 tests in 13.712s — OK

backend/.venv/bin/python -m py_compile data/scripts/ingest_firms_v1.py data/scripts/firms_historical_access.py data/tests/test_d05_ingestion.py data/tests/test_firms_historical_access.py
Passed (no output)

Targeted credential-pattern scan over the new script and tests
No credential-shaped value found (no output)

Full 253,388-row CLI execution and identical second invocation
Passed; measured results are listed above and in d05_full_run_validation.json
```

Independent review initially blocked D05 on three cases. They are resolved and covered
by deterministic tests: an observation dated July 26 or 27 now aborts without a
published batch; caller-supplied boundary metadata cannot override the pinned source,
snapshot, commit, checksums, ODbL terms, attribution, or exact canonical crosswalk;
and transient acquisition failures retry within a maximum of five configured attempts.
Retry exhaustion removes temporary files, preserves an existing destination, and never
echoes a credential-bearing URL.

The second independent review found that an already-existing valid batch returned
before rechecking boundary inputs, and that broad `OSError` handling could retry local
filesystem failures. The finalized path validates pinned boundary metadata, canonical
geometry checksum, exact crosswalk, and source URL before reuse. Regression tests alter
metadata and geometry after creating a valid batch and verify rejection. Response-read
errors remain transient, while local tempfile/write/replace errors are outside retry
handling. Deterministic tests prove a local tempfile `OSError` and HTTP 404 each use
exactly one attempt, clean up safely, preserve prior output, and redact request secrets.

Observed development failures are retained rather than hidden:

1. The first direct CLI attempt failed before processing with `ModuleNotFoundError:
   No module named 'data'`; direct-execution imports were fixed and tested.
2. The first full implementation used the older unprepared polygon routine and was
   manually interrupted after several minutes. It published no batch. The final
   implementation uses the already-validated latitude-band scanline index and the
   subsequent full run completed successfully.
3. `git diff --check` could not run because this supplied workspace has no `.git`
   directory. This is an environment limitation, not a passing Git check.

## Data-quality and operational risks

- Ten observations intersect more than one polygon in the accepted OSM snapshot.
  They are preserved as `multiple_match` with null province values; they are not
  coerced to a nearest province.
- 796 observations are outside all accepted province polygons and remain unassigned.
- The output is newline-delimited JSON for a clear D05 handoff. D06 owns physical
  ClickHouse types, engines, partitions, loading transactions, grants, and views.
- The public historical source may be replaced upstream. Source checksum mismatch
  creates a different deterministic batch identity and requires explicit provenance;
  it never mutates an existing batch.
- Row validation is fail-closed. A malformed row aborts the entire staged batch;
  D05 does not publish a partially valid subset or silently quarantine bad data.
- An observation on an approved known-gap date is treated as a source contradiction
  and aborts the batch; coverage can therefore never say gap/null while publishing a
  detection for the same day.
- Acquisition defaults to three attempts and permits only one through five. Only
  transient network, timeout, HTTP 429/5xx, or response-read failures retry. Invalid
  CSV content, local filesystem failures, and other HTTP 4xx responses fail immediately.
- The pipeline records the supplied artifact provenance but does not claim that row
  presence proves complete satellite coverage. Missing non-gap dates remain
  `unknown`; only independently documented July 26–27 gaps receive a gap status.

## BE/D06 handoff

D06 may consume only a checksum-verified, published D05 directory. It must preserve
the four D04 interfaces and all nullable coverage/geography semantics. It must not
load staging paths, infer zero from `unknown` or `known_satellite_gap`, expose raw
source hashes to browser consumers, or grant the Backend write access.

Recommended review decision: accept D05 technical completion and move it to `DONE`
only after independent Tech Lead verification. D06 must remain blocked until that
approval is recorded in the canonical backlog.
