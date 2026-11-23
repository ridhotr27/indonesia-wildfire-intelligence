# Semantic-Only Intent Routing Evaluation Strategy

**Status:** Active; LIR-07 development+shadow benchmark recorded, final holdout sealed  
**Owner:** Backend Engineer, with Data Engineer truth review and Tech Lead gate approval

## 1. Purpose

Measure whether embedding-based routing reduces supported-question fallbacks and improves English/Indonesian understanding without weakening tool safety, entity accuracy, exact analytics, NASA grounding, latency, or resource bounds. Routing/planning must record zero generative LLM calls. Results compare variants on identical frozen data and hardware.

## 2. Existing evidence, not a new result

- B11's 64-case deterministic corpus recorded 100% expected route/tool-boundary agreement for its reviewed patterns. That narrow regression corpus is not evidence of general paraphrase understanding.
- B14's 290-case held-out run measured all-minilm at 41.38% route accuracy, 20.20% fallback recovery, 16.92% eligible semantic-intent accuracy, and 0% unsupported false accepts. BGE-M3 measured 46.21%, 28.08%, 27.36%, and 8% respectively. Both remained no-go.
- B09 recorded 90% NASA-document Recall@5 on its approved retrieval evaluation.
- Q01 is approved `DONE` as an evaluation with a no-go recommendation; release-quality live/manual criteria remain open.

Consumed B11/B14 cases become development/regression material. They must not be presented as the fresh holdout for this feature.

LIR-07's corrected semantic-only run (`lir07_semantic_lir01_dev_shadow_v2.json`) evaluated 800 unsealed LIR-01 development+shadow cases: 34.375% route accuracy, 21.667% exact-operation accuracy on supported cases, zero forbidden unsupported tool calls, and 2.52/72.18 ms p50/p95. The candidate fails quality gates. On 2026-11-17 the user acting as Tech Lead accepted these limitations and authorized guarded mode as the LIR-09 default without consuming the final holdout; this is not evidence of release readiness. The v1 artifact is retained but superseded because it omitted deterministic filter-resolution parity.

## 3. Versioned labeled dataset

Create a reviewed corpus with a manifest containing dataset version, schema version, source category, reviewer status, content hash, creation date, and prohibited-content scan result. Keep raw production chats out of the corpus unless a separate privacy-approved process exists.

### 3.1 Minimum composition

Target at least 800 unique cases before rollout evaluation:

| Category | Minimum | Coverage |
|---|---:|---|
| Analytics only | 240 | Single/multi-province count, comparison, monthly trend, highest/lowest/top-N, ties, and zero |
| NASA RAG only | 120 | FIRMS, VIIRS, FRP, confidence, product distinction, limitations, interpretation |
| Explicit combined | 100 | Exact analytics plus independent documentation explanation |
| Multi-turn follow-ups | 120 | Province/date/topic/operation carry-over, overrides, conflicts, topic changes, unsafe history |
| Ambiguous/clarification | 100 | Missing year/date/province, ambiguous scope, conflicting entities, vague “more”/“there” |
| Unsupported/adversarial | 120 | Burned area, confirmed fires, causes, forecasts, unsupported products/regions/dates, prompt/tool/SQL injection |

Language targets across the full set:

- At least 35% English.
- At least 35% Indonesian.
- At least 15% mixed/colloquial Indonesian-English.
- Remaining cases may cover misspellings, abbreviations, punctuation variants, and short conversational turns.

Every supported intent needs at least 40 holdout examples, and no language-intent cell used for approval should have fewer than 20 examples. If the corpus cannot meet that bound, report the cell as underpowered rather than averaging it away.

### 3.2 Labels

Each case should contain:

- Stable case and semantic-family IDs.
- Language and difficulty labels.
- Current message, product, UI context, and bounded prior turns where applicable.
- Expected route: analytics, RAG, combined, clarification, or unsupported.
- Expected operation ID(s).
- Canonical expected entities and their permitted provenance.
- Expected clarification/unsupported reason.
- Expected tool-call boundary and maximum model calls.
- Reference analytics parameters and result fixture/query ID when applicable.
- Reviewed relevant NASA chunk/document judgments for RAG cases.
- Safety tags such as negation, quotation, injection, unsupported metric, or context poisoning.

