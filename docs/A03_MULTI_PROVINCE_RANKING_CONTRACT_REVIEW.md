# A03 multi-province and ranking contract review

**Decision requested:** Approve the API v1.2.0 proposal and its coordinated rollout
rules. **Approval state:** unapproved; A03 remains a review candidate until the Tech
Lead explicitly approves it. This record does not authorize B13 or I05.

## Outcome

The smallest safe public addition is optional `ChatResponse.province_analytics`, a
strict envelope with a categorical result and its bounded execution facts. It supports
selected-province totals/breakdowns and canonical province rankings without parsing
answer prose or overloading monthly chart periods. Existing v1.0/v1.1 payloads remain
valid and existing one-province semantics do not change.

The proposal is v1.2.0 under `/api/v1`. It is not emitted by the runtime yet. Proposal
models live separately from approved runtime schemas, and the proposal OpenAPI is
generated separately, so the approved v1.1 snapshot remains immutable.

## Frozen decisions

| Question | Decision |
|---|---|
| Selected result | Combined selected total plus one ordered row for every requested province |
| Comparison | Presentation of the multi-province operation, not a third operation; optional typed high/low ties and max-minus-min difference |
| Stable IDs | `hotspot_multi_province_summary_v1`, `hotspot_province_ranking_v1` |
| API version | Additive proposal v1.2.0 under `/api/v1`; health/metadata literals unchanged |
| Trace compatibility | Do not add IDs to strict v1.1 `execution_trace`; use nested `province_analytics.execution` |
| Combined mode | Legacy trace may cover route/RAG only and contains no analytics step; nested execution is authoritative for province analytics |
| Ranking universe | All 38 metadata-defined canonical provinces; top-level empty province filters mean this operation-defined universe |
| Direction | Fixed `highest` or `lowest`; server maps it to static catalog behavior |
| Top N | 1–38 dense-rank cutoff; include every cutoff tie; maximum 38 rows |
| Ordinal | Return every row at the requested dense rank |
| Rank lookup | Return exactly the named province with its rank in the full universe |
| All / zero | Explicit `all` and `zero_count` selection variants; covered zeroes participate |
| Tie ordering | Count by direction, then metadata `province_order`; equal counts share dense rank |
| Partial coverage | Numeric observed subtotals/ranking labeled `partial` and `among available observations` |
| Unavailable | Breakdown retains requested null rows and null total; required `comparison_requested` preserves true/false request intent while result comparison is null; ranking has no rows/winner; excluded count is null |
| Null geography | Nullable Indonesia-wide count for the same product/date range, separate from all rows/totals/ranks and never attributed to selected provinces |
| Display names/order | FE requires an ordered 38-entry metadata array with unique canonical two-digit codes and unique nonempty names; code/name must match and `province_order` is its one-based array position |
| Categorical presentation | `chart` remains null; no monthly-series union change |
| Data interface | Existing approved D04 views are sufficient; no DE contract or schema change is required |
| Errors | Existing 400/422 policy retained; valid unavailable coverage returns typed HTTP 200; missing/unsupported scope clarifies safely |

## Rolling compatibility finding

A naive v1.2 extension of `execution_trace.analytics_query.operation_id` is not
backwards compatible. The deployed v1.1 frontend validator rejects unknown operation
IDs and would reject the entire otherwise valid chat response. Merely making the
categorical result optional does not solve that failure.

The accepted proposal keeps legacy trace schemas unchanged. A03 analytics facts are
nested inside the new optional object. Cached v1.1 clients ignore that top-level field
and retain answer/metric rendering. Deployment is FE-compatible reader first, then BE
writer; the BE router feature remains disabled until the compatible FE is available.
Rollback disables A03 operation routing. This compatibility decision is mandatory,
not an implementation suggestion.

## Schema and invariant review

- Breakdown scope is two-to-38 unique canonical codes. Row order exactly matches
  deduplicated message order. Complete/partial counts are numeric; unavailable counts
  are null. Numeric total exactly equals the row sum.
- Ranking selection is a discriminated union: top-N, ordinal, lookup, all, or zero.
  Result rows are unique, metadata-backed, direction-ordered, tie-stable, dense-ranked,
  and bounded at 38. Available top-N cannot be empty. An ordinal with no matching
  dense rank and a zero selection with no zero-count province both return empty rows
  and null `cutoff_tie_count`.
- `selection_complete: true` plus `cutoff_tie_count` makes cutoff truncation explicit;
  top-N reaches N unless all 38 rows are exhausted, and returned cutoff ties must match
  the asserted count. B13 must prove this fact from its complete aggregation.
- The ranking universe includes covered zero-count provinces by reconciling against
  the province reference. Null-geography observations never become a province row.
- Coverage state, issues, nullability, metric, top-level filter dates, breakdown scope,
  execution parameters, returned row count, metric value, and optional top-level metric
  are cross-validated. Province categorical rows cannot be validated as chart periods.
- Every A03 province identifier is exactly two ASCII digits across result rows,
  selections, parameters, comparisons, and metadata correlation. Every public
  detection count/difference/metric is capped at `9007199254740991` so Python/OpenAPI
  cannot authorize values that JavaScript cannot represent exactly.
