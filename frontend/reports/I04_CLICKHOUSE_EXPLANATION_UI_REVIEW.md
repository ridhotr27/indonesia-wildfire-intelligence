# I04 ClickHouse Answer Explanation UI — Review Handoff

## Outcome

The existing collapsed **How this answer was generated** disclosure now contains an
additional **How the data became this answer** section for analytics and combined
responses when a validated execution trace and validated dashboard metadata are both
available.

The section presents a semantic six-stage flow:

1. request route;
2. resolved province/date filters and whether they came from the message or dashboard;
3. a non-executable display signature built from the allowlisted operation ID and typed
   filters;
4. the verified fixed read-only ClickHouse path, or a clearly synthetic repository path;
5. normalized monthly periods, coverage handling, exact response metric, and recorded
   duration; and
6. the boundary between deterministic analytics and any local documentation generation.

For verified metadata, the UI explains that FastAPI bound validated filters to
server-owned parameterized read-only ClickHouse reads for monthly counts and coverage.
It does not describe `returned_rows` as physical database rows; it labels the field
**Monthly periods in result**, matching the backend service's normalized
`summary.series` semantics. For mock metadata, the UI names only the synthetic
repository and contains no `ClickHouse` text.

## Truthfulness and consistency boundaries

- The browser still calls FastAPI only. No ClickHouse, Qdrant, Ollama, or NASA request
  was added.
- The detailed lineage requires an executed `analytics_query` trace step; an analytics
  route alone cannot create the explanation.
- ClickHouse is named only when `metadata.data_status` and
  `metadata.source.data_status` are both `verified`.
- The approved-operation description is selected only by the typed allowlisted
  `operation_id`. The display signature is constructed locally from typed filters and
  is labeled **Approved operation**, never SQL.
- Analytics trace parameters must equal top-level response filters. I04 additionally
  fails closed when the trace metric name/value differs from the top-level metric, or
  when a supplied chart's normalized series length differs from `returned_rows`.
- Structured chart coverage dates are displayed without recomputing completeness. A
  numeric partial result is described as the observed subtotal retained for available
  periods; a null result says no numeric total is supportable. With no structured issue,
  the UI says only that the backend checked coverage.
- Analytics-only responses say **No LLM generated or changed this number** only when
  `usage.llm_calls` is zero and no completed generation step exists.
- Combined responses say the model could explain/cite documentation without changing
  the metric only when a completed local-generation step exists. RAG-only and
  unsupported traces retain the I03 execution record and never show analytics lineage.
- Field-absent/null traces remain unchanged. Missing or inconsistent metadata omits the
  provider-specific lineage rather than guessing.

## Security and accessibility

- Response-controlled execution labels are no longer rendered. Static labels are keyed
  only by the allowlisted step kind, so a forged label containing SQL, credentials,
  paths, or HTML cannot enter the visible execution record.
- React text rendering is used throughout; no raw HTML, executable widget, SQL console,
  or copy-to-run control exists.
- Retrieval URLs remain HTTPS-only and now reject localhost, `.local`, loopback,
  link-local, and RFC1918 IPv4 hosts before rendering.
- Existing exact-key trace validation continues to reject prompts, passages, vectors,
  debug objects, and discriminator mismatches.
- The native `details`/`summary` disclosure remains collapsed, keyboard focusable, and
  associated with the answer. The lineage is a semantic section with a named heading,
  ordered list, and definition lists.
- Flow fields use min-width constraints and `overflow-wrap`; below 420 px, the flow and
  metadata rows collapse to one column without an intentional horizontal scroll.

## Files changed

- `src/components/chat/execution-trace.tsx`
- `src/components/chat/execution-trace.test.tsx`
- `src/components/chat/chat-panel.tsx`
- `src/components/dashboard/dashboard.tsx`
- `src/lib/api/validation.ts`
- `src/lib/api/execution-trace-contract.test.ts`
- `src/app/globals.css`
- `reports/I04_CLICKHOUSE_EXPLANATION_UI_REVIEW.md`

No backend or shared contract file was changed.

## Verification — 2026-11-12

Focused I04/I03 chat and contract run:

```text
npm test -- --run src/components/chat/execution-trace.test.tsx \
  src/components/chat/chat-panel.test.tsx \
  src/lib/api/execution-trace-contract.test.ts

3 files passed; 22 tests passed
```

The focused cases cover verified analytics, mock analytics, combined separation,
RAG-only, unsupported, absent/null trace compatibility, missing/inconsistent metadata,
structured coverage dates, keyboard/collapsed behavior, safe links, exact metric and
chart-period mismatches, internal URLs, and malicious response-controlled labels.

Full frontend checks:

```text
npm test
10 files passed; 45 tests passed

npm run typecheck
Passed (tsc --noEmit)

npm run lint
Passed (eslint .)

npm run build
Passed (Next.js 16.4.2 webpack production build; static `/` generated)
```

The build retained the pre-existing warning that `NODE_ENV` has a non-standard value.
Compilation, TypeScript, page-data collection, static generation, optimization, and
build-trace collection completed.

Production source and application-bundle scans:

```text
rg -n -i '(raw_prompt|passage_body|embedding_vector|query_id|database_url|...|
select[[:space:]].*[[:space:]]from|insert[[:space:]]into|drop[[:space:]]table|
create[[:space:]]table)' src/components/chat src/lib/api \
  -g '!*.test.ts' -g '!*.test.tsx'
No matches

rg -n 'dangerouslySetInnerHTML|document\.write|eval\(' \
  src/components/chat src/lib/api -g '!*.test.ts' -g '!*.test.tsx'
No matches

rg -n 'NEXT_PUBLIC_.*(KEY|SECRET|PASSWORD|TOKEN)|
https?://(localhost|127\.0\.0\.1|10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.)' \
  .next/static/chunks/app
No matches
```

These are bounded pattern scans, not a dedicated vulnerability or secret audit.

## Limitations and next evidence

No live verified ClickHouse/Qdrant/Ollama browser smoke was run in this frontend task,
and no live dependency timings are claimed. A browser automation runner is not
configured in the frontend workspace, so no Playwright screenshot, real narrow-device
browser inspection, or manual screen-reader session was performed. Responsive behavior
is supported by the CSS breakpoint and component semantics and covered structurally,
but those manual checks remain Q01 evidence.

The backend specialist separately verified the wording against the current
`HotspotService.summary` and read-only adapter behavior: `returned_rows` represents the
normalized monthly series length; summary reads are parameterized; coverage is read and
validated; available monthly counts form the subtotal; and analytics metrics are
composed outside Ollama. I04 does not by itself approve Q01, deployment, or release.
