# LIR-01 Current-System Audit, Corpus, and Baseline Review

**Status:** DONE; approved 2026-11-16  
**Date:** 2026-11-15  
**Scope:** evaluation artifacts only; no chatbot runtime, prompt, threshold, model, index,
application configuration, API contract, or ClickHouse behavior changed

## Freeze decision and dependency verification

The Tech Lead explicitly authorized LIR-01. It has no ticket dependency and consumes the
existing D04 data contract, B11 deterministic router, B14 semantic-intent profile, and Q01
evaluation assets. The environment reports Python-compatible installed versions of Pydantic
2.14.1, LangGraph 0.6.11, qdrant-client 1.19.1, pytest 8.4.2, and Ruff 0.17.1. `pip check`
reported `No broken requirements found`. No dependency was added or upgraded.

## Current-system inventory

The frozen baseline is the existing single bounded LangGraph agent and its existing typed
boundaries:

- Deterministic intent routing decides analytics, NASA documentation RAG, combined, or safe
  fallback/denial before any semantic fallback.
- `ChatFilterResolver` owns canonical province/date resolution and current message/UI
  precedence. The public API has no approved history contract, so A/B deliberately do not
  consume corpus history.
- Existing analytics operations are `hotspot_summary_v1`, `hotspot_trend_v1`,
  `hotspot_multi_province_summary_v1`, and `hotspot_province_ranking_v1`. The existing map
  operation remains observable in the vocabulary but is not introduced as a new chat tool.
- Analytics evaluation predicts the existing read-only typed ClickHouse operation and
  parameters. It never executes ClickHouse, accepts SQL, or calculates a numeric result.
- NASA evaluation predicts `nasa_documentation_v1`; it does not execute Qdrant retrieval,
  generation, or citation validation. The approved NASA manifest remains the provenance
  source.
- Variant A is the current deterministic router/filter/operation behavior with semantic
  routing disabled. Variant B is the existing B14 deterministic-first semantic fallback.
  The loaded B14 profile is collection `analytics_intent_examples_v1`, taxonomy
  `wildfire-intents-v1`, 32 examples, cosine distance, and `ollama:all-minilm` at 384
  dimensions with its existing calibrated per-intent thresholds.
- C and D are not implemented or run by LIR-01. The corpus call-boundary schema already
  carries explicit A/B/C/D planner-call labels and the common prediction/result shape is
  deliberately independent of tool execution so later tickets can add frozen C/D adapters.

Known pre-freeze limitations are preserved rather than tuned away: B11 covered a narrow
reviewed deterministic corpus; B14's prior all-minilm and BGE-M3 profiles did not meet rollout
quality gates; Q01 retained a NASA retrieval miss; A/B cannot resolve true follow-ups because
history is not part of the current public request contract.

## Frozen corpus

`lir01-intent-routing-corpus-v1.0.0` contains 1,200 synthetic, reviewed cases across 300
semantic families. It contains no production conversations and claims no synthetic numeric
result. SHA-256:
`148118c06de8cb9e007bc1767d1fc84a900c56d8cb90c9644fdb91da50ed8102`.

| Dimension | Counts |
|---|---|
| Category | analytics 400; NASA RAG 200; combined 160; multi-turn 160; ambiguous 140; unsupported/adversarial 140 |
| Language | English 451 (37.58%); Indonesian 449 (37.42%); mixed 300 (25.00%) |
| Partition | development 560; shadow-validation 240; sealed final holdout 400 |
| Intent | single count 140; monthly trend 140; multi-province 140; ranking 120; documentation 220; combined 160; clarification 140; unsupported 140 |

All category and language minima in `EVALUATION.md` pass. Every supported intent has at
least 40 final-holdout cases. Some final language-by-intent cells contain 10-16 cases, below
the suggested 20-case approval-cell bound; those cells are explicitly underpowered and must
not be used alone for a rollout claim. LIR-12 must report that limitation rather than average
it away.

Every case has stable case/family IDs, language/difficulty, route, operation, canonical
entities and provenance, reason, exact call boundary, truth sources, review state, and safety
tags. The strict model rejects unknown fields, inconsistent route/tool boundaries, incomplete
dates, invalid province codes, duplicate signatures, and semantic families crossing a split.

The generator keeps substitutions of a reused paraphrase frame in one partition. Exact
normalized message/history duplicates are zero. The recorded maximum cross-partition
character-trigram Jaccard similarity within a category is 0.5114, below the frozen 0.80
rejection threshold. The first pre-freeze draft measured 0.9367; it was regenerated before
freeze. Its generated baseline outputs were discarded after DE review and are not evidence.

Twenty final-holdout cases across five semantic families explicitly label partial coverage
across the known gap, a wholly unavailable range, verified-zero-only handling, dense-rank
cutoff ties, and explicit reporting of observations not assigned to exactly one province.
They are contract/operation cases, claim no measured NASA number, and cite the approved
synthetic contract fixture only for behavior—not as real observation evidence.

The final holdout is sealed by default in the runner and was not consumed. The immutable A/B
artifacts contain only development plus shadow-validation cases.

