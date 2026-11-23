# B14 semantic intent routing review — 2026-11-15

## Outcome

B14 implementation is complete for review, but guarded rollout is **not approved**. The backend now
has a deterministic-first semantic fallback, a separate versioned Qdrant intent collection, strict
compatibility manifests, disabled/shadow/guarded modes, offline build/evaluation tooling, bilingual
fixtures, a 500-case synthetic corpus, typed-operation integration, degraded behavior, and rollback.

The installed `ollama:all-minilm` model was subsequently made available locally. A separate
384-dimensional index was built, thresholds were calibrated on development-only cases, the index was
rebuilt with that calibration, and the held-out partition was measured. The result does not meet
B14's accuracy/fallback targets, so guarded rollout remains **no-go** and disabled by default.
The multilingual BGE-M3 candidate was also downloaded and evaluated in a separate collection against
the same frozen corpus. It improved recovery but failed the zero-false-accept safety gate and was
rejected; production configuration remains pinned to all-minilm and disabled semantic routing.

## Architecture and safety evidence

- The deployed architecture remains one bounded LangGraph runtime.
- Deterministic exact routes, security denials, unsupported measures/products/regions/dates, and
  quoted/negated handling run before semantic matching and do not call the intent index.
- Semantic output is one allowlisted intent only. The existing resolver independently validates
  province/date slots, and runtime code selects existing typed fixed operations.
- The intent collection is separate from NASA documentation and pins taxonomy, dataset hash,
  embedding name/dimension, cosine distance, collection, example count, thresholds, and calibration.
- Indexes build offline into staging and publish atomically. API startup never rebuilds them.
- Missing, corrupt, incompatible, uncalibrated-guarded, or unavailable intent indexes degrade to the
  deterministic runtime. The server never switches model/provider or calls a cloud service.
- Configuration defaults to `disabled`; `shadow` does not change answers; rollback is setting the
  mode to `disabled`.
- No public API/trace fields, generated SQL, conversation memory, production-chat collection,
  frontend behavior, ClickHouse schema, or dependency were added.

## Data and evaluation artifacts

- `resources/semantic_intents/examples_v1.json`: 32 reviewed EN/ID/mixed index examples across all
  eight bounded intents. Records contain no SQL, answer values, vectors, credentials, or user IDs.
- `evaluation/b14_semantic_corpus_v1.json`: 500 unique synthetic cases: 400 supported cases (50 per
  intent), 200 Indonesian cases, and 100 unsupported/adversarial/ambiguous cases. Exact indexed-text
  leakage is rejected by tests. The templates are reviewed; individual expansion review remains open.
- `evaluation/run_b14_semantic.py`: deterministic-first evaluator reporting route accuracy, eligible
  semantic intent accuracy, fallback recovery, unsupported false accepts, per-intent/per-language
  results, and p50/p95 match latency.

## Measured results — real all-minilm held-out run

The held-out partition contained 290 cases. This run used `ollama:all-minilm`, collection
`analytics_intent_examples_v1`, 384-dimensional cosine vectors, and the development calibration
`b14-all-minilm-b14-semantic-evaluation-v1.0.0`.

| Measure | Result |
|---|---:|
| Held-out cases | 290 |
| Route accuracy | 41.38% |
| Baseline supported generic fallbacks | 203 |
| Fallback recovery | 20.20% |
| Eligible supported semantic intent accuracy | 16.92% |
| Unsupported false-accept rate | 0.0% |
| Clarification precision | 20.0% |
| English route accuracy | 45.0% |
| Indonesian route accuracy | 38.0% |
| Semantic match latency p50 / p95 | 15.19 ms / 28.57 ms |
| Deterministic / semantic accepted / semantic rejected share | 16.90% / 14.14% / 68.97% |

The zero unsupported false-accept gate passed, but the 95% intent-accuracy and 60% fallback-reduction
gates failed substantially. Per-intent recall ranged from 0% for single count, multi-province total,
and combined requests to 80% for documentation semantics. The complete precision/recall/F1 and
confusion matrix are committed in `evaluation/b14_all_minilm_heldout_result_v1.json`.

For comparison only, the explicitly non-release hashing surrogate measured 32.2% route accuracy,
2.97% fallback recovery, 2.99% eligible intent accuracy, and 2.0% unsupported false accepts. It
remains prohibited for guarded routing.

### Multilingual candidate comparison

