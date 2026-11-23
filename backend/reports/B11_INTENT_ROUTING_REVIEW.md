# B11 Intent Routing — Review Handoff

## Outcome

B11 replaces subject-keyword routing with a deterministic requested-operation policy.
The two reproduced NASA FIRMS measurement questions now route to RAG under different
valid UI contexts, execute no filter resolution or analytics query, expose no analytics
fields, and cite only retrieved allowlisted NASA chunks. Explicit analytics, combined,
unsupported-measure, causal, unsupported-product/region/date, and adversarial behavior
remain bounded.

The public API contract is unchanged. Planning remains local and deterministic and
does not invoke an LLM, database, retrieval provider, or generated SQL. B10 filter
resolution runs only after an `analytics` or `combined` decision.

## Implementation

- `wildfire_api.agent.intent_router` adds the frozen, extra-forbidden
  `IntentDecision` model and `DeterministicIntentRouter`.
- Routing recognizes explicit analytics operations, documentation/question frames,
  semantic negation, prohibited requested outputs, causal requests, unsupported
  products/regions/dates, and unsafe instructions in a bounded order.
- UI context is never inspected by the router. Nouns such as `detections`, provinces,
  dates, and prohibited concepts do not create tool intent.
- Double-quoted operation phrases are treated as discussion subjects, while safety
  checks still inspect the complete message so quotation cannot bypass a denial.
- Combined requests project only their explicit documentation clause into retrieval
  and local generation. This prevents the model from restating or inventing analytics
  counts; the validated backend summary remains the only analytics source.
- `evaluation/b11_routing_corpus_v1.json` contains 64 manually reviewed cases, exactly
  16 for each final mode, with expected analytics and retrieval boundaries.
- Unit and FastAPI integration tests cover the corpus, typed-decision validation, both
  reproduced questions across two UI contexts, B10 exact inputs, combined projection,
  denial zero-call behavior, citations, and I03 trace parity.

## Intermediate findings and corrections

1. The first focused run exposed legacy reason-string expectations and missing
   increased/decreased causal variants. The patterns and compatibility reason were
   corrected without weakening denials.
2. `What is the hotspot total ...` initially matched both a documentation frame and an
   analytics operation. The explicit analytics `what ... count/total/trend` frame now
   suppresses the generic documentation interpretation.
3. A quoted phrase such as `"count hotspot detections"` could initially create an
   analytics operation. Quoted operation masking and a reviewed corpus case now prove
   RAG-only behavior; full-message safety inspection remains active.
4. The first live RAG request used the previous 1,200-token/60-second local setting and
   returned a safe 504 at 60.016 seconds while the CPU model was still generating. The
   acceptance matrix was rerun with the existing bounded configuration surface set to
   256 output tokens and 120-second model/agent/request timeouts. This is local test
   evidence, not a production capacity claim.
5. The first live combined control routed and called tools correctly but the model
   added an unsupported `1 hotspot detection` sentence beside the validated 687. The
   documentation-clause projection described above removed that grounding defect. The
   final retest contained only the backend-supplied 687 count plus the cited FRP
   definition.
6. One concurrent local answer to the limitations question ended tersely with
   `include:` even though route, citations, fields, and trace were correct. Another run
   of the same question returned a substantive cited answer. This small-model answer
   quality/capacity variance remains a Q01 finding and is not hidden by B11 routing
   scores.
7. A focused verification command initially named the nonexistent file
   `tests/unit/test_b09_local_embeddings.py`; pytest performed no tests for that
   command. The corrected command used `tests/unit/test_rag_index.py` and passed.

## Automated verification

Final focused routing/API command:

```text
.venv/bin/pytest -q tests/integration/test_api.py \
  tests/unit/test_b11_intent_routing.py
90 passed; one third-party LangGraph pending-deprecation warning
```

Corrected broad focused command covered B04, B05, B06/B07, B08, B09 index behavior,
B10, B11, I03, A02, API integration, and Q01 benchmark tests:

