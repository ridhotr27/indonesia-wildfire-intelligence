# Q01 — release evaluation

**Status:** `DONE` evaluation with no-go release recommendation  
**Recommendation:** **NO-GO for R01/release approval**

## Outcome

The versioned 50-question benchmark and runner are reproducible, and all local DE, BE,
and FE regression checks pass. The current deterministic retrieval configuration misses
the proposed release target: Recall@5 measured **80% (8/10)** against a target of at
least 85%. The misses are R05 (VIIRS day/night flags) and R08 (the FIRMS `scan` field).

Q01 must not be marked `DONE` yet. Numeric analytical answer accuracy, a manual
citation-claim audit, hosted browser-to-live-services E2E/performance, and automated plus
manual accessibility audits were not observed in this environment. These are recorded as
`null`, not silently converted into passes.

## Measured results

| Measure | Observed | Proposed target | Disposition |
|---|---:|---:|---|
| Reviewed benchmark size | 50 | at least 50 | Pass |
| Supported route accuracy | 100% (35/35) | diagnostic only | Pass; not numeric-answer accuracy |
| Unsupported handling | 100% (15/15) | at least 95% | Pass |
| Retrieval Recall@5 | 80% (8/10) | at least 85% | Fail; improve/approve production retriever and rerun |
| Retrieved support-term proxy | 70% (7/10) | no release target | Diagnostic only; manual audit still required |
| Unsafe arbitrary-query executions | 0 | 0 | Pass for evaluated bounded planner/security suite |
| Planner latency p95 | 0.323 ms | under 10 s end-to-end | Diagnostic only; not E2E latency |
| Analytical result accuracy | Not measured | at least 90% | Required live deterministic parity run |
| Manual citation support | Not measured | at least 95% | Required reviewed claim/source audit |
| Hosted E2E p95 | Not measured | under 10 s | Required deployed/live-service run |
| Accessibility | Not measured | release quality | Required axe-equivalent and manual AT review |

The retrieval run fetched four allowlisted official NASA sources, indexed 201 chunks, and
recorded source hashes in `q01_evaluation_results.json`. The deterministic hashing
embedding is intentionally not described as a production model.

## Verification actually run

- `.venv/bin/python evaluation/run_q01.py`: 50 routes evaluated; 10 labeled retrieval
  questions scored; live official NASA sources fetched.
- `.venv/bin/pytest`: 139 passed, one opt-in live ClickHouse test skipped, one documented
  third-party LangGraph warning.
- `.venv/bin/ruff check .`: passed after correcting five Q01 line-length findings.
- `backend/.venv/bin/python -m unittest discover -s data/tests -p 'test_*.py'`: 61 passed.
- `npm test`: eight files / 24 tests passed.
- `npm run typecheck`; `npm run lint`; `npm run build`: passed. The build retained the
  existing warning about the environment's non-standard `NODE_ENV`.

An initial data-suite invocation from `data/` produced nine import errors because that
command omitted the repository root from Python's import path. It was corrected and the
root invocation passed all 61 tests. The first Q01 focused test also exposed three
benchmark prompts whose wording invoked a second route; the reviewed prompts were
corrected, then both focused tests passed.

## Security, accessibility, and E2E interpretation

The 139-test backend suite retains B05 coverage for payload, quota, concurrency,
deadline, CORS, log-redaction, bounded-tool, and safe dependency-failure behavior. The
24-test frontend suite retains the I02 contract journeys, safe citation rendering,
runtime validation, typed failures, and map lifecycle checks. These are useful regression
evidence, but they are not a hosted browser penetration test or a WCAG/manual
assistive-technology audit.

## Required disposition before approval

1. Select/approve the release retrieval configuration, address R05/R08, and rerun until
   the accepted target or an explicit waiver is recorded.
2. Execute deterministic numeric answers against the approved live ClickHouse dataset
   and publish question-level comparisons.
3. Perform and record a human citation-claim support audit.
4. Run a real browser against live API, ClickHouse, and Qdrant; measure end-to-end p95.
5. Run an automated accessibility scanner and manual keyboard/screen-reader review.

No production model/provider, public authentication, hosting, map-tile terms, deployment,
or release approval is inferred.
