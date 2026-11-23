# LIR-11 Security, Contract, and Degraded-Mode Review

**Status:** DONE  
**Date:** 2026-11-17

## Scope and boundaries

LIR-11 adds verification only. Runtime code, public API schemas, routing, LIR-04
validation, query templates, and the two-tool limit are unchanged. No final holdout,
production dependency, deployment, or production configuration was used. The live matrix
started process-owned HTTP failure endpoints on ephemeral `127.0.0.1` ports and used a
temporary local Qdrant path.

## Observed failure matrix

| Dependency/failure | Expected | Observed |
|---|---|---|
| ClickHouse connection | Safe typed unavailability | `DEPENDENCY_UNAVAILABLE`; 152.64 ms |
| ClickHouse timeout | Bounded safe timeout | `REQUEST_TIMEOUT`; 65.49 ms with 50 ms provider bound |
| Ollama connection | Safe model fallback | `MODEL_UNAVAILABLE`; 19.50 ms |
| Ollama timeout | Bounded safe fallback | `MODEL_UNAVAILABLE`; 51.46 ms with 50 ms provider bound |
| Qdrant missing index | Fail closed | `INDEX_UNAVAILABLE`; no silent rebuild |
| Qdrant retrieval failure in combined flow | Preserve analytics | Exact count retained; no citation; partial trace |
| Ollama generation failure in combined flow | Preserve validated branches | Exact count and supplied citation retained; model prose rejected; partial trace |

The committed deterministic matrix also injects `httpx` connection/timeout exceptions,
Ollama URL/timeout exceptions, missing/corrupt Qdrant manifests, unsafe input, rollback
settings, and provider upper bounds. Responses and logs contain no injected credential,
raw attack text, SQL, traceback, prompt, passage body, vector, or chain-of-thought.

## Verification

- `ruff check .`: passed.
- LIR-11 focused: 9 passed.
- Security/contract/provider/LIR-04/LIR-09/LIR-10 regressions: 247 passed.
- Full backend suite: 497 passed, 1 existing opt-in live ClickHouse skip, 1 existing
  LangGraph pending-deprecation warning (498 collected).
- `pip check`: no broken requirements.
- Report/evaluation forbidden-content scan: no matches.
- Isolated live command: `.venv/bin/python scripts/validate_lir11_live_failures.py`;
  passed with the observations above.

## Rollback and degraded mode

- `WILDFIRE_SEMANTIC_ROUTING_MODE=disabled` restores deterministic routing.
- `WILDFIRE_RAG_RETRIEVAL_PROFILE=dense`, the B09 Qdrant path, and its matching recursive
  chunk profile restore the evaluated dense retriever.
- `WILDFIRE_AGENT_COMBINED_STAGE_BUDGETING=false` restores whole-workflow-only budgeting.
- Missing/incompatible Qdrant remains a startup failure when local RAG is explicitly
  enabled; semantic-index failure degrades to deterministic routing; provider failures
  return typed limitations without fabricating analytics or citations.

## Remaining risks

The isolated matrix validates real network behavior through production clients but does
not kill shared ClickHouse/Qdrant/Ollama processes, by design. Sustained concurrency,
resource exhaustion, and a representative healthy-to-failed-to-recovered local dependency
matrix remain LIR-12 release evidence. The existing opt-in live ClickHouse parity test
remains skipped when no approved isolated service is configured.

## Tech Lead final acceptance — 2026-11-17

Approved `DONE`. Independent review reran Ruff, dependency integrity, the 247-test
security/contract/provider regression set, the full 497-pass/one-skip backend suite, and
the process-owned loopback matrix. The repeated live observations were: ClickHouse safe
connection failure in 178.34 ms and bounded timeout in 73.15 ms; Ollama safe connection
failure in 22.01 ms and bounded timeout in 51.59 ms; missing temporary Qdrant failed
closed. Static inspection confirmed loopback-only ephemeral binding, temporary storage,
sanitized results, unchanged runtime/configuration/API code, LIR-04 and two-tool
boundaries, and documented rollback. The existing warning and opt-in ClickHouse skip are
accepted as unrelated. Sustained load and healthy-to-failed-to-recovered representative
services remain LIR-12 release evidence, not LIR-11 blockers. No final holdout or
deployment occurred.
