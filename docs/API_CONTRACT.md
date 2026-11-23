# API Contract — approved v1.1.0 plus A03 v1.2.0 proposal

**Status:** v1.1.0 is approved; the A03 v1.2.0 section is an unapproved review proposal and is not implemented  
**Base path:** `/api/v1`  
**Transport:** JSON over HTTPS in deployed environments  
**Approved OpenAPI:** `docs/openapi/api_v1.1.0.openapi.json`  
**A03 proposal OpenAPI:** `docs/openapi/api_v1.2.0-proposal.openapi.json`  
**Shared examples:** approved v1.0/v1.1 fixtures plus the unapproved `docs/fixtures/api_contract_v1.2.0.province_analytics.fixture.json`

This contract is the browser-to-backend interface for Indonesia Wildfire Intelligence
v1.0. It incorporates the approved D04 data contract without implementing live
ClickHouse analytics, LangGraph, or frontend integration. All committed examples are
explicitly synthetic and are not NASA observations or evaluation results.

## 1. Shared conventions

- Dates are inclusive UTC calendar dates in `YYYY-MM-DD` form. Timestamps are ISO 8601
  timezone-aware UTC values serialized with `Z`.
- Verified v1 analytics use product ID `VNP14IMG.002_SNPP_FIRMS_SP`, calendar 2023 UTC,
  and canonical two-digit province codes. Visibly synthetic development mode may use
  unmistakable mock identifiers; mock values never imply verified availability.
- GeoJSON coordinates are WGS84 `[longitude, latitude]`.
- Every success and error response contains `request_id`; the server also emits
  `X-Request-ID`.
- `data_status` is `mock` or `verified`. A response labeled `mock` must not be displayed
  as real NASA data.
- Hotspots are satellite active-fire/thermal-anomaly detections, not confirmed wildfire
  incidents or burned-area measurements.
- Unknown fields are rejected in requests. Clients may ignore additive response fields
  introduced by a compatible minor version.

### Source object

```json
{
  "provider": "Synthetic fixture",
  "dataset_version": "DEMO-FIXTURE-v1-NOT-NASA-DATA",
  "data_status": "mock",
  "url": "https://firms.modaps.eosdis.nasa.gov/",
  "attribution": "Synthetic contract fixture; not NASA observations"
}
```

Verified responses must identify NASA FIRMS and the approved D04 product/version.
Province-boundary attribution remains available through metadata or limitations where
geographic results are returned.

### Coverage issue

```json
{
  "date_utc": "2023-07-26",
  "coverage_status": "known_satellite_gap",
  "evidence_url": "https://landweb.modaps.eosdis.nasa.gov/displayissue?id=480",
  "note": "Unavailable coverage; never a zero-detection day."
}
```

`coverage_status` is `known_satellite_gap` or `unknown`. A known gap requires an
evidence URL. The documented 2023-07-26 and 2023-07-27 S-NPP gaps must never be
represented as zero detections.

## 2. `GET /health`

Returns process liveness. It does not prove data, vector-store, or model readiness.

```json
{
  "request_id": "example-request-id",
  "status": "ok",
  "api_version": "1.0.0"
}
```

## 3. `GET /metadata`

Returns filter options, the supported coverage window, known unavailable dates, source
identity, and freshness. The frontend must populate filters from this response.

```json
{
  "request_id": "example-request-id",
  "api_version": "1.0.0",
  "products": [
    {"product_id": "DEMO_VIIRS", "display_name": "Synthetic VIIRS-shaped fixture"}
  ],
  "provinces": [
    {"province_code": "14", "display_name": "Riau"}
  ],
  "coverage": {
    "date_min": "2023-01-01",
    "date_max": "2023-12-31",
    "known_unavailable_dates": ["2023-07-26", "2023-07-27"]
  },
  "source": {
    "provider": "Synthetic fixture",
    "dataset_version": "DEMO-FIXTURE-v1-NOT-NASA-DATA",
    "data_status": "mock",
    "url": "https://firms.modaps.eosdis.nasa.gov/",
    "attribution": "Synthetic contract fixture; not NASA observations"
  },
  "data_freshness_at": null,
  "data_status": "mock"
}
```

`data_freshness_at` is null when no verified publication has occurred. It must not be
fabricated from application startup time.

## 4. `POST /hotspots/summary`

Request:

```json
{
  "product_id": "DEMO_VIIRS",
  "province_codes": ["14"],
  "date_from": "2023-07-25",
  "date_to": "2023-07-27",
  "group_by": "month"
}
```