| Measure | all-minilm | BGE-M3 |
|---|---:|---:|
| Route accuracy | 41.38% | 46.21% |
| Eligible semantic intent accuracy | 16.92% | 27.36% |
| Fallback recovery | 20.20% | 28.08% |
| English route accuracy | 45.0% | 52.86% |
| Indonesian route accuracy | 38.0% | 40.0% |
| Unsupported false accepts | **0.0%** | **8.0% — fail** |
| Match latency p50 / p95 | 15.19 / 28.57 ms | 88.13 / 163.25 ms |

BGE-M3 is not selected because safety is a hard gate and its latency/resource cost is materially
higher. The comparison artifacts are `evaluation/b14_bge_m3_calibration_v1.json` and
`evaluation/b14_bge_m3_heldout_result_v1.json`. Multilingual E5 was not evaluated because it was not
available in the approved local Ollama inventory; no cloud model or new Python dependency was used.

The pre-existing B09 NASA-document retrieval result remains 90% Recall@5. B14 does not change NASA
document embeddings, chunks, retrieval ranking, citations, or answer generation, so no new RAG
Recall@K/MRR/nDCG or faithfulness improvement is claimed here.

## Commands and actual results

```text
.venv/bin/pytest -q tests/unit/test_b14_semantic_intent.py
10 passed

.venv/bin/pytest -q
378 passed, 1 skipped (379 collected)

.venv/bin/ruff check .
All checks passed!

.venv/bin/python evaluation/run_b14_semantic.py --surrogate
500 cases; non-release surrogate diagnostic recorded above

WILDFIRE_EMBEDDING_PROVIDER=ollama ... scripts/build_semantic_intent_index.py
published 32 examples; 384-dimensional ollama:all-minilm manifest

... evaluation/calibrate_b14_thresholds.py --output \
  evaluation/b14_all_minilm_calibration_v1.json
calibrated from 164 semantic-eligible development cases

... evaluation/run_b14_semantic.py --partition heldout --output \
  evaluation/b14_all_minilm_heldout_result_v1.json
290 held-out cases; real-model metrics reported above

ollama pull bge-m3; build/calibrate/evaluate in a separate bge-m3 collection
290 held-out cases; improved recovery but 8% unsupported false accepts; rejected
```

One third-party LangGraph pending-deprecation warning remains unchanged.

## Operator build and rollback

To reproduce the approved local profile:

```text
cd backend
WILDFIRE_EMBEDDING_PROVIDER=ollama \
WILDFIRE_EMBEDDING_MODEL_NAME=all-minilm \
.venv/bin/python scripts/build_semantic_intent_index.py

WILDFIRE_EMBEDDING_PROVIDER=ollama \
WILDFIRE_EMBEDDING_MODEL_NAME=all-minilm \
.venv/bin/python evaluation/calibrate_b14_thresholds.py \
  --output evaluation/b14_all_minilm_calibration_v1.json

WILDFIRE_EMBEDDING_PROVIDER=ollama \
WILDFIRE_EMBEDDING_MODEL_NAME=all-minilm \
.venv/bin/python scripts/build_semantic_intent_index.py \
  --calibration evaluation/b14_all_minilm_calibration_v1.json

WILDFIRE_EMBEDDING_PROVIDER=ollama \
WILDFIRE_EMBEDDING_MODEL_NAME=all-minilm \
.venv/bin/python evaluation/run_b14_semantic.py --partition heldout
```

Do not enable `guarded` until an improved strategy passes a fresh independent holdout, individual
corpus review, adversarial zero-call verification, and latency/resource review. Roll back by
setting `WILDFIRE_SEMANTIC_ROUTING_MODE=disabled`; do not delete or mutate the NASA RAG index.

## Open acceptance items

1. Independently review all expanded held-out cases and run semantic near-duplicate leakage analysis.
2. Improve or replace the intent embedding/example strategy without tuning against the consumed
   held-out set; create a new independently held-out version before the next acceptance measurement.
3. Meet 95% macro intent accuracy, 60% fallback reduction, 0%
   unsupported false accepts/forbidden calls, and 100% typed-slot/fixed-operation correlation.
4. Measure Qdrant startup, storage, memory, concurrency, and end-to-end p50/p95 latency.
5. Run representative local ClickHouse/Qdrant/Ollama end-to-end cases and feed results into Q01.

With Tech Lead approval on 2026-11-16, B14 is `DONE` as a no-adoption result. Semantic routing remains disabled by default, and release
approval remains blocked.