## Independent structured-data review boundary

The Data Engineer independently confirmed the D04 truth boundary used here:

- Only `VNP14IMG.002_SNPP_FIRMS_SP`, calendar 2023 UTC, is in scope.
- 2023-07-26 and 2023-07-27 are unavailable coverage, not zero detections.
- The metric is the count of exact-deduplicated FIRMS observations. It is not confirmed
  fires, burned area, cause, or a forecast.
- Province assignment follows the accepted 38-province contract; unassigned and
  multiple-match observations are not silently assigned.
- The approved crosswalk maps `91` to Papua and `92` to Papua Barat. The frozen evaluation
  uses `92` for Papua Barat and records the existing Backend resolver mismatch as a runtime
  limitation rather than changing runtime behavior in this ticket.
- English province aliases are Backend-owned until LIR-02 publishes a DE semantic catalog;
  `Sumbar` is not asserted as an approved data alias.

The corpus points to the approved data contract, parameterized query catalog, routing policy,
and NASA manifest. It does not claim independent numeric truth for Aceh versus Sumatera
Barat, complete rankings, ties, zero-count provinces, or synthetic fixtures. Those remain
future DE fixture/reference-query work and are not represented as measured LIR-01 accuracy.

## Actual A/B baseline results

Both variants used the identical 800 development plus shadow-validation cases. The final
holdout remained unconsumed. These results measure route/operation/entity prediction only;
they do not measure ClickHouse numeric agreement, NASA Recall/MRR/nDCG, citation support,
answer faithfulness, generation quality, end-to-end latency, or production capacity.

| Metric | A: deterministic | B: current B14 all-minilm |
|---|---:|---:|
| Cases | 800 | 800 |
| Route accuracy | 33.50% | 35.50% |
| Route macro-F1 | 38.92% | 36.03% |
| Tool precision / recall / F1 | 88.68% / 26.11% / 40.34% | 83.95% / 28.33% / 42.37% |
| Analytics entity exact accuracy | 8.54% | 11.67% |
| Supported fallback rate | 68.83% | 64.33% |
| Clarification precision | 100.00% | 22.49% |
| Unsupported false-accept rate | 0.00% | 0.00% |
| Forbidden tool calls | 0 | 0 |
| Prediction p50 / p95 | 0.131 / 0.868 ms | 1.640 / 50.381 ms |

Variant B accepted 35 semantic matches and rejected 349; 416 cases stayed on deterministic
routing. Multi-turn route accuracy was 0% for both, as expected from the intentionally absent
history contract. Variant B modestly improved overall route accuracy, tool recall, entity
exactness, and supported fallback rate, while reducing macro-F1 and clarification precision.
This is baseline evidence, not an adoption recommendation and not permission to change the
disabled-by-default semantic runtime behavior.

## Reproduction and actual verification

Commands were run from `backend/` unless noted:

```text
.venv/bin/python -m pip check
.venv/bin/python evaluation/build_lir01_corpus.py
.venv/bin/python evaluation/run_lir01_baseline.py --variants A
.venv/bin/python evaluation/run_lir01_baseline.py --variants B
.venv/bin/pytest tests/evaluation/test_lir01_baseline.py
.venv/bin/pytest tests/unit/test_b11_intent_routing.py tests/unit/test_b14_semantic_intent.py tests/evaluation/test_q01_benchmark.py tests/evaluation/test_lir01_baseline.py
.venv/bin/pytest
.venv/bin/ruff format --check evaluation/lir01_models.py evaluation/build_lir01_corpus.py evaluation/run_lir01_baseline.py tests/evaluation/test_lir01_baseline.py
.venv/bin/ruff check .
```

The focused LIR-01 suite passed 11 tests. The combined B11/B14/Q01/LIR-01 regression passed
105 tests, and the final full backend suite passed 389 with 1 existing opt-in skip. Ruff
passed repository-wide, and Ruff formatting passed for all four LIR-01 Python files. Test
runs emitted one existing LangGraph pending-deprecation warning and no failure. Variant B
required the installed local Ollama 0.40.15 service and existing
`all-minilm` model; it was started loopback-only for the run and stopped immediately after.

## Limitations and next-ticket boundaries

- This ticket freezes and measures the current system; it does not improve the scores.
- No application runtime behavior or public API changed.
- The synthetic corpus needs future individual/domain review expansion; it is not production
  chat data and cannot establish real-user satisfaction.
- No numeric analytics execution occurred. DE-owned zero/tie/null/unassigned truth expansion
  belongs to LIR-02 and later final evaluation.
- No NASA retrieval or answer generation occurred, so retrieval relevance, citation accuracy,
  and faithfulness remain unmeasured here and belong to LIR-08/LIR-10/LIR-12.
- Multi-turn performance cannot improve until LIR-03 explicitly approves a bounded history
  contract and LIR-06 implements its safe use.
- C/D candidates, planner tokens, resource/concurrency behavior, confidence intervals, and
  final rollout decisions are future-ticket work. The final holdout must stay sealed until
  the approved LIR-12 run.