`group_by` is `month` in v1. Province codes contain 1–38 distinct values. Dates must be
ordered, within metadata coverage, and within the server's configured range bound.

Response fields:

- `total`: integer for complete or partially available ranges; null when no numeric
  total is supportable because the entire range is unavailable.
- `is_complete`: false whenever a requested date has unavailable/unknown coverage.
- `coverage_issues`: exact affected dates and states.
- `warnings`: human-readable coverage or interpretation warnings.
- `series[].count`: nullable under the same rules as `total`.
- `series[].is_complete` and `series[].coverage_issues`: period-level coverage state.

Three cases are normative:

1. **Complete range with no detections:** `total: 0`, `is_complete: true`, no coverage
   issues. This is distinct from missing coverage.
2. **Partially available range:** `total` is the sum of available detections,
   `is_complete: false`, and issues/warnings identify excluded unavailable dates.
3. **Wholly unavailable range:** `total: null`, `is_complete: false`, and coverage
   issues explain why no numeric result is available.

The complete, partial, and unavailable examples in the shared fixture are canonical.

## 5. `GET /hotspots/geojson`

Query parameters:

| Name | Required | Rule |
|---|---:|---|
| `product_id` | yes | Metadata-supported product |
| `province_code` | yes | One metadata-supported province |
| `date_from` | yes | Inclusive UTC date |
| `date_to` | yes | Inclusive UTC date, not before `date_from` |
| `limit` | no | Default 500; server hard cap 5,000 |

The response is a GeoJSON FeatureCollection. Only assigned observations are returned.
Ordering is `(acquired_at_utc, observation_id)`. The backend fetches at most
`effective_limit + 1`; the sentinel determines `truncated` and is not returned.

Allowed browser properties are:

- `observation_id`
- `acquired_at_utc`
- `product_id`
- `province_code`
- `confidence_code` (`l`, `n`, or `h`; not a probability)
- `frp_mw` (non-negative; zero is valid)
- `daynight_code` (`D` or `N`)

Response metadata contains `request_id`, product/filters, returned count, effective
limit, truncation, completeness, coverage issues, source, and the hotspot caveat.
Source-row hashes, ingestion internals, and boundary geometry are never browser map
properties. The shared fixture is the canonical capped-map example.

An empty, completely covered result is HTTP 200 with `features: []`, `returned: 0`,
`is_complete: true`. A gap is HTTP 200 with incomplete coverage metadata; it is not a
fabricated empty success.

## 6. `POST /chat`

Request:

```json
{
  "message": "What does FRP mean?",
  "product_id": "DEMO_VIIRS",
  "context": {
    "province_code": "14",
    "date_from": "2023-09-01",
    "date_to": "2023-09-30"
  }
}
```

The message is 1–2,000 characters. Context values may all be null; if dates are used,
they must be ordered. `mode` is `analytics`, `rag`, `combined`, or `unsupported`.

Response:

```json
{
  "request_id": "example-request-id",
  "answer": "Synthetic contract response; no live model or retrieval was used.",
  "mode": "unsupported",
  "filters": null,
  "metrics": null,
  "chart": null,
  "map": null,
  "citations": [],
  "limitations": ["Synthetic fixture only."],
  "usage": {"llm_calls": 0}
}
```

`metrics` is a nullable list of `{name, value, unit}`; numeric values may be null when
coverage prevents a result. `chart` is a typed line/bar object using summary points.
`map` is a typed FeatureCollection using the same sanitized GeoJSON features. Citation
entries contain `title`, HTTPS `url`, and stable `chunk_id`. The backend must abstain
rather than invent metrics, citations, burned area, confirmed incidents, or causes.

## 7. Errors

Shape:

```json
{
  "request_id": "example-request-id",
  "error": {
    "code": "RATE_LIMITED",
    "message": "Try again later.",
    "retry_after_seconds": 60
  }
}
```

| HTTP | Code | Meaning |
|---|---|---|
| 400 | `INVALID_FILTER` | Semantically unsupported product/date/province combination |
| 404 | `NOT_FOUND` | Route or identified resource does not exist |
| 422 | `VALIDATION_ERROR` | Malformed shape, type, enum, bounds, or date ordering |
| 429 | `RATE_LIMITED` | Server-side quota reached; retry may be supplied |
| 500 | `INTERNAL_ERROR` | Redacted unexpected failure |
| 503 | `DEPENDENCY_UNAVAILABLE` | Required bounded dependency unavailable |
| 504 | `REQUEST_TIMEOUT` | Bounded processing deadline exceeded |

