# B05 — Quotas, timeouts, logging, and security controls

**Status:** DONE by explicit user/Tech Lead direction on 2026-10-26  
**Dependency:** B04 DONE

## Delivered controls

- Server-side per-client and process-global fixed-window request quotas with typed
  `429 RATE_LIMITED` responses and `Retry-After`.
- Immediate concurrency rejection rather than an unbounded wait queue.
- A hard ASGI request deadline with a safe typed `504 REQUEST_TIMEOUT` response.
- Actual-body and declared-body limits, including requests without `Content-Length`.
- Explicit-origin CORS; wildcards and path/query/fragment origins fail closed.
- HMAC-pseudonymous peer identifiers, with a required server-side salt in production.
- Structured operational logs for request status/duration/dependency state and bounded
  agent graph/tool/LLM usage, result size, and zero current model cost.
- Credential/content redaction and safe unexpected-error logging without stack traces or
  exception text in client responses.
- Existing B02 read-only query catalog, `readonly=2`, parameter binding, execution timeout,
  and row caps remain unchanged; B04 graph/tool/context/model ceilings remain enforced.

Configuration and deployment notes are in `backend/.env.example` and `backend/README.md`.

## Verification performed

```text
backend/.venv/bin/python -m pytest backend/tests/unit/test_b05_security.py -q
8 passed

backend/.venv/bin/python -m pytest backend
137 passed, 1 third-party LangGraph pending-deprecation warning

backend/.venv/bin/ruff check backend/src backend/tests
All checks passed

backend/.venv/bin/python -m py_compile \
  backend/src/wildfire_api/core/config.py \
  backend/src/wildfire_api/core/logging.py \
  backend/src/wildfire_api/core/security.py \
  backend/src/wildfire_api/main.py
passed (no output)
```

The focused tests cover per-client/global quota behavior and reset, health availability
under exhausted user quota, concurrency rejection, payload rejection, wall-clock timeout,
CORS allow/deny behavior, log redaction, and production salt enforcement. The full suite
retains the existing dependency-outage, graph/tool cap, read-only query, safe error, and
contract coverage.

## Explicit limitations

- Rate and concurrency state is process-local. Multi-worker or multi-host deployment must
  use a shared atomic store before claiming truly deployment-global quotas.
- Provider-side spending ceilings must be configured with the selected provider; no paid
  model/provider is enabled, so observed token use and estimated model cost are zero.
- Public authentication remains a Lead deployment decision. B05 identifies clients
  pseudonymously and limits abuse but does not invent an account system.
- This work does not claim live D06-to-BE parity; that remains I01.
