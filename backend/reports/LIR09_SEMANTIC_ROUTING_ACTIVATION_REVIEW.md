# LIR-09 Semantic Routing Activation Review

**Status:** DONE  
**Date:** 2026-11-17

## Decision and implementation

The user acting as Tech Lead accepted LIR-07's recorded 34.375% routing accuracy and 21.667% exact-operation accuracy as known limitations and authorized guarded semantic routing as the active default.

- `guarded` is now the default; `disabled` restores the previous deterministic routing strategy.
- The semantic intent index uses loopback Ollama `all-minilm` independently of the NASA RAG embedding provider.
- Deterministic denials/exact routes and the LIR-04 `ValidatedPlan` execution gate remain authoritative.
- Analytics, NASA RAG, combined, clarification, and unsupported outcomes remain inside the single bounded graph.
- Low-confidence semantic results clarify without tool calls. Missing semantic dependencies degrade to deterministic routing.
- Existing NASA retrieval and downstream Ollama answer generation are unchanged; no generative model performs routing.

## Verification

- Ruff: passed.
- Focused LIR-09/LIR-07/LIR-04/B04/B11/API regression set: 199 passed.
- Full backend suite: 461 passed, 1 existing opt-in skip.
- Existing benchmark artifacts were not modified and the final holdout was not consumed.

## Remaining limitations

The accepted routing and exact-operation accuracy remain below the original quality gates. This ticket does not authorize deployment or release.

## Tech Lead final acceptance — 2026-11-17

Approved `DONE` under the explicit decision accepting the measured routing limitations.
Independent inspection and regression reruns confirmed all five outcomes, deterministic
denial and LIR-04 execution precedence, zero-tool safe fallback, preserved downstream
generation, a bounded graph, and the `disabled` rollback path. This approval does not
approve deployment, release, or the final quality gate.