Data Engineer independently reviews metric, product, province, date/coverage, tie/zero/null, and expected numeric truth. Backend owns intent/route labels and retrieval relevance judgments. Disagreements are resolved before freeze and recorded without inspecting candidate model predictions.

### 3.3 Leakage prevention and splits

- Split train/development/holdout by semantic family or paraphrase template, not by randomly shuffling near-duplicates.
- Keep province/date substitutions of the same template in one partition.
- Reject exact and normalized duplicates and report embedding/character near-duplicate analysis.
- Suggested split: 50% development, 20% shadow-validation, 30% final holdout.
- Use development data for prompts, examples, thresholds, model selection, and failure analysis.
- Use shadow-validation once for rollout tuning after configuration freezes.
- Use final holdout once for the approval decision. Consumed holdout becomes regression data; a new holdout is needed for later tuning claims.

## 4. Variants under comparison

Run every variant using identical cases, canonical contracts, tool mocks/live reference snapshot, hardware, concurrency, warm-up policy, and measurement code.

### A. Existing rule-based router

Current deterministic `DeterministicIntentRouter`, `ChatFilterResolver`, runtime regex operation selection, and current RAG. Semantic routing disabled.

### B. Existing semantic router

Current deterministic-first B14 semantic planner with the pinned index/model/calibration being evaluated. Report rejected matches and disabled/shadow behavior separately; do not silently tune on holdout.

### C. Guarded semantic-only router

Deterministic policy/exact routes followed by the calibrated intent-example index, deterministic slot extraction, and LIR-04 validation. No generative routing/planning call.

### D. Candidate embedding/index profile

The same guarded boundary with one alternate pinned multilingual embedding/index profile. Compare only after model identity, license, dimensions, normalization, and thresholds are frozen.

Also retain two diagnostic ablations when practical:

- Semantic classification without history versus deterministic approved bounded context resolution.
- Current dense NASA retrieval versus each proposed retrieval profile.

## 5. Metrics

### 5.1 Routing and tools

- **Routing accuracy:** exact expected final route divided by cases.
- **Macro/per-class precision, recall, and F1:** for analytics, RAG, combined, clarification, and unsupported.
- **Tool-selection precision/recall/F1:** multi-label operation IDs; a route alone is insufficient.
- **Unsafe/unsupported false-accept rate:** prohibited cases that execute any forbidden tool.
- **Unnecessary fallback rate:** supported cases ending in clarification/unsupported without an expected missing field.
- **Fallback reduction:** `(baseline fallback rate - candidate fallback rate) / baseline fallback rate` on the same supported subset.
- **Clarification accuracy/precision:** correct reason and zero execution when clarification is expected.
- **Route/tool boundary agreement:** exact model, retrieval, and analytics call counts relative to labels.

### 5.2 Entity and rewrite quality

- Exact-match accuracy for product, metric, province set/order, date range, direction, ranking limit, comparison scope, and documentation topic.
- Exact operation-plus-required-entities accuracy.
- Entity provenance accuracy: every accepted value must come from an allowed current/UI/history source.
- Follow-up resolution accuracy by carry-over type and override/conflict case.
- Rewrite preservation: reviewed pass/fail for language, entities, dates, metric, product, negation, scope, and operation.
- Hallucinated-slot rate: accepted executable values absent from permitted inputs; release target is zero.

### 5.3 RAG and answer quality

- Recall@1/3/5 against reviewed relevant chunks/documents.
- MRR and nDCG@5.
- Citation precision and citation support for material claims.
- Answer faithfulness and unsupported-claim rate using reviewed claim/evidence labels; an LLM judge may assist but cannot be the sole authority.
- Exact numeric agreement for analytics and combined answers.
- Combined-branch integrity: generated prose does not alter counts, rankings, ties, coverage, or limitations.

### 5.4 Performance and resources

- Per-stage and end-to-end p50/p95/p99 latency.
- Planning, embedding, Qdrant, BM25, reranking, ClickHouse, generation, and citation-validation duration.
- Routing embedding calls; downstream NASA generation calls/tokens/retries; context characters.
- Peak RSS/VRAM where available, CPU utilization, index size, model size, startup time, and steady-state concurrency behavior.
- Cache hit rate and invalidation correctness if a safe cache is introduced.
- Error/degraded-mode rate by dependency.

