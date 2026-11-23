# B04 — Bounded LangGraph agent and `/chat` review

**Owner:** Backend Engineer agent `/root/b04_be`  
**Technical status:** `IN_REVIEW`  
**Approval status:** Not approved; only the Tech Lead may mark B04 `DONE`.  
**Date:** 2026-10-23

## Summary

B04 replaces the transparent chat scaffold with one bounded LangGraph state graph.
It routes analytics, NASA-document retrieval, combined, and unsupported requests to
typed deterministic tool adapters. It never accepts SQL text, never creates runtime
sub-agents, and does not activate an LLM or paid service.

The default planner is deterministic and reports `llm_calls: 0`. Provider and model
names remain optional server-side configuration for a future approved implementation.
The graph enforces six steps, two tool calls, 1,200 future model tokens, 6,000 retrieved
characters, and an eight-second deadline by default. All ceilings are server-side and
validated. B05 still owns public quotas, concurrency middleware, logging/redaction
operations, and production security policy.

Analytics calls the approved B02 service through a structured input containing only
product, province, and dates. Counts, filters, and chart series are copied from the
validated `SummaryResponse`; request ID, product, metric, province, dates, source
status, and provider must match the tool request before the composer sees a result.
Retrieval calls the B03 interface with a bounded query and limit, revalidates every
passage, and accepts citations only from approved HTTPS NASA hosts with B03-format
document/chunk IDs, SHA-256 content hashes, timezone-aware retrieval timestamps, and
`untrusted_content=true`. Retrieved text is never copied into the generated answer or
interpreted as instructions.

Burned-area, confirmed-fire, causal, predictive, unsupported product/date/region, and
prompt-injection requests abstain without calling tools. Missing context or retrieval
configuration also produces an honest typed response without fabricated evidence.
Malformed tool output and dependency outages fail closed with A01 typed errors.

## Files changed

- `backend/.env.example`
- `backend/README.md`
- `backend/pyproject.toml`
- `backend/src/wildfire_api/agent/__init__.py`
- `backend/src/wildfire_api/agent/runtime.py`
- `backend/src/wildfire_api/agent/state.py`
- `backend/src/wildfire_api/core/config.py`
- `backend/src/wildfire_api/main.py`
- `backend/src/wildfire_api/services/chat.py`
- `backend/tests/integration/test_api.py`
- `backend/tests/unit/test_agent_scaffold.py` (removed; superseded by B04 tests)
- `backend/tests/unit/test_b04_bounded_agent.py` (new)
- `backend/reports/B04_BOUNDED_LANGGRAPH_REVIEW.md` (new)

No `docs/`, `data/`, `frontend/`, infrastructure, shared contract, or OpenAPI snapshot
was changed.

## Verification evidence

Commands were run from `backend/` with the existing `.venv`.

1. `.venv/bin/pip install -e '.[dev,rag,agent]'`
   - Initial sandboxed attempt failed because dependency resolution could not reach the
     package index. The approved network-enabled retry succeeded and installed
     LangGraph 0.6.11. B04 then moved LangGraph into the required application
     dependencies, so the obsolete `agent` extra no longer exists.
2. `.venv/bin/pytest tests/unit/test_b04_bounded_agent.py tests/integration/test_api.py -q`
   - First implementation run failed during collection because `agent/__init__.py`
     still exported the removed scaffold. The export was corrected.
   - Next run: **6 failed, 23 passed**. Five failures were assertions checking a
     substring as an exact list member. One was a real plural-keyword routing defect:
     `limitations` selected analytics rather than combined mode. The classifier and
     assertions were corrected.
   - Corrected run: **30 passed**.
3. `.venv/bin/ruff check .`
   - First run after implementation reported eight long lines and one import-order
     issue. Targeted formatting/import fixes were applied.
   - Final result: **All checks passed**.
4. `.venv/bin/pytest -q`
   - Final complete backend regression: **93 passed**.
5. `.venv/bin/pytest tests/unit/test_b04_bounded_agent.py tests/integration/test_api.py -q`
   - Final focused B04/API result after step/timeout/token tests: **33 passed**.

### Independent-review fixes

Independent review withheld approval and identified four fail-closed blockers. The
implementation and tests were corrected without changing A01, B03, or shared files:

1. Tool-call budget is now reserved before each external invocation. A combined flow
   with a one-call ceiling invokes analytics once and proves through the retrieval spy
   that the second tool is never called.
2. The bounded deterministic classifier now covers explicit inflected causal forms
   such as `why were`, `explain why`, `causal`, and `attribute`, plus additional
   explicit unsupported countries including Brazil. This is a finite v1 rule set, not
   a claim of general natural-language geography understanding.
