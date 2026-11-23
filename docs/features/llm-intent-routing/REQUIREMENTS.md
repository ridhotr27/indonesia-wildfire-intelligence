# Semantic Intent Routing Requirements

**Status:** Approved architecture; LIR-09 activation `IN_REVIEW`, guarded by default  
**Feature:** Embedding-based intent understanding and deterministic execution validation  
**Owners:** Backend Engineer (runtime); Data Engineer (structured metric/entity semantics); Tech Lead (contracts and rollout)  
**Related baseline:** B10-B14, Q01, API v1.2.0, data contract v1.0.0

## 1. Background and current problem

The chatbot must answer supported wildfire-intelligence questions even when users phrase the same meaning differently. The current production path is deterministic-first: Python rules select `analytics`, `rag`, `combined`, or `unsupported`; a separate resolver extracts province and absolute-date filters; typed tools execute fixed read-only ClickHouse queries or retrieve allowlisted NASA documentation. The local LLM currently writes grounded NASA-document answers after routing. It does not normally interpret the question before routing, and analytics-only answers use zero LLM calls.

This design is safe and reproducible, but it creates avoidable generic fallbacks when a supported request does not match a reviewed regular expression. B14 added semantic intent matching as a disabled/shadow/guarded fallback. Its real held-out evaluation showed that neither tested embedding profile was release-ready: all-minilm preserved a 0% unsupported false-accept rate but achieved only 41.38% route accuracy and 20.20% fallback recovery; BGE-M3 improved recovery but falsely accepted 8% of unsupported cases. On 2026-11-17 the user acting as Tech Lead accepted the later LIR-07 limitations and authorized guarded mode as the active default for LIR-09. This exception does not claim that release gates passed or authorize deployment.

The feature goal is to reduce unnecessary fallbacks for English, Indonesian, mixed-language, paraphrased, conversational, and explicit multi-intent questions while preserving deterministic security, exact analytics, citation provenance, and the existing single bounded LangGraph architecture. Routing and intent planning use no generative LLM call. Existing LLM generation remains limited to grounded NASA-document answer paths that already use it.

## 2. Verified existing behavior

- `POST /api/v1/chat` accepts one message, a product ID, and nullable province/date UI context. It has no conversation-history field.
- `DeterministicIntentRouter` applies unsafe/unsupported policies and reviewed operation/documentation patterns.
- `ChatFilterResolver` recognizes the 38 canonical provinces, reviewed English aliases, English/Indonesian months, and bounded absolute dates. Message filters override UI context.
- One bounded LangGraph routes through `plan`, `resolve_filters`, `analytics`, `retrieve`, and `compose`, with explicit graph-step, tool-call, timeout, retrieval-character, and model-token limits.
- Analytics tools accept typed arguments only. The ClickHouse repository selects from a static query catalog and sends parameterized requests with `readonly=2`; neither users nor models provide SQL.
- NASA RAG chunks allowlisted documents, searches a persistent local Qdrant collection, validates NASA provenance, and asks local Ollama to produce structured cited answers.
- The semantic intent index is separate from the NASA-document index. LIR-09 defaults it to guarded mode; `disabled` remains the deterministic rollback.
- `docs/ARCHITECTURE.md`, named in the task request, is absent. The approved architecture is documented in `docs/TECHNICAL_DESIGN.md` and the implementation.

## 3. User stories and use cases

### US-01 — Paraphrased analytics

As a user, I can ask the same supported count, comparison, trend, or ranking question with different natural wording and receive the same validated operation instead of a generic fallback.

Examples:

- “Which had more detections in September 2023, Aceh or West Sumatra?”
- “Between Aceh and Sumatera Barat, who recorded the larger September 2023 hotspot count?”
- “Provinsi mana yang paling banyak terdeteksi hotspot pada September 2023?”

### US-02 — Documentation questions

As a user, I can ask direct or implicit questions about FIRMS, VIIRS, FRP, confidence, products, and detection limitations and receive an answer grounded in cited NASA documentation.

### US-03 — Explicit combined questions

As a user, I can request an exact ClickHouse result and an independently grounded NASA explanation in one turn. The generated prose must not change the numeric result.

### US-04 — Clarification

As a user, I receive a specific clarification when required entities are absent, conflicting, ambiguous, unsupported, or outside coverage, instead of an invented filter or an irrelevant generic answer.

### US-05 — Follow-up questions

As a user, I can ask a bounded follow-up such as “What about Aceh?” or “And why should that not be treated as confirmed fires?” when the required conversation history is explicitly provided under an approved API contract. The system must preserve the original metric, operation, time scope, language, and negation unless the current turn overrides them.

### US-06 — Safe unsupported requests

As a user, I receive an honest refusal for burned area, confirmed-fire counts, causal attribution, prediction, unsupported products/regions/dates, or instructions to bypass controls. No analytics or retrieval tool is called when policy prohibits it.