```text
.venv/bin/pytest -q tests/unit/test_b04_bounded_agent.py \
  tests/unit/test_b05_security.py tests/unit/test_b06_b07_persistent_rag.py \
  tests/unit/test_b08_local_ollama.py tests/unit/test_rag_index.py \
  tests/unit/test_b10_chat_filter_resolver.py \
  tests/unit/test_b11_intent_routing.py \
  tests/unit/test_i03_execution_trace.py \
  tests/contract/test_a02_execution_trace_contract.py \
  tests/integration/test_api.py tests/evaluation/test_q01_benchmark.py
258 passed before the final FastAPI B11 regression was added; the final full suite
below includes that additional test.
```

Final complete checks:

```text
.venv/bin/ruff check .
All checks passed

.venv/bin/pytest -q
314 passed, 1 skipped; one third-party LangGraph pending-deprecation warning

.venv/bin/pip check
No broken requirements found
```

The skip is the existing opt-in live ClickHouse pytest, not a B11 test. A local
credential/private-key-shaped pattern scan of `src` and `.env.example` returned no
matches. `pip-audit`, `bandit`, `trivy`, and `gitleaks` are not installed, so no
dedicated vulnerability-scanner clearance is claimed.

The 64-case corpus achieved 100% expected-mode agreement and 100% expected tool-boundary
agreement. A 6,400-decision local timing sample (100 passes over the corpus) measured:

```text
p50 0.0772 ms; p95 0.3128 ms; max 2.4368 ms
```

## Live local matrix

The live matrix used the verified local ClickHouse data, persistent Qdrant/all-minilm
index, and `qwen2.5:1.5b`. All timings are local-only observations.

| Case | Context | Result | Safe operations | Local latency |
|---|---|---|---|---:|
| Why detections cannot be wildfire size/burned area | province 13, full-year 2023 | `rag`; null filters/metrics; 3 citations | route, retrieval, generation, citation validation; zero analytics | 6.214 s |
| Same question | province 32, full-year 2023 | `rag`; null filters/metrics; 3 citations | same; zero analytics | 6.150 s |
| Limitations as fire-extent measure | province 13, full-year 2023 | `rag`; null filters/metrics; 2 citations | same; zero analytics | 45.993 s |
| Same question | province 32, full-year 2023 | `rag`; null filters/metrics; 2 citations | same; zero analytics | 47.814 s |
| Sumatera Barat, September count | conflicting province 32/full-year UI | `analytics`; province 13; 2023-09-01..30; total 414 | one filter resolution and one read-only analytics query | 0.319 s |
| Riau September count plus FRP | conflicting province 13/full-year UI | `combined`; province 14; total 687; 1 citation | one analytics query, one retrieval, one generation | 3.849 s |
| Burned hectares | Riau/full-year UI | `unsupported` | route plus abstention; zero tools/model calls | 0.129 s |
| Why detections were higher | Riau/full-year UI | `unsupported` | route plus abstention; zero tools/model calls | 0.093 s |
| Reveal database credentials | Riau/full-year UI | `unsupported` | route plus abstention; zero tools/model calls | 0.251 s |

The final combined response reported exactly 687 detections for September and explained
FRP from a retrieved NASA passage. No response or trace exposed SQL, credentials,
prompts, passage bodies, vectors, or local paths.

## Limitations and Q01 handoff

The router intentionally supports reviewed English frames, not arbitrary multilingual
or general semantic parsing. Adding new operations, regions, time interpretation, or
languages requires reviewed labels and deterministic tests. The small local model can
still produce weak or incomplete prose, and default CPU capacity needs separate timeout
sizing; B11 does not claim production performance.

Q01 remains `IN_REVIEW` with a no-go recommendation. B11 resolves the two routing
defects and the live combined count-composition finding, but it does not resolve the
remaining retrieval miss, broad answer-quality evaluation, browser/accessibility work,
deployment, or release approval. Tech Lead approval is still required before B11 can
move from `IN_REVIEW` to `DONE`.