Valid filters with zero detections do not use `NO_DATA`; they return an empty HTTP 200
success with coverage semantics. Error messages must not expose secrets, SQL, stack
traces, internal URLs, or provider credentials.

## 8. Optional execution provenance (v1.1.0 proposal)

A successful `ChatResponse` may include `execution_trace`; it may also be absent or
null. Its absence preserves the v1.0.0 response semantics. Trace construction reports
operations that already occurred and must never trigger another analytics, retrieval,
generation, network, or filesystem operation.

`execution_trace` contains `trace_version: "1.0"`, final `route` (`analytics`, `rag`,
`combined`, or `unsupported`), final `status` (`complete`, `abstained`, or `partial`),
and one to eight ordered steps. Step sequences are contiguous from one. Each step has
an allowlisted `kind`, `complete | abstained | failed` status, a 1–200 character plain
label, optional non-negative integer `duration_ms` no greater than 300,000, and a
strict details object discriminated by the same `kind`.

Allowed details are:

- `route_selection`: final route only.
- `filter_resolution`: canonical province codes and dates, the source of each field
  (`message | ui_context | absent`), up to five allowlisted reason codes, and the
  validation outcome. Raw spans and messages are prohibited.
- `analytics_query`: `hotspot_summary_v1 | hotspot_trend_v1 | hotspot_map_v1`, the
  exact canonical filters, literal `read_only: true`, at most 5,000 returned rows, and
  an optional hotspot metric summary. Parameters equal top-level response filters.
- `vector_retrieval`: literal provider `local`, bounded public model/collection display
  names, `top_k` at most five, and up to five ranked items containing only chunk ID,
  title, approved HTTPS source URL, and rank. Retrieved evidence candidates are not
  necessarily cited.
- `local_generation`: literal provider `ollama`, bounded display model, zero-to-five
  input passages, and one or two actual model calls.
- `citation_validation`: zero-to-five candidate/accepted counts and
  `passed | abstained | failed`. Cited chunk IDs are a subset of retrieved chunk IDs.
- `abstention`: one of `missing_province`, `missing_date_range`,
  `unsupported_intent`, or `insufficient_evidence`.

Analytics-only and unsupported traces have zero model calls and do not invent model or
retrieval steps. Partial or failed operations cannot be labeled complete. HTTP error
envelopes never include traces; `request_id` remains the support correlation value.

The explicit serialization allowlist excludes credentials/authentication data, raw
SQL or DDL, database topology and query IDs, local paths, prompts or full messages,
passage bodies, vectors, model raw output, arbitrary exceptions and debug objects,
headers, client IPs, rate-limit keys, and chain-of-thought. URLs must already be
approved HTTPS retrieval metadata. Labels are concise execution facts suitable for
logs and screenshots, not explanations of hidden reasoning. Frontends construct any
display signature from typed fields and never execute it.

The four normative trace examples are synthetic analytics, RAG, combined, and
abstention responses in the v1.1.0 fixture. The original v1.0.0 chat example, which has
no trace field, remains a normative compatibility case.

## 9. Versioning and compatibility

- The URL major remains `/api/v1`; v1.1.0 is an additive minor proposal over the
  approved v1.0.0 baseline.
- To honor the decision that `execution_trace` is the only response-shape addition,
  existing health/metadata payload fields (including their frozen `api_version`
  literal) are unchanged. The canonical OpenAPI document `info.version` identifies
  schema release 1.1.0; clients detect trace support by validating the optional field,
  not by branching on health or metadata.
- Patch versions may clarify text without changing fields or behavior.
- Minor versions may add optional response fields. Clients must ignore unknown optional
  response fields.
- Removing/renaming fields, changing types/nullability/enums, changing coverage or
  coordinate semantics, or strengthening required inputs requires a new major version.
- Approved snapshots are immutable. Changes require BE/FE review, contract-test updates,
  and Tech Lead approval.
- Backend OpenAPI and frontend types are checked against the same committed synthetic
  fixture. The OpenAPI snapshot must equal the application-generated document.

## 9. Security and ownership boundaries

- The browser calls FastAPI only. It never receives ClickHouse, Qdrant, NASA API, or LLM
  credentials and never executes SQL.
- Backend analytics will use only the D04 read-only view allowlist and parameterized
  filters after B02/G2.
- Payload, date, map, tool, timeout, quota, and concurrency bounds are server-enforced.
- This contract does not authorize B02, B04, I02, production deployment, a paid model,
  or public-service activation.

## 10. A03 optional province analytics (v1.2.0 proposal)