### US-07 — Graceful local-model failure

As a user, I receive a deterministic answer, specific clarification, or safe fallback when Ollama or a model is unavailable or returns invalid structured output. The application never silently selects another provider.

## 4. Functional requirements

| ID | Requirement |
|---|---|
| FR-01 | Run deterministic security denials, unsupported-domain policy, and unambiguous high-precision routes before probabilistic planning. |
| FR-02 | For unresolved supported language, classify against reviewed multilingual intent examples using a pinned embedding model, cosine similarity, and measured per-intent score/margin/agreement thresholds. Routing makes no generative LLM call. |
| FR-03 | Preserve the original message. Any bounded context rewrite is deterministic, untrusted derived data and may be used only after entity-preservation validation; analytics never executes from rewritten prose. |
| FR-04 | Extract and validate intent separately from product, metric, provinces, date range, direction, ranking limit, comparison operands, and documentation topic. |
| FR-05 | Independently canonicalize entities using server-owned product, province-alias, metric, coverage, and operation contracts. Model strings never become ClickHouse parameters directly. |
| FR-06 | Map an accepted plan only to `analytics`, `rag`, `combined`, `clarification`, or `unsupported`, and only to existing or separately approved typed tools. |
| FR-07 | Keep all ClickHouse execution read-only, parameterized, bounded, and selected from the server-owned static query catalog. Generated SQL is prohibited. |
| FR-08 | For RAG, retrieve only allowlisted NASA documentation, retain stable provenance, and accept citations only for passages supplied to generation. |
| FR-09 | For combined requests, validate analytics and documentation clauses independently. Failure of one branch must not corrupt or fabricate the other branch. |
| FR-10 | Use bounded context resolution for follow-ups only after an approved request contract supplies history. Do not introduce hidden server-side conversation memory. |
| FR-11 | Prefer current-turn entities over history. Never carry forward an unsafe request, assistant-generated fact, unsupported metric, or conflicting entity without clarification. |
| FR-12 | If a semantic match is unavailable, ambiguous, below threshold, missing required slots, or incompatible with deterministic policy/LIR-04 validation, clarify or abstain with zero forbidden tool calls. |
| FR-13 | Preserve existing successful deterministic behavior and response contracts. Any optional history input or new public trace fact requires coordinated API/FE review before implementation. |
| FR-14 | Support `disabled`, `shadow`, and guarded rollout modes with a one-setting rollback to the deterministic baseline. |
| FR-15 | Record privacy-safe operational metrics for route source, accepted operation, clarification/fallback reason, model duration, validation outcome, and tool-call count without raw prompts, messages, history, vectors, SQL, passage bodies, or chain-of-thought. |
| FR-16 | Keep the semantic intent index separate from NASA RAG, version its examples/model/dimensions/thresholds, and atomically load only compatible calibrated indexes. Similarity may select a coarse route but never directly authorize ClickHouse arguments or SQL. |

## 5. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-01 | Preserve one bounded LangGraph runtime; do not add runtime specialist or supervisor agents. |
| NFR-02 | Preserve current graph/tool/time/token limits unless a separately reviewed measurement justifies a bounded change. |
| NFR-03 | Keep Ollama loopback-only and all inference local under the approved profile; no cloud fallback or browser model access. |
| NFR-04 | Maintain the PRD's initial end-to-end p95 target below 10 seconds on the approved local test profile, and report stage-level p50/p95 latency. |
| NFR-05 | Existing API requests and responses remain valid. Additive contract work must follow the project's versioning and FE-reader-before-BE-writer rollout policy. |
| NFR-06 | Model/index versions, prompts, schemas, evaluation corpora, thresholds, hardware, and results are reproducible and versioned. |
| NFR-07 | Failure is closed and deterministic: no arbitrary tool, SQL, entity, citation, number, or provider is selected after a dependency failure. |
| NFR-08 | Analytics numbers remain exact tool outputs; documentation claims remain supported by retrieved evidence. |
| NFR-09 | Runtime logs and evaluation artifacts comply with privacy constraints and do not persist production conversations into training or vector indexes. |
| NFR-10 | New dependencies are prohibited unless an ablation demonstrates a material need and the Tech Lead approves their operational cost and license. |

## 6. Scope

### In scope

- Semantic-only routing for unresolved natural language using reviewed multilingual examples.
- High-precision deterministic-first routing and independent plan validation.
- English/Indonesian/mixed-language intent and entity evaluation.
- Bounded context resolution and rewriting design for explicitly supplied history.
- Comparative evaluation of deterministic and guarded semantic-only variants.
- Optional semantic candidate-tool retrieval and RAG retrieval improvements only when justified by measurement.
- Existing analytics, RAG, combined, clarification, and unsupported paths.
- Shadow evaluation, feature flags, rollback, privacy-safe telemetry, and Q01 handoff.

