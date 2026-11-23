# LIR-10 Combined Execution and Recovery Review

**Status:** DONE  
**Date:** 2026-11-17

## Scope and dependency decision

The user explicitly authorized LIR-10 implementation while LIR-08 and LIR-09 remain
`IN_REVIEW`. Their runtime behavior and tickets were not changed. The implementation
preserves the single bounded graph, two-tool limit, LIR-04 validation, parameterized
ClickHouse adapters, existing Ollama generation, and public API contract.

## Combined behavior

| Analytics branch | Documentation branch | Result |
|---|---|---|
| success | success | Exact server-composed analytics plus grounded generated context and supplied-passage citations |
| success | retrieval empty/failure/timeout | Exact analytics retained; no citations; explicit documentation limitation; partial trace |
| success | generation rejected/failure/timeout | Exact analytics and retrieved NASA source metadata retained; no model claim accepted; partial trace |
| invalid/missing/failure/timeout | success | No analytics number; model generation is skipped; retrieved NASA sources and explicit analytics limitation retained |
| failure | failure | No fabricated result or citation; safe insufficient-evidence response |

Runtime validation rejects generated hotspot-count claims that differ from exact tool
outputs and rejects every generated citation outside the supplied passage set. Zero,
null/unavailable, warnings, coverage, province ties, and exclusions remain server-owned.
Attempted dependency calls continue to count against the two-tool budget.

## Verification

- `ruff check .`: passed.
- LIR-10 focused: 9 passed.
- B08/B11/B13/I03/LIR-09/API/A02/A03 regression set: 167 passed.
- Full backend suite: 478 passed, 1 existing opt-in skip, 1 existing LangGraph pending-deprecation warning.
- Final holdout was not consumed. No live benchmark, deployment, or release was performed.

## Remaining risks

The outer workflow deadline remains the final hard stop for planning, composition, and
any cancellation-resistant provider call. Combined stages now reserve composition time
and cancel their awaited coroutine directly without detached asyncio tasks; synchronous
provider work delegated through the existing `to_thread` boundary remains bounded by
its provider timeout and is assigned to live failure injection in LIR-11. Live
ClickHouse/Qdrant/Ollama failure injection remains release evidence for LIR-11/LIR-12.

## Project Lead review — changes requested

LIR-10 remains `IN_REVIEW`; it is not approved `DONE`.

1. The outer `asyncio.timeout` raises `REQUEST_TIMEOUT` without retaining an analytics
   result completed earlier in a combined request. Add internal branch deadlines that
   reserve bounded time for composition, then test a genuinely sleeping dependency.
2. Generated-output integrity currently rejects conflicting hotspot counts, but it
   does not prove that generated prose cannot alter rankings or coverage. Add explicit
   adversarial rank/coverage tests and a deterministic rejection boundary.
3. Combined multi-province/ranking execution uses `province_analytics_tool_input`, but
   the v1 execution trace serializes only single-summary analytics. Without changing
   the public contract, prove correlation through the existing A03
   `province_analytics.execution` object and ensure the generic trace never reports a
   false operation.

### Remediation plan

- **Scope/files:** `agent/runtime.py`, `agent/execution_trace.py`, state only if needed,
  focused LIR-10 tests, this report, and ticket evidence. No router, LIR-04, SQL, API,
  dependency, or tool-budget change.
- **Tests:** completed-analytics plus sleeping RAG/model; sleeping analytics plus valid
  RAG; exact zero/null/partial/tie/ranking/exclusion identity; conflicting generated
  count/rank/coverage; citation subset; A03/trace correlation; B08/B13/I03/LIR-09/API
  regressions and full backend checks.
- **Risk/rollback:** keep existing whole-workflow timeout as the final hard stop; use
  internal stage budgeting only for combined requests. A single internal switch or
  reverting the bounded stage budget must restore current behavior without changing
  deterministic routing, validation, or response schemas.

## Remediation implementation — ready for independent review

- Combined analytics, retrieval, and generation now receive bounded stage budgets
  inside the unchanged outer deadline. A reserved composition window preserves any
  completed validated branch. The implementation awaits and cancels stages directly;
  it creates no detached asyncio tasks.
- `WILDFIRE_AGENT_COMBINED_STAGE_BUDGETING=false` restores the prior whole-workflow-only
  deadline behavior without changing routing, validation, tool limits, or API schemas.
- Generated documentation is rejected when it attempts to restate province ranking or
  ordering, conflicts with authoritative coverage state/gaps, changes hotspot counts,
  or cites a chunk outside supplied passages. Rejection retains deterministic analytics
  and does not invent replacement prose.
- A03 province analytics are parsed through the approved strict contract and checked
  against the exact typed tool input before their source and execution provenance are
  retained. The generic v1 trace records route/partial status and never fabricates a
  single-summary operation for province/ranking work; A03 execution remains the typed
  operation/source record in the same response.

### Remediation verification

- `ruff check .`: passed.
- LIR-10 focused remediation: 19 passed.
- B04/B08/B13/I03/LIR-09/API/A02/A03 regression set: 161 passed.
- Full backend suite: 488 passed, 1 existing opt-in skip, 1 existing LangGraph
  pending-deprecation warning.
- The final holdout was not consumed. No live dependency matrix, deployment, or release
  was performed. LIR-10 remains `IN_REVIEW` pending independent approval.

## Tech Lead final acceptance — 2026-11-17

Approved `DONE`. Independent inspection confirmed the unchanged hard workflow deadline,
bounded direct cancellation without detached tasks, preservation of validated partial
branches, strict count/rank/order/coverage/citation rejection, and typed A03
operation/source correlation without a fabricated generic trace operation. The rollback
switch restores whole-workflow-only timeout behavior; provider work remains bounded by
configured timeouts. Ruff and the full backend suite were rerun successfully: 488 passed,
1 existing opt-in skip, and 1 existing LangGraph pending-deprecation warning. API
contracts, routing behavior, LIR-04 validation, and the two-tool limit remain unchanged.
Live dependency failure injection remains LIR-11 scope, not an LIR-10 blocker.