This section is a coordinated contract proposal. It does not authorize B13 runtime
queries or I05 rendering. If approved, v1.2.0 adds one optional nullable
`ChatResponse.province_analytics` object. Existing one-province responses, monthly
charts, endpoints, request shapes, error envelopes, health/metadata version literals,
and the approved v1.1 `execution_trace` remain unchanged.

### 10.1 Compatibility and rollout decision

The existing frontend deliberately rejects unknown `execution_trace.analytics_query`
operation IDs. Adding A03 operation IDs to that v1.1 union would therefore break a
cached strict client, even if `province_analytics` itself were optional. A03 does not
extend the legacy analytics trace union. New province operations put their bounded
query facts in `province_analytics.execution`; analytics-only A03 responses omit
`execution_trace`. Combined A03 + documentation responses may retain a v1.1 trace for
route/retrieval/generation/citation steps, but it contains no `analytics_query` step;
the nested A03 execution object is the authoritative analytics provenance.

This permits the coordinated deployment order FE v1.2 first, then BE v1.2. A v1.1
client ignores the unknown top-level object and continues rendering the deterministic
answer and optional metric. A v1.2 client validates and renders the categorical rows.
BE must not emit an A03 province result before the compatible FE is deployed. Rollback
disables the new router operations; it does not change existing response semantics.

### 10.2 Result envelope

`province_analytics` has exactly two required members:

- `result`: a strict union discriminated by `kind`.
- `execution`: a strict, post-execution fact record correlated with the result.

Both result kinds carry metric `satellite_hotspot_detections`, product ID, inclusive
UTC dates, source/provenance, `coverage_state` (`complete | partial | unavailable`),
`is_complete`, bounded coverage issues, and nullable
`not_assigned_to_exactly_one_province_count`. The exclusion count covers observations
not assigned to exactly one canonical province; it is never a province row and is
excluded from selected totals and rankings. It is null when no supportable value is
available, including wholly unavailable coverage.

Source is the approved source object. Every A03 province code on the wire is a string
matching exactly `^\d{2}$`; one-character or nonnumeric aliases are invalid. FE requires
metadata and accepts it only as an ordered array of exactly 38 entries with unique canonical two-digit province codes
and unique nonempty display names. It validates source, product, province code, and
name before accepting a new result. `province_order` is exactly the province's
one-based position in that ordered `GET /metadata.provinces` array; it is the stable
canonical tie breaker and is not user text.

`not_assigned_to_exactly_one_province_count` always has Indonesia-wide scope for the
same product and absolute date range, including on a selected-province breakdown. It
must be worded as a national assignment exclusion and never as detections excluded
from, or attributable to, the selected provinces.

### 10.3 Selected-province breakdown

`kind: province_breakdown` represents 2–38 distinct, explicitly named canonical
provinces. It contains ordered `requested_province_codes`, `total`, two-to-38 rows,
and nullable `comparison`. Rows follow deduplicated message order and contain code,
name, canonical order, and nullable count. UI context never adds a province when two or
more message provinces establish the complete scope.

For complete or partial coverage every row count is numeric, including covered zero,
and `total` exactly equals the row sum. Partial values are observed subtotals over
available dates. For wholly unavailable coverage, all requested rows remain present
with null counts, total and comparison are null, and no value is described as zero.
When comparison was requested and numeric values are available, `comparison` returns
all tied highest codes, all tied lowest codes, and exact max-minus-min difference; its
presence must match the typed execution parameter. For wholly unavailable coverage,
the required boolean `comparison_requested` preserves what the request asked (true or
false), while `comparison` is necessarily null. Null result presence does not imply
that comparison was not requested.

Top-level `filters.province_codes` equals the requested ordered codes and filter dates
equal result dates. A categorical result uses `chart: null`; province rows must never
be coerced into monthly `ChartPoint.period` values.

### 10.4 Province ranking

`kind: province_ranking` always uses the approved universe of 38 canonical provinces
and only observations assigned to exactly one province. Top-level
`filters.province_codes: []` means the ranking operation's all-38 universe; it is not
a missing-province clarification and it must be displayed as `All 38 provinces`.
`direction` is `highest` or `lowest`; callers cannot supply an order expression.

The strict `selection` union is:

- `top_n` with `top_n` 1–38. N is a dense-rank cutoff, not a row limit, so every tie at
  the cutoff is returned and row count can exceed N but never 38.
- `ordinal` with requested dense rank 1–38; every tie at that rank is returned. If no
  row in the full universe has that dense rank, rows are empty and
  `cutoff_tie_count` is null.
- `rank_lookup` with one canonical province; exactly that province's row is returned
  with its dense rank in the full universe.