### Out of scope

- Generative LLM routing, intent planning, entity invention, or SQL generation.
- Arbitrary or model-generated SQL, new ClickHouse schemas, or database writes.
- New wildfire metrics, products, date coverage, geographic levels, prediction, causation, burned area, or confirmed-fire capability.
- Additional runtime agents, autonomous planning loops, online learning, or automatic prompt/model tuning from user conversations.
- Cloud LLM/embedding fallback, browser-side credentials, hosted-Qdrant migration, or deployment approval.
- Exposing prompts, raw rewrites, similarity scores, hidden reasoning, or chain-of-thought in the UI.
- Claiming that B14, Q01, or this proposed feature has passed release gates.

## 7. Security and safety requirements

- Questions, history, retrieved documents, embedding matches, and model output are untrusted inputs.
- Deterministic denial policy remains authoritative over LLM or embedding output.
- Validate exact schema, enum, string length, collection size, date bounds, province count, ranking limit, and operation compatibility before execution.
- A plan cannot introduce an entity not present in the current message, approved UI context, or explicitly supplied accepted history.
- Assistant history is context, never evidence and never authority to select a tool or numeric value.
- Prompt injection, quoted instructions, negation, SQL/tool injection, tool-name coercion, citation fabrication, oversized history, and cross-turn context poisoning require explicit adversarial tests.
- Analytics uses only fixed operation IDs and server-owned parameterized queries with the read-only serving identity.
- RAG continues to enforce public NASA HTTPS URLs, stable hashes/chunk IDs, bounded context, and citation-subset validation.
- No production message, history, prompt, or model output is inserted into Qdrant or an evaluation corpus without a separate reviewed privacy process.

## 8. Acceptance criteria

The following remain production release gates. The explicit LIR-09 decision permits guarded local/runtime activation with known accuracy limitations, but does not satisfy or waive deployment/release criteria:

1. Deterministic denial and existing supported-route regression suites remain 100% within their security/tool-call boundaries.
2. Unsupported false accepts and forbidden tool calls are 0.
3. Semantic-only route macro-F1 is at least 0.90 and no supported intent has recall below 0.80.
4. Tool-selection precision is at least 0.99; exact operation plus required-entity accuracy is at least 0.95.
5. Unnecessary fallback rate on supported holdout questions falls by at least 50% relative to the frozen deterministic baseline.
6. Clarification decisions are at least 0.95 precise and never fabricate missing entities.
7. English and Indonesian route accuracy are each at least 0.90; report mixed-language results separately without hiding low-volume classes.
8. Analytics answers exactly match reference ClickHouse results, including ties, zeros, partial coverage, unavailable periods, and geography exclusions.
9. NASA retrieval and answer quality do not regress below the approved Q01/B09 baseline; report Recall@5, MRR, nDCG@5, citation support, faithfulness, and unsupported-claim rate.
10. End-to-end p95 stays below 10 seconds on the approved profile; stage latency, model calls, token counts, peak memory, CPU, and index size are recorded.
11. Existing API, contract, unit, integration, adversarial, and full backend tests pass. Any approved history contract has matching BE/FE contract tests and old-client compatibility evidence.
12. Shadow telemetry shows no new unsafe route class before guarded enablement, and rollback to deterministic routing is tested.

These are approval thresholds, not observed results. Actual measurements must be reported without removing or relabeling failures.

## 9. Open questions and assumptions

| ID | Decision required | Current assumption |
|---|---|---|
| OQ-01 | Which multilingual embedding profile is eligible for routing? | Keep `all-minilm` as the measured local baseline; a replacement requires pinned model/license/digest, recalibration, and a safety/quality win. |
| OQ-02 | How will conversation history reach the backend? | No hidden server memory. Propose an optional bounded request field under separate coordinated contract approval, or defer true follow-ups. |
| OQ-03 | May similarity choose an executable operation? | No. It selects a coarse intent only; deterministic slots and the LIR-04 registry/validator authorize operations. |
| OQ-04 | How are low-confidence and near-tie matches handled? | Reject to clarification using measured score, margin, and neighbor-agreement thresholds; do not retry with a generative planner. |
| OQ-05 | What confidence signal is trusted? | Only measured embedding thresholds plus deterministic policy, entity provenance, and operation compatibility; similarity alone is insufficient. |
| OQ-06 | Does a clarification require a new public response mode or field? | Prefer the existing `unsupported` response with specific wording unless a separately approved contract demonstrates a necessary additive field. |
| OQ-07 | Who owns canonical metric/entity terminology? | Data Engineer publishes and reviews the semantic data contract; Backend consumes it for planners and validators. |
| OQ-08 | Can consumed B14 holdout cases be reused? | Only as development/regression data. A fresh family-separated holdout is required for rollout decisions. |