Report all metrics overall and by language, intent, difficulty, single/multi-turn, and failure class. Always publish counts and confidence intervals for headline proportions; do not report percentages without denominators.

## 6. Analytics correctness protocol

For each analytics case:

1. Validate expected operation and parameters independently of the implementation under test.
2. Execute the approved parameterized reference query or consume a frozen DE truth fixture tied to the same data snapshot.
3. Compare product, provinces, dates, metric, total/rows, ordering, dense ranks, ties, coverage issues, zero/null distinction, and national geography-exclusion count exactly.
4. Require no generative LLM call for any routing/planning case; NASA generation remains measured separately after routing.
5. Reject any model-generated SQL, unregistered operation, parameter drift, or numeric transformation.

## 7. Safety and adversarial protocol

Include at minimum:

- Prompt/system-instruction extraction.
- SQL, table, tool-name, and parameter injection.
- Requests to ignore deterministic rules or fake citations.
- Unsupported measures embedded in otherwise supported questions.
- Quoted and negated prohibited phrases.
- Malicious prior assistant/user history and cross-turn scope poisoning.
- Oversized/repeated history and Unicode/punctuation variants.
- Retrieval passages containing instruction-like text.
- Model timeout, malformed JSON, unknown operation, extra fields, added entity, and contradictory route.
- Missing/corrupt semantic and NASA indexes.

The hard release gate is zero forbidden tool calls, zero arbitrary SQL paths, zero fabricated citations, and zero hallucinated executable slots in the final holdout and required adversarial suites.

## 8. Collection and reproducibility

The evaluator should emit one machine-readable result per case plus an aggregate report. Record:

- Git/workspace artifact versions and corpus/manifest hashes.
- Model IDs/digests, licenses, dimensions/context windows, prompts, schemas, embedding prefixes/normalization, and index manifests.
- Hardware/OS, thread/concurrency settings, warm/cold policy, and dependency versions.
- Feature flags and thresholds.
- Expected and actual route, operation, canonical entities, reason, call counts, latency, and failure class.
- Retrieval ranks and stable chunk IDs, but not full passage bodies in general telemetry.
- Exact commands and actual pass/fail/skip counts.

Keep development and final-holdout reports separate. Never overwrite a consumed result; publish a new version.

## 9. Statistical comparison and decision rules

- Compare variants on paired cases.
- Report absolute values and deltas from A, plus bootstrap 95% confidence intervals for accuracy/F1/fallback metrics where practical.
- Use paired error analysis or McNemar's test for route-correctness changes; do not treat tiny percentage differences as meaningful without counts.
- A candidate cannot compensate for a safety regression with average accuracy.
- Prefer C over D when quality is statistically/practically equivalent because C is the established calibrated profile and has lower migration risk.
- Adopt D only if the alternate embedding/index profile produces an approved material improvement without failing any safety/resource gate.
- Retrieval-profile adoption requires improvement in ranking metrics and answer support, not Recall@5 alone.

## 10. Proposed rollout gates

Use the acceptance thresholds in `REQUIREMENTS.md`. In addition:

- No existing deterministic supported or denial regression.
- No material decline in any language or intent subgroup.
- P95 and resource use fit the approved local deployment envelope.
- Shadow-validation failure distributions match offline expectations and reveal no new unsafe class.
- A tested one-setting rollback restores the deterministic baseline.
- Contract-dependent follow-up cases cannot gate the current-turn feature until their contract is approved and implemented.

If C passes and D does not materially outperform it, prefer C for release. If no candidate passes, publish the failure report and do not infer release readiness from LIR-09's explicit guarded-default exception. `disabled` remains the tested deterministic rollback.

## 11. Result report template

1. Corpus version, partitions, reviewer coverage, leakage checks.
2. Model/index/prompt/schema/configuration and local hardware.
3. A/B/C/D routing, tool, entity, fallback, clarification, language, and safety table.
4. Retrieval/answer-quality table and per-query misses.
5. Latency/resource table.
6. Exact analytics and combined integrity results.
7. Regressions, malformed-output/dependency failures, and representative failure cases.
8. Gate-by-gate pass/fail with evidence.
9. Recommendation: no-go, shadow-only, limited guarded rollout, or broader guarded rollout.
10. Rollback evidence and unresolved risks.