- `all`, which returns exactly 38 rows.
- `zero_count`, used with `lowest`, which returns every covered zero-count province
  and, when no province has zero, returns empty rows with `cutoff_tie_count: null`.

Rows contain code, metadata name, canonical order, numeric count, and dense rank.
Ordering is count descending for `highest` or ascending for `lowest`, then canonical
order for ties. Equal counts share a rank; the next different count increments rank by
one. Lowest and all-province operations reconcile with the province reference so
covered zeroes participate. Available `top_n` always returns at least rank one.
Literal `selection_complete: true` asserts that the fixed operation exhausted the
selection. `cutoff_tie_count` equals the number of rows at the requested top-N/ordinal
cutoff (or all returned zero rows) and is null for lookup/all/unavailable. Validators
require top-N to reach N unless all 38 rows are exhausted and require the advertised
cutoff tie count to equal returned tied rows. Empty `ordinal` and `zero_count`
selections use null rather than a fabricated zero tie count. B13 must prove the
assertion against its full all-38 aggregation and include negative truncated/tie
tests.

Partial coverage may return numeric rows only with `coverage_state: partial`, exact
issues, and user wording `Ranking among available observations`; it is not a complete
period winner. Wholly unavailable ranking has an empty row list, null execution metric,
and no winner or fabricated zero.

### 10.5 Execution facts and correlation

Stable IDs are `hotspot_multi_province_summary_v1` and
`hotspot_province_ranking_v1`. `execution.parameters` is itself discriminated:

- `multi_province_summary`: product, 2–38 ordered distinct codes, dates, and
  `comparison_requested`.
- `province_ranking`: product, dates, direction, and the exact selection union.

Execution also contains literal `read_only: true`, literal `parameterized: true`,
`returned_rows` (province result rows, never raw database rows), metric name, and
nullable metric value. Returned rows equal `result.rows.length`; product/dates/scope,
selection, total/leading metric, comparison presence, and top-level filters/metrics
must agree exactly. Analytics-only A03 responses require `usage.llm_calls: 0`.
Combined documentation generation may not alter, sum, compare, or rank these values.

### 10.6 Coverage, errors, and bounds

The approved coverage issue vocabulary is unchanged. Complete means no issues;
partial and unavailable require at least one exact issue. Known gaps retain an HTTPS
evidence URL. Missing dates or ranking range, unknown/ambiguous province, unsupported
N, unsupported growth ranking, and prohibited measures remain successful safe
clarifications in `mode: unsupported` when the request is structurally valid. A
malformed type/bound is 422; a recognized but unsupported product/date/province
combination is 400. Wholly unavailable valid scope is a successful typed result, not
an error.

All objects reject extra fields. Every public detection count, total, comparison
difference, exclusion count, and execution metric is a non-negative integer no greater
than JavaScript `Number.MAX_SAFE_INTEGER` (`9007199254740991`); rows are
bounded by 38; selection integers are 1–38; display names are metadata-supplied and
bounded. URLs come only from approved source/coverage metadata and require a public
HTTPS hostname: terminal-dot, repeated-dot/root-like, localhost/local suffix, and all
IP-literal forms are rejected rather than normalized. No SQL, identifiers,
tables, hosts, credentials, prompts, passages, vectors, query IDs, local paths, raw
messages, free-form debug objects, or chain-of-thought are exposed.

Nullable fields remain required wire keys: the national null-geography exclusion
count, breakdown row `count`, breakdown `total` and `comparison`, ranking
`cutoff_tie_count`, and execution `metric_value`. Their value may be null only under
the semantics above; omitting a key is invalid.

### 10.7 Compatibility matrix

| Client / response | v1.0–v1.1 response | v1.2 A03 response |
|---|---|---|
| v1.1 strict client | Full approved behavior | Renders answer/metric; ignores optional `province_analytics`; no unknown analytics trace ID |
| v1.2 client | Full approved behavior; field absent/null accepted | Strict categorical result, provenance, and correlation validation |
| v1.1 backend | Emits no new field | Not applicable |
| v1.2 backend after coordinated enablement | Existing behavior unchanged | Emits A03 result only for approved operation frames |

The proposal fixtures are conspicuously synthetic. They cover two/three-province
breakdown and comparison, top one, cutoff ties, covered zero, rank lookup, partial and
wholly unavailable ranking, separate geographic exclusion, combined documentation,
mock provenance, old-field absence, and fail-closed mutations. They are not live
ClickHouse correctness, accessibility, Q01, deployment, or release evidence.
