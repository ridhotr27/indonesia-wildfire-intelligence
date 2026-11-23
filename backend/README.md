# Backend

## Deterministic chat filters (B10)

Analytics chat requests resolve province and absolute-date mentions locally before the
typed analytics tool is called. Explicit message filters override UI context; absent
fields fall back independently to UI context. Ambiguous, invalid, relative, open-ended,
or out-of-2023 dates produce a clarification response and execute no analytics query.
The allowlist in `wildfire_api.agent.filter_resolver` contains all 38 D04 provinces and
reviewed unique English aliases. Supported dates are ISO days/ranges, English or
Indonesian month plus year, and a four-digit year. A month without a year inherits the
UI year only when both UI dates share that year.

The resolver emits values only. It cannot emit SQL, table names, identifiers, limits,
or query fragments, and RAG-only/unsupported routes never enter filter resolution.

## Deterministic requested-operation routing (B11)

Chat routing distinguishes the operation a user requests from nouns or prohibited
concepts that the question merely mentions. Analytics requires an explicit bounded
operation such as `how many`, `count`, `show monthly`, `trend`, `compare`, or `map`.
Province/date UI context can fill filters only after analytics intent exists; it never
creates analytics intent by itself.

Documentation frames such as `what does ... mean`, `what are the limitations`,
`how should ... be interpreted`, and `why can't X be interpreted as Y` use the local
NASA-document RAG path even when they mention detections, confirmed fires, fire
extent, or burned area. A direct request for burned hectares, confirmed-fire counts,
prediction, or real-world causal attribution remains unsupported. Combined mode
requires both an explicit analytics operation and a separate documentation request.
For combined requests, only the explicit documentation clause is sent to retrieval and
generation; analytics values remain exclusively supplied by the validated analytics
adapter and are composed separately.

Routing remains deterministic and local. It cannot generate SQL, call dependencies,
or use an LLM to select tools. The versioned B11 corpus is stored at
`evaluation/b11_routing_corpus_v1.json`; RAG-only routes execute no ClickHouse query
and do not inherit analytics metrics from the dashboard's selected filters.

FastAPI backend for the Indonesia Wildfire Intelligence Agent. B02 adds a
parameterized, read-only ClickHouse analytics adapter for the approved D04 views.
The safe default remains the explicitly synthetic mock until DE publishes those
views and a read-only serving credential is configured.

## Local development

Requires Python 3.12 or newer.

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,rag]'
cp .env.example .env
python -m wildfire_api.rag.cli \
  --location data/qdrant-local-hashing \
  --embedding-provider hashing \
  --chunking-profile recursive-character-1400-200-v1 \
  --retrieval-profile hybrid_rrf
uvicorn wildfire_api.main:app --reload
```

The versioned API is served under `/api/v1`; interactive OpenAPI documentation
is at `/docs`. Run checks with:

```bash
pytest
ruff check .
```

The B03 NASA-document retrieval pipeline uses LangChain chunking and Qdrant:

```bash
python -m pip install -e '.[dev,rag]'
python -m wildfire_api.rag.cli \
  --location :memory: \
  --query "What does fire radiative power mean?" \
  --query "What are VIIRS confidence classes?"
```

The CLI fetches only allowlisted HTTPS NASA sources from
`resources/nasa_documents/manifest.json`, records content hashes and stable
citation metadata, and treats retrieved text as untrusted evidence. Its local
hashing embeddings are deterministic and cost-free for development; they are
not an approved production embedding model or a release-quality relevance
claim. A persistent local Qdrant path or server URL may be passed through
`--location`. The B04 runtime accepts this retriever through the server-side
application factory; when no index is configured, documentation questions abstain
without citations.

For a persistent local index, build it explicitly before starting the API:

```bash
python -m wildfire_api.rag.cli \
  --location data/qdrant-local-hashing \
  --embedding-provider hashing \
  --chunking-profile recursive-character-1400-200-v1 \
  --retrieval-profile hybrid_rrf
uvicorn wildfire_api.main:app
```

The indexing command accepts only the approved NASA manifest, builds in a staging
directory, records a versioned manifest, and publishes the new index only after a
complete build. It is safe to rerun and does not learn from chat messages or crawl
unapproved sources. The API never indexes at startup; the development configuration
loads the pinned local index and fails startup if it is missing, corrupt, or
incompatible. The deterministic extractive formatter returns only sentences from
validated retrieved passages and requires no model service. Generated Qdrant data
remains local and is excluded from Git; back up or rebuild
`data/qdrant-local-hashing` as part of local operations.

### Local Ollama answers and semantic retrieval (B08/B09)

Install and start Ollama, then download the two local models once:

```bash
ollama pull qwen2.5:1.5b
ollama pull all-minilm
```

Build the semantic index explicitly, then start the API with both local providers:

```bash
python -m wildfire_api.rag.cli \
  --location data/qdrant-lir08 \
  --embedding-provider ollama \
  --embedding-model all-minilm \
  --chunking-profile structure-title-1400-200-v1 \
  --retrieval-profile hybrid_rrf

