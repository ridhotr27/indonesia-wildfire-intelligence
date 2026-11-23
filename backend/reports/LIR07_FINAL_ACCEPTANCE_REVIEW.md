# LIR-07 Independent Final Acceptance Review

**Decision:** IN_REVIEW — acceptance denied  
**Date:** 2026-11-17

## Findings

Architecture and safety boundaries pass: the single bounded LangGraph runtime remains;
deterministic denials/exact routes precede semantic matching; similarity supplies no
arguments; deterministic resolution and LIR-04 validation authorize every executable
operation; missing/low-confidence matches fail closed; no generative router or generated
SQL exists; shadow/disabled behavior and deterministic rollback are tested. The semantic
index is separate, versioned, compatibility-checked, and contains reviewed English,
Indonesian, and mixed-language examples.

The corrected immutable development+shadow artifact contains 800 cases, records zero
forbidden unsupported tool calls, consumes no final holdout, and reports p50/p95 routing
latency of 2.52/72.18 ms. Independent calculation from its confusion matrix found:

| Gate | Required | Observed | Result |
|---|---:|---:|---|
| Route macro-F1 | >= 0.90 | 0.3511 | Fail |
| Minimum supported-route recall | >= 0.80 | analytics 0.1056; combined 0.1667; RAG 0.6000 | Fail |
| Exact operation + required entities | >= 0.95 | operation exactness 0.2167 | Fail |
| Forbidden unsupported tool calls | 0 | 0 | Pass |
| Routing p95 | < 10 seconds | 72.18 ms | Pass |

Overall route accuracy is 0.34375. The explicit LIR-09 decision accepted these
limitations for guarded local activation, but `REQUIREMENTS.md` states that this exception
does not satisfy or waive deployment/release gates. LIR-07 also originally required a
disabled default; LIR-09 later changed the default to guarded under that exception.

## Independent verification

- Ruff: passed.
- Focused LIR-07/B14/LIR-04/LIR-09/B04/B11/API set: 199 passed.
- Full backend suite: 497 passed, 1 existing opt-in skip, 1 existing LangGraph warning.
- Benchmark artifact recomputation: 800 cases; no final holdout; metrics above.

## Actionable blockers

Choose one path before approval:

1. Improve and freeze the candidate on development/shadow data until every written
   LIR-07 quality gate passes, without consuming the final holdout; or
2. Formally amend LIR-07 into a completed no-go/experimental-evidence ticket, explicitly
   separating implementation completion from release eligibility and recording a Tech
   Lead waiver of the current quality-gate acceptance language.

Passing tests or the LIR-09 activation exception alone cannot make the current LIR-07
criteria pass. LIR-12 must not start while LIR-07 remains `IN_REVIEW`.

## Configuration inconsistencies before LIR-12 freeze

- LIR-07 records disabled-by-default, while LIR-09 and `Settings` default to `guarded`.
- `Settings` versus `.env.example`: request timeout 15/120 seconds; agent timeout 8/120;
  Ollama timeout 60/120; retrieved characters 6000/3000; model tokens 1200/192.
- Default runtime is `degraded` with RAG/generation disabled and hashing RAG embeddings;
  the candidate local profile requires `local_grounded`, local RAG, Ollama all-minilm,
  and Ollama Qwen generation.
- Freeze must pin the semantic manifest/dataset/calibration/threshold hashes, LIR-08
  Qdrant manifest and retrieval profile, all-minilm and Qwen identities/licenses/digests,
  LIR-04 catalog/data/API versions, effective limits, hardware/concurrency/warm-up policy,
  evaluator/corpus hashes, and rollback values.
- Variant D must be explicitly excluded or supplied as a distinct approved immutable
  alternate; no eligible frozen alternate currently exists.

## Backend remediation update (2026-11-17)

Remediation improved the 800-case development+shadow result to 85.0% route accuracy,
0.8850 macro-F1, 0.6667 analytics recall, 1.0000 combined/RAG recall, and 0.8000 exact
operation accuracy, with zero forbidden calls. All 680 current-contract cases now pass;
the remaining 120 cases require history that LIR-03 explicitly deferred. LIR-07 therefore
remains `IN_REVIEW`. See `LIR07_REMEDIATION_REVIEW.md` and the immutable v9 artifact.
