# LIR-06 context and rewrite review

**Status:** IN_REVIEW  
**Date:** 2026-11-16

The bounded resolver preserves the original message and reuses `ChatFilterResolver` for current-message-over-UI precedence. It records canonical province/date provenance, detects English/Indonesian follow-up frames and unbound references, and requires clarification when an operation or referent depends on unavailable history.

`PlanContextValidator` verifies every executable planner entity against the canonical current/UI source, including provinces, dates, metric, product, dimensions, direction, ranking limit/selection, and comparison intent. UI values overridden by the current message cannot re-enter execution. The schema continues to reject `user_history` provenance.

`RetrievalRewriteValidator` permits only bounded NASA retrieval queries that preserve canonical provinces, dates/numbers, product terms, negation, unsupported-measure wording, and topic overlap. Rewrites never produce analytics parameters and are not integrated into runtime.

Verification:

- Focused LIR-06: 24 passed in 0.12s.
- LIR-04/LIR-05/B10 focused regression: 135 passed in 0.55s before the final ranking-boundary addition.
- Full backend: 450 passed, 1 existing opt-in ClickHouse integration skipped in 5.93s.
- Backend Ruff and changed-file formatting: passed.

No public API, history field, LangGraph/runtime path, dependency, model, query, or frontend changed. Under the LIR-03 deferral, true multi-turn carry-over remains intentionally unavailable and gated. LIR-06 remains in review because LIR-05 has not passed its required live benchmark and therefore is not a `DONE` dependency. The existing Papua-code mismatch remains a separate integration risk.
