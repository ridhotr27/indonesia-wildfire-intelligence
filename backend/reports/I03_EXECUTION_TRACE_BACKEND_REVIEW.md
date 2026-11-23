# I03 Execution Trace Backend — Review Handoff

## Outcome

The chat runtime now returns the approved optional API 1.1 execution trace on every
successful chat response. Trace construction is a pure serialization step over facts
already recorded by the bounded graph. It cannot invoke analytics, Qdrant, Ollama,
network, or filesystem operations.

Analytics traces use the stable read-only `hotspot_summary_v1` operation identifier.
Their parameters are constructed from the exact `AnalyticsToolInput` that B10 sent to
the service and are validated against top-level response filters. Retrieval exposes
only ranked citation metadata; generation exposes bounded provider/model/count facts;
and citation validation reports accepted counts without passage bodies. Unsupported
responses contain no invented analytics, retrieval, or model operations.

## Runtime facts and safety

- Steps are contiguous and reflect graph order: final route, optional filter
  resolution, analytics, retrieval, local generation, citation validation, and/or
  abstention.
- Durations use a monotonic clock around the operation that already occurs and are
  bounded by the approved schema.
- Runtime configuration supplies public display names for the embedding model,
  collection, and generation model; internal URLs and local storage paths are absent.
- The existing schema rejects mismatched detail discriminators, non-contiguous
  sequences, filter divergence, citation IDs outside retrieval results, model-call
  divergence, non-HTTPS citation metadata, extra fields, and out-of-bound counts.
- HTTP dependency/timeout errors continue to use error envelopes and never serialize a
  trace. Trace construction adds no dependency call or retry.

## Frontend handoff

The canonical response examples remain
`docs/fixtures/api_contract_v1.1.0.execution_trace.fixture.json`. The supplemental
backend fixture `tests/fixtures/i03_execution_trace_backend.fixture.json` gives FE the
runtime step ordering and stable display identifiers. FE should render only typed
fields, treat `execution_trace` as optional/null for v1.0 compatibility, and never
execute or reconstruct calls from the display data.

## Verification (2026-11-07)

Focused I03 plus B02/B04/B05/B08/B10 and A02 contract suite:

```text
.venv/bin/pytest tests/unit/test_i03_execution_trace.py \
  tests/contract/test_a02_execution_trace_contract.py \
  tests/unit/test_b02_clickhouse_repository.py \
  tests/unit/test_b04_bounded_agent.py tests/unit/test_b05_security.py \
  tests/unit/test_b08_local_ollama.py tests/unit/test_b10_chat_filter_resolver.py -q
173 passed; one third-party LangGraph pending-deprecation warning
```

The complete backend suite (including B06/B07/B09, integration, contract, OpenAPI,
evaluation, and security regression tests):

```text
.venv/bin/pytest -q
237 passed, 1 skipped; the skipped I01 test requires opt-in live ClickHouse credentials
```

Static and local security checks:

```text
.venv/bin/ruff check src tests
All checks passed

.venv/bin/pip check
No broken requirements found

Allowlisted secret-pattern scan of src and .env.example
No matches
```

Dedicated dependency-vulnerability scanners (`pip-audit`, `bandit`, `trivy`, and
`gitleaks`) are not installed in this workspace, so no vulnerability-cleared claim is
made. The full suite emitted one third-party LangGraph pending-deprecation warning.

## Limitations

The trace is request-local display provenance, not a distributed tracing or audit-log
system. Millisecond durations can be zero for fast local operations. A live I01 query,
live Qdrant retrieval, and live Ollama generation were not run because services and
opt-in credentials were unavailable; deterministic fakes verify exact runtime
instrumentation and zero additional calls.
