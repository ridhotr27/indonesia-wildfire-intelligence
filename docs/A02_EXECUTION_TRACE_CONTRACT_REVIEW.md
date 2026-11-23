# A02 execution-trace contract review

**Decision requested:** Approve API schema v1.1.0 as an additive minor version under
`/api/v1`. This record does not self-approve A02 and does not authorize I03 runtime or
UI work.

## Review result

The proposal adds only optional nullable `ChatResponse.execution_trace`. Existing
v1.0.0 chat payloads parse unchanged. The trace is a bounded, strict, discriminated
execution-provenance record; it is not planner narration or chain-of-thought. Backend
and frontend validators reject unknown trace fields, mismatched discriminators,
non-contiguous sequences, more than eight steps, more than five retrieval items, and
out-of-range counts/durations.

Four synthetic fixtures cover analytics, local RAG, combined execution, and safe
abstention. Cross-field validation requires analytics parameters to match top-level
filters, trace route to match response mode, model-call totals to match usage, and
citations to be a subset of retrieved chunk IDs. The fixture scan prohibits debug,
credential, SQL, prompt, passage, vector, and path-shaped content and bounds the
serialized fixture below 50 KB.

## Compatibility and security assessment

- Compatible: field absent, field null, and valid field-present responses.
- Fail closed: extra fields, unknown kinds, mismatched detail kinds, oversized arrays,
  unsafe URL schemes, and inconsistent response/trace facts.
- No new browser dependency access and no change to error envelopes.
- No runtime instrumentation, extra operations, or UI was implemented under A02.
- Public model and collection values are display metadata, bounded to 100 characters;
  they cannot select backend resources.

## Approval boundary

The Tech Lead must explicitly approve the shared v1.1.0 contract before A02 is `DONE`
or I03 uses it at runtime. If `execution_trace` becomes required or changes existing
response semantics, this minor proposal must be rejected in favor of a major version.

## Verification evidence

Executed from the repository root unless the command starts in `frontend/`:

- `backend/.venv/bin/pytest backend/tests/contract/test_a01_api_contract.py backend/tests/contract/test_a01_openapi_snapshot.py backend/tests/contract/test_a02_execution_trace_contract.py`
  — 18 passed; one third-party LangGraph pending-deprecation warning.
- `backend/.venv/bin/ruff check backend/src/wildfire_api/schemas/chat.py backend/tests/contract/test_a02_execution_trace_contract.py`
  — passed.
- `npm test -- src/lib/api/contract-fixture.test.ts src/lib/api/execution-trace-contract.test.ts`
  from `frontend/` — 7 tests passed in 2 files.
- `npm run typecheck` from `frontend/` — passed.
- `npm run lint` from `frontend/` — passed.

These are contract-only checks. No live ClickHouse, Qdrant, Ollama, NASA network,
browser, runtime instrumentation, or UI verification was performed or claimed.