WILDFIRE_RAG_BACKEND=local \
WILDFIRE_QDRANT_PATH=data/qdrant-lir08 \
WILDFIRE_RAG_RETRIEVAL_PROFILE=hybrid_rrf \
WILDFIRE_RAG_CHUNKING_PROFILE=structure-title-1400-200-v1 \
WILDFIRE_EMBEDDING_PROVIDER=ollama \
WILDFIRE_EMBEDDING_MODEL_NAME=all-minilm \
WILDFIRE_AGENT_MODEL_PROVIDER=ollama \
WILDFIRE_AGENT_MODEL_NAME=qwen2.5:1.5b \
WILDFIRE_AGENT_TIMEOUT_SECONDS=60 \
WILDFIRE_REQUEST_TIMEOUT_SECONDS=60 \
uvicorn wildfire_api.main:app
```

The evaluated B09 rollback remains available by setting the Qdrant path to
`data/qdrant`, the retrieval profile to `dense`, and the chunking profile to
`recursive-character-1400-200-v1`.

The request path is `user → deterministic policy/exact route → semantic intent match
for unresolved wording → LIR-04 validation → analytics and/or NASA retrieval → local
Ollama generation where already required → citation validation → response`. Routing
uses embeddings and never a generative model. `WILDFIRE_SEMANTIC_ROUTING_MODE=guarded`
is the default; set it to `disabled` to restore the previous deterministic strategy.
Both model services are accepted only on an HTTP loopback address, and there is no
cloud fallback. If the semantic index cannot start, routing safely falls back to the
deterministic strategy. Chat messages are never added to either approved index.

## Configuration

All settings use the `WILDFIRE_` prefix and may be placed in `.env`. See
`.env.example` for the supported development settings and reserved server-side
integration secrets. Real service credentials must remain server-side.

To use the B02 adapter after DE has published the D04 views, set
`WILDFIRE_ANALYTICS_BACKEND=clickhouse` and provide the ClickHouse URL, database,
read-only username, password, and timeout shown in `.env.example`. The adapter:

- executes only a static SELECT query catalog over the four approved D04 views;
- binds every filter with ClickHouse typed query parameters;
- sends `readonly=2`, execution-time, and result-row limits on every request;
- fetches at most `limit + 1` map rows and never returns the sentinel row;
- rejects unsupported data-contract major versions;
- maps database timeout/unavailability to A01-safe typed errors.

The B04 `/chat` runtime is one LangGraph state graph with deterministic planning by
default. It routes allowlisted analytics, NASA retrieval, combined, and unsupported
requests; validates structured tool inputs and outputs; and enforces graph-step,
tool-call, retrieved-context, model-token, and wall-clock ceilings. Planning uses no
LLM. When the disabled-by-default local Ollama provider is enabled, only grounded RAG
composition makes one model call and reports it in `usage.llm_calls`; no paid service
is enabled.

### Public-service controls (B05)

The API enforces process-local per-client and global fixed-window quotas, rejects
work above its concurrency ceiling, caps declared request-body size, and applies a
wall-clock timeout to every non-health request. `/health` remains available to the
orchestrator when user quotas are exhausted. Client addresses are HMAC-pseudonymized
before logging; forwarding headers are deliberately ignored unless the ASGI server is
deployed behind an explicitly trusted proxy. Configure all bounds with the B05 values
in `.env.example` and set `WILDFIRE_CLIENT_ID_SALT` to a high-entropy server-side secret
in production (startup fails closed if it is absent).

CORS is disabled by default. Allowed entries must be explicit HTTP(S) origins; wildcard
origins and origins containing paths, queries, or fragments are rejected. JSON logs
contain request ID, route, status, duration, pseudonymous client ID, and dependency
status. Known credential-shaped fields and values are redacted, request/chat content is
not logged, and unexpected exceptions expose only their class to operators and a safe
typed error to clients.

The rate and concurrency counters are per API process. A multi-worker or multi-host
deployment must replace them with a shared atomic limiter before claiming global quotas.
Provider-side spend ceilings remain an operator control in addition to these application
limits; no paid provider is enabled by this repository.

Database grants and physical views are DE-owned D06/I01 deliverables. B02 tests
prove the client requests read-only mode, but do not claim a live grant check.

For an I01 environment that has already applied D06, loaded the approved D05 batch,
and provisioned a view-only reader, run the opt-in parity and permission check without
placing credentials in source control:

```bash
backend/.venv/bin/python backend/scripts/validate_i01_clickhouse.py \
  --url "$I01_CLICKHOUSE_URL" \
  --database wildfire \
  --username "$I01_CLICKHOUSE_USERNAME"
```

The validator exercises the real FastAPI metadata, summary, known-gap, and bounded-map
paths; reconciles the approved D06 full-batch counts; verifies nullable unassigned and
multiple-match geography; rejects any synthetic identity; and proves raw SELECT, INSERT,
and DDL denial for the backend reader. It never prints or persists the password.

## Current boundaries

- `MockHotspotRepository` contains synthetic fixtures labeled `MOCK_ONLY` and is
  still the default.
- `ClickHouseHotspotRepository` is selectable, but no live ClickHouse result is
  claimed until D06/I01 publish and verify the database interfaces.
- The optional answer and embedding models run through loopback-only Ollama; no paid
  API connection or cloud fallback is made.
- The chat endpoint uses the bounded single-agent LangGraph runtime. Analytics uses
  the configured repository; RAG requires an injected B03 index and otherwise
  abstains honestly.
- The approved A01 contract is versioned in `docs/API_CONTRACT.md`; the committed
  OpenAPI snapshot and shared fixtures are contract evidence, not live-service claims.
