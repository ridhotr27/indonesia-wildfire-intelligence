# I03 Execution Trace UI — Review Handoff

## Outcome

The chat UI now associates an initially collapsed, native `details` disclosure named
**How this answer was generated** with each successful assistant message that has a
validated API v1.1 execution trace. API v1.0 responses with an absent or null trace
render unchanged.

The disclosure presents the final route and status followed by ordered, plain-language
steps for analytics, retrieval, combined, and unsupported/abstained responses. It shows
only approved discriminated fields: resolved filters and their sources, stable read-only
operation identifiers, bounded counts, public local model/collection names, approved
retrieval metadata, citation-validation outcomes, durations, and abstention reasons.
It does not render arbitrary JSON, raw HTML, prompts, passages, vectors, SQL, topology,
credentials, exceptions, or hidden reasoning, and it cannot execute or reconstruct an
operation.

## Accessibility, responsive behavior, and safety

- Native `details`/`summary`, ordered lists, and definition lists provide semantic,
  collapsed disclosure and browser keyboard behavior without a custom focus model.
- Component tests verify the summary enters the tab order, starts collapsed, opens,
  and exposes each normative route's content.
- Long labels, model/collection names, filter values, and source titles wrap; definition
  rows collapse to one column below 420 px.
- Retrieved source links come only through the strict chat validator, require HTTPS,
  and use `target="_blank" rel="noopener noreferrer"`.
- The validator rejects extra fields, discriminator mismatches, unsafe URLs, excessive
  counts, response/trace filter divergence, ungrounded citation IDs, and model-call
  divergence before the response enters chat state. An invalid trace therefore fails
  closed as the existing dependency-unavailable chat error, rather than partially
  rendering untrusted provenance.
- The disclosure is purely presentational and makes no network or dependency call.

## Files

- `src/components/chat/execution-trace.tsx` — typed disclosure and step renderers.
- `src/components/chat/execution-trace.test.tsx` — four-route, compatibility,
  backend-order, safe-link, keyboard/semantic, and malicious-payload coverage.
- `src/components/chat/chat-panel.tsx` — per-assistant-message integration.
- `src/app/globals.css` — disclosure styling and narrow-width wrapping.
- Existing `src/lib/api/types.ts`, `validation.ts`, and their A02 contract tests are
  consumed without contract changes.

Tests consume both the canonical synthetic API v1.1 examples and
`backend/tests/fixtures/i03_execution_trace_backend.fixture.json`. These fixtures are
contract/runtime examples, not NASA observations or evidence that dependencies ran.

## Verification — 2026-11-07

Focused I03 and chat/contract suite:

```text
npm test -- --run src/components/chat/execution-trace.test.tsx \
  src/components/chat/chat-panel.test.tsx \
  src/lib/api/execution-trace-contract.test.ts
3 files passed; 11 tests passed
```

Full frontend checks:

```text
npm test
10 files passed; 34 tests passed

npm run typecheck
Passed (tsc --noEmit)

npm run lint
Passed (eslint .)

npm run build
Passed (Next.js 16.4.2 webpack production build; static `/` generated)
```

The build emitted a pre-existing environment warning that `NODE_ENV` has a non-standard
value; compilation, TypeScript, page generation, and trace collection still completed.

Browser application-chunk scan:

```text
rg -n -i '(password|passwd|secret[_-]?key|api[_-]?key|authorization:|bearer ...|
clickhouse://|qdrant://|ollama://|/Users/|raw_prompt|select ... from|insert into|
private[_-]?key)' .next/static/chunks/app
No matches
```

Generic framework/polyfill/MapLibre vendor chunks contain generic words such as
`password`, `/Users/`, and `insert into`; no application chunk contains a match. This
is a bounded pattern scan, not a dedicated secret or vulnerability audit.

## Limitations and readiness

No manual screen-reader, narrow-device browser, or local live ClickHouse/Qdrant/Ollama
smoke was run. Services were intentionally off, so no live timings are claimed. jsdom
does not emulate native keyboard toggling of `details`; the test verifies native
semantic markup and focusability, then opens it through the native click interaction.
No Playwright/browser E2E runner or dedicated vulnerability scanner is configured in
the frontend workspace.

Within those limits, the frontend implementation is technically ready for Tech Lead
review. This does not mark I03, Q01, or the release as approved or complete.
