# LIR-05 structured planner review

**Status:** IN_REVIEW  
**Date:** 2026-11-16

The isolated planner makes at most one loopback Ollama call to pinned `qwen2.5:1.5b`, temperature zero, using prompt `lir05-intent-planner-v1` and the strict LIR-04 JSON schema. It builds a bounded prompt from the original question, UI context, and static catalog-backed operation registry. Executable output must pass the LIR-04 validator; malformed, unknown, oversized, unavailable, timeout, denied, and incompatible output returns a reason-specific non-executable result. Logs contain only low-cardinality outcome, duration, model-call count, and prompt version.

Configuration defaults to disabled. The planner is not imported by application startup, LangGraph, or chat services.

Verification:

- Focused mocked planner suite: 12 passed in 0.11s.
- Full backend: 426 passed, 1 existing opt-in ClickHouse integration skipped in 5.79s.
- Repository Backend Ruff lint and changed-file format checks: passed.
- Live development benchmark (2026-11-16): all 480 approved LIR-01 variant-C cases executed against local Ollama 0.40.15 and `qwen2.5:1.5b`. Route accuracy and operation exactness were both 16.67% (80/480); outcomes were 342 `timeout`, 84 `invalid_structured_output`, and 54 `validation_rejected`. Planner latency was 8,003.33 ms p50 and 8,005.82 ms p95; maximum runner RSS was 132,755,456 bytes. The model was CPU-bound on a four-core Intel Core i5 machine with 8 GB RAM; Ollama reported a 1.2 GB loaded model and 100% CPU execution. Artifact: `backend/evaluation/lir05_variant_c_live_v1.json` (SHA-256 `ad337dedfb3060757967aaa1aa65bcde4bd4f22364e3891a4561cb6c0b8f5c92`).
- Model verification: Ollama ID `65ec06548149`; 1.5B Qwen2, Q4_K_M, 32,768 model context; Apache-2.0 license; model blob SHA-256 `183715c435899236895da3869489cc30ac241476b4971a20285b1a462818a5b4`. Planner configuration remained prompt `lir05-intent-planner-v1`, temperature zero, one call/no retry, 512 output tokens, 8-second timeout, and loopback-only endpoint.

The reusable evaluator consumes only LIR-01 development cases labeled for variant C, records route/operation accuracy, call counts, p50/p95 latency, and process RSS, and excludes raw questions/model output from results.

Acceptance result: **failed**. The live run supplies the previously missing identity, license, digest, quality, latency, and resource evidence, but the approved candidate is far below the documented quality thresholds and produces no accepted executable plan in this run. LIR-05 remains `IN_REVIEW`; do not approve or integrate this planner. A future authorized ticket must diagnose the timeout/structured-output failures and rerun the same development benchmark before any new candidate is considered.

## Prompt-v2 corrective sample (2026-11-17)

Prompt `lir05-intent-planner-v2` now consumes canonical metric/product IDs and the bilingual 38-province code mapping from the verified LIR-02 catalog, states route/operation compatibility, and includes one schema-valid example per route. Strict `IntentPlan` and validator behavior is unchanged. Planner results and evaluation artifacts now record bounded Pydantic/validator rejection codes without raw model output.

The focused LIR-01/LIR-04/LIR-05 suites passed 48 tests and changed-file Ruff passed. A representative 12-case English/Indonesian/mixed sample across analytics, RAG, combined, and clarification stopped early because all 12 calls reached the unchanged 8-second timeout. Ollama reported approximately 1,518 evaluated prompt tokens for the expanded catalog/example prompt. Route and operation accuracy were 25% only because fail-closed clarification coincided with the three expected clarification cases; valid-plan rate was 0%, timeout rate 100%, and latency was 8,004.21 ms p50 / 8,011.48 ms p95. Artifact: `backend/evaluation/lir05_prompt_v2_live_sample_v1.json` (SHA-256 `ad3218f7ff37e2a062ddc38194c7bff51928229548210ad4b23eeda07c8121f2`). LIR-05 remains `IN_REVIEW`; latency on the approved CPU profile is still the dominant blocker, so the full benchmark was not rerun.
