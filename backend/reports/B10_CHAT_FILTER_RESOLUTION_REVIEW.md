# B10 Chat Filter Resolution — Review Handoff

## Outcome

B10 adds a deterministic, typed filter-resolution stage between route classification
and the existing typed analytics adapter. Message province and complete absolute dates
override conflicting UI context. Missing message fields fall back independently.
Invalid or ambiguous explicit values return an unsupported clarification response and
do not call analytics.

The internal frozen `ResolvedChatContext` records canonical values, per-field source,
safe mention labels/reason codes, and resolution status. It is not a public API model.
The v1 `ChatResponse.filters` continues to expose the exact filters returned by the
validated analytics service; no public contract field changed.

## Supported inputs and boundaries

- All 38 D04 official province names and reviewed unique English aliases are versioned
  in one backend allowlist. Matching is NFKC/case/punctuation/whitespace tolerant and
  longest-match aware for names such as `Kepulauan Riau` and `Papua Barat Daya`.
- Dates: ISO day or inclusive range, English/Indonesian month plus year, calendar year,
  and the approved same-UI-year inheritance for a month without a year.
- Ambiguous numeric, relative, open-ended, reversed, multiple, and out-of-window dates
  fail closed. No explicit date is clamped.
- Resolution runs only for analytics/combined routes. RAG-only and unsupported routes
  retain route separation. Existing denial rules remain before the resolver.
- The synthetic A01 `MOCK_ONLY` fixture retains its deliberately non-D04 typed province
  context; production products use the D04 canonical allowlist.

## Verification

Focused test command (2026-11-07):

```text
.venv/bin/pytest tests/unit/test_b10_chat_filter_resolver.py tests/unit/test_b04_bounded_agent.py tests/integration/test_api.py -q
145 passed; one third-party LangGraph pending-deprecation warning
```

The focused suite covers all official provinces/aliases, all English/Indonesian month
spellings, precedence, fallbacks, leap/month boundaries, invalid/ambiguous forms,
bounded injection text, zero-call behavior, routes inherited from B04, and the exact
`13 / 2023-09-01 / 2023-09-30 / 414` regression using a capturing fake analytics tool.

After the API regression assertion was added, the final commands were:

```text
.venv/bin/pytest -q -ra
225 passed, 1 skipped (opt-in I01 live ClickHouse credentials absent); one third-party
LangGraph pending-deprecation warning

.venv/bin/ruff check .
All checks passed!
```

No opt-in live ClickHouse test was run in this implementation session; therefore the
pre-existing controlled 414 observation is not re-claimed as a new live measurement.

## Limitations

Relative dates, districts/cities, geocoding, product inference, arbitrary SQL, and LLM
filter parsing remain excluded. Unknown prose locations are rejected by the existing
planner; the resolver never guesses a near match. General RAG routing/model-quality
findings remain outside B10.