3. A valid-shape analytics response fails closed unless its request ID, metric,
   product, exact single-province filter, date range, source status, and expected
   provider match the structured tool request.
4. Retrieved passages fail closed before citation unless URL authority, HTTPS scheme,
   untrusted flag, SHA-256 content hash, SHA-256 stable chunk ID, B03 document ID,
   section/title, and timezone-aware retrieval timestamp satisfy B03 provenance rules.

Review-fix verification:

- First corrected focused run:
  `.venv/bin/pytest tests/unit/test_b04_bounded_agent.py tests/integration/test_api.py -q`
  — **52 passed**.
- Final complete regression after the additional provider/document/timestamp cases:
  `.venv/bin/pytest -q` — **115 passed**.
- Final focused B04/API rerun:
  `.venv/bin/pytest tests/unit/test_b04_bounded_agent.py tests/integration/test_api.py -q`
  — **55 passed**.
- Final lint: `.venv/bin/ruff check .` — **All checks passed**.

### Final classifier re-review

Final re-review found one remaining high-severity fail-closed gap: finite causal and
country lists missed present-perfect/past-perfect forms (`why have` / `why had`),
`explain what led to`, Germany, France, and other explicit unknown prose geography.
The same review also found that the broad `attribute` stem would incorrectly abstain
valid NASA field/source-attribution documentation questions.

The planner now separates unsupported measures from causal intent, treats any `why`
question and explicit causal constructions as unsupported, and recognizes
`explain what led to`, reasons/drivers/due-to, and only the causal form `attribute ...
to`. Scientific questions about the confidence/FRP attributes and NASA source
attribution remain RAG requests.

Analytics still requires the typed A01 product, province, and date context at the
tool boundary. In addition, explicit prose location cues (`in`, `within`, `across`,
or `for`) fail closed unless they identify Indonesia, one of the approved canonical
38 province names, a bounded temporal phrase, or the selected/current province.
Known explicit foreign countries include Germany and France. Unknown cue phrases such
as Bavaria or Europe also abstain. This is intentionally a conservative structured
policy, not a claim of general named-entity recognition.

Table-driven tests assert unsupported mode, zero analytics calls, zero retrieval
calls, and an honest causal or geography limitation for tense/inflection and location
variants. Positive regressions cover Riau, selected-province and September analytics,
plus confidence attribute, FRP attribute, and source-attribution RAG questions.

- Focused final-classifier run:
  `.venv/bin/pytest tests/unit/test_b04_bounded_agent.py tests/integration/test_api.py -q`
  — **69 passed**.
- Complete backend regression: `.venv/bin/pytest -q` — **129 passed**.
- Final lint: `.venv/bin/ruff check .` — **All checks passed**.
- The previously recorded third-party LangGraph pending-deprecation warning remains;
  no new warning or project failure was introduced.

Pytest reports one third-party `LangChainPendingDeprecationWarning` from LangGraph's
serializer default. It is retained as a warning rather than hidden; no application
failure or deprecated project API was observed.

Coverage includes deterministic analytics, RAG, combined, and unsupported routing;
exact numeric/schema grounding; stable citation propagation; prompt injection in user
and retrieved content; unsupported burned-area/confirmed-fire/causal/prediction/
product/year/region claims; malformed planner and tool output; missing context and RAG
dependency; tool-call, graph-step, timeout, retrieved-context, input, and model-token
bounds; mismatched analytics identity/source fields; invalid HTTP/non-NASA citation
URLs, weak hashes/IDs, trusted-content flags, missing metadata; and API-level
analytics/citation responses.

## Limitations and risks

- The safe default analytics repository remains synthetic. B04 does not claim live
  NASA/ClickHouse results; D06 and I01 own that integration and parity evidence.
- A B03 index must be injected server-side. The default app abstains on RAG questions
  rather than fetching/indexing NASA documents during API startup.
- The deterministic planner intentionally handles a bounded v1 vocabulary. It does
  not extract arbitrary provinces/dates from prose; A01 typed context remains the
  authoritative analytics input.
- No live model/provider benchmark, token consumption, answer-quality metric, or cost
  result is claimed. The explicit model-token ceiling is dormant while `llm_calls=0`.
  Provider selection and any paid activation still require the documented approval.
- Retrieval answers intentionally direct users to cited NASA evidence rather than
  paraphrasing untrusted passage text. Q01 owns retrieval and citation-support quality
  measurement.
- Public quotas, concurrency controls, operational telemetry, and hardened production
  timeouts remain B05; this ticket implements only per-run graph/tool/context/deadline
  safety needed by the runtime itself.

## Handoff

B04 is technically ready for independent review and Tech Lead approval. It is not
`DONE`. If approved, B05 becomes eligible to start. I02 additionally remains blocked
on I01 and its other recorded dependencies.