- Nullable semantic fields are required wire keys rather than omittable defaults:
  national null-geography exclusion, breakdown row count/total/comparison, ranking
  cutoff tie count, and execution metric value. Explicit null and a missing fact are
  therefore never conflated.
- Analytics-only calls require zero LLM calls. Combined RAG citations and model calls
  retain v1.1 validation but cannot modify the nested deterministic result.
- Source data status and full source object can be checked against metadata. Mock
  fixtures cannot claim a verified ClickHouse/NASA query.

## Threat review

Every new object is exact-key and bounded. Operations and directions are enums; N and
ordinal are integers 1–38; codes are canonical validated identifiers; labels and
provenance are server/metadata supplied. `read_only` and `parameterized` are literal
post-execution facts, not user controls. The response contains no SQL, dynamic order or
group expression, database/view/table name, host, query ID, credential, prompt,
passage, vector, raw message, local path, exception, debug object, or chain-of-thought.
Provenance and evidence URLs require public HTTPS hostnames; terminal-dot,
repeated-dot/root-like, localhost/local suffix, and all IP-literal forms fail closed.

The browser still calls FastAPI only. B05 body, graph/tool, timeout, quota, concurrency,
CORS, logging, and pseudonymization controls are unchanged. One analytics clause will
map to one server-owned operation; query implementation and injection testing belong
to B13, not this proposal.

## Consumer review handoff

Backend can implement both operations over existing D04 serving views: observation
aggregation supplies assigned and null-geography counts, daily coverage supplies the
coverage state, and the canonical province reference supplies all-38/zero
reconciliation and stable order. No ingestion or ClickHouse schema change is inferred.

Frontend receives a fully typed categorical result and never needs to parse prose,
sum rows, compute ranks, reorder ties, or infer completeness. Its proposal validator
accepts old field absence, validates exact unions and cross-field facts, and requires
the exact 38-entry canonical metadata array before checking source plus
code/name/order against it. I05 remains responsible for
accessible presentation and browser evidence after approval and B13 completion.

Independent BE and FE reviewers must record their final accept/reject findings before
Tech Lead approval. Any requested semantic change must update docs, OpenAPI, both
proposal validators, fixtures, and checks together.

## Proposal artifacts

- `docs/API_CONTRACT.md` section 10
- `docs/openapi/api_v1.2.0-proposal.openapi.json`
- `docs/fixtures/api_contract_v1.2.0.province_analytics.fixture.json`
- `docs/fixtures/api_contract_v1.2.0.province_analytics.edge.fixture.json`
- `backend/src/wildfire_api/contracts/api_v1_2_proposal.py`
- `backend/src/wildfire_api/contracts/openapi_v1_2_proposal.py`
- `backend/scripts/export_openapi_a03_proposal.py`
- `backend/tests/contract/test_a03_province_analytics_contract.py`
- `frontend/src/lib/api/a03-contract-proposal.ts`
- `frontend/src/lib/api/a03-contract-proposal.test.ts`

## Verification evidence

Executed during the proposal pass:

- `backend/.venv/bin/pytest backend/tests/contract/test_a01_api_contract.py backend/tests/contract/test_a01_openapi_snapshot.py backend/tests/contract/test_a02_execution_trace_contract.py backend/tests/contract/test_a03_province_analytics_contract.py -q`
  — 62 passed after adding two-digit province-code, JavaScript-safe-integer, required
  nullable-key, and OpenAPI alignment cases; one third-party LangGraph
  pending-deprecation warning.
- `backend/.venv/bin/ruff check backend/src/wildfire_api/contracts/api_v1_2_proposal.py backend/src/wildfire_api/contracts/openapi_v1_2_proposal.py backend/scripts/export_openapi_a03_proposal.py backend/tests/contract/test_a03_province_analytics_contract.py`
  — passed.
- `npm test -- src/lib/api/contract-fixture.test.ts src/lib/api/execution-trace-contract.test.ts src/lib/api/a03-contract-proposal.test.ts` from `frontend/`
  — 40 tests passed in three files, including matching one-character code,
  over-safe-count, and missing-nullable-key rejection cases.
- `npm run typecheck` from `frontend/` — passed.
- `npx eslint src/lib/api/a03-contract-proposal.ts src/lib/api/a03-contract-proposal.test.ts`
  from `frontend/` — passed.

Independent backend and frontend consumer review is complete. The final holistic
review accepted the two-digit province-code constraint, JavaScript-safe integer
bounds, required nullable keys, discriminator/OpenAPI alignment, coverage and ranking
semantics, metadata gating, rolling compatibility, and safe-URL policy with no
remaining contract blocker. No live ClickHouse, Qdrant, Ollama, NASA network, browser,
accessibility, performance, Q01, deployment, or release result is claimed by these
contract checks.

## Approval boundary and limitations

The fixtures are synthetic and are not numeric truth or live evidence. The proposal
does not implement query catalog entries, routing/resolution, deterministic prose,
observability, UI tables/charts, accessibility, or local integration. Runtime still
uses approved v1.1 schemas. A03 cannot become `DONE`, and B13/I05 cannot begin, until
the Tech Lead explicitly approves the reviewed proposal and coordinated rollout.
