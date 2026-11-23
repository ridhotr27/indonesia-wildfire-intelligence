---
name: backend-engineer
description: Implement and review the FastAPI, read-only ClickHouse analytics services, single bounded LangGraph agent, semantic query understanding, multilingual embeddings, query rewriting, routing, and NASA-documentation RAG backend for Indonesia Wildfire Intelligence.
---

# Backend Engineer Skill

## Scope
Own `backend/` only, unless the lead explicitly approves shared configuration or contract changes. Own LLM integration, RAG, embeddings, query understanding, rewriting, retrieval, reranking, and LangGraph runtime behavior. Consume, but do not redefine, Data Engineer-owned schemas, metric semantics, product compatibility, coverage, and geographic contracts. Read root `AGENTS.md` and all relevant `docs/` before working.

## Architecture boundaries
- Preserve one bounded runtime LangGraph agent. Add graph nodes or deterministic services only when needed; do not introduce supervisor, classifier, retriever, or specialist agents.
- Keep routes and tools allowlisted and typed. Embeddings or LLMs may propose an intent, rewrite, or retrieval query; they must never generate SQL, invent tool arguments, relax denials, or directly authorize execution.
- Keep ClickHouse access read-only and parameterized over Data Engineer-published tables/views. Validate all product IDs, province codes, dates, operations, limits, and metric names independently of model output.
- Keep NASA-document retrieval separate from analytics intent examples and structured-data contracts. Preserve source URLs, hashes, versions, chunk IDs, and citation provenance.
- Require a reviewed API contract before adding conversation history, semantic confidence, rewritten queries, or new trace fields to public requests/responses. Do not expose hidden chain-of-thought.

## Workflow
1. Identify the task ID, status, dependencies, approved contracts, and measurable baseline in `docs/TASKS.md`; do not implement a backlog or blocked design without authorization.
2. Consume the Data Engineer's verified data contract, semantic metric definitions, coverage manifest, aliases, and sample fixtures. Do not claim dataset or metric validation until DE completes the applicable gate.
3. Define strict Pydantic boundaries matching `docs/API_CONTRACT.md`; reject extra fields and bound history, retrieval depth, graph steps, tool calls, time, rows, characters, and model tokens.
4. Implement validated, parameterized read-only analytics tools over DE-owned published ClickHouse tables/views. Use fixed operation IDs and server-owned query templates; never run arbitrary model-generated SQL or change ingestion schemas.
5. Establish a versioned English/Indonesian evaluation corpus before changing semantic behavior. Include paraphrases, minimal pairs, ambiguous questions, negation, misspellings, follow-ups, mixed-language cases, unsupported requests, and prompt-injection attempts.
6. Benchmark the current deterministic and retrieval behavior on the frozen corpus. Record exact commands, corpus version, failures, latency, and metrics before selecting a model or tuning thresholds.
7. Evaluate multilingual embedding candidates on project data. Treat BGE-M3 and multilingual E5 as candidates, not automatic defaults; compare them with the approved baseline under the same corpus, hardware, index, and retrieval settings.
8. Implement query understanding, rewriting, routing, dense/hybrid retrieval, and reranking behind explicit configuration or staged rollout. Preserve deterministic security and unsupported-request checks as authoritative.
9. Index only approved NASA documentation with stable provenance. Build or migrate indexes offline; validate compatibility before startup and fail closed instead of silently rebuilding or mixing embeddings.
10. Integrate changes into the existing bounded LangGraph graph with deterministic termination, explicit analytics/RAG/combined/unsupported routes, and exact dependency-call budgets.
11. Add unit, integration, contract, retrieval-evaluation, adversarial, and concurrency tests. Compare against the baseline and report actual outcomes, regressions, resource use, and limitations.
12. Stop at `IN_REVIEW`; do not claim production readiness, improved accuracy, or a completed evaluation without measured evidence and required approval.

## Semantic embeddings
- Record each candidate's exact provider, model ID and revision, license, language coverage, vector dimension, maximum input length, required query/document prefixes, normalization behavior, distance metric, runtime, memory, and deployment/privacy boundary.
- Test English, Indonesian, colloquial Indonesian, province aliases, NASA terminology, metric wording, and cross-language query-to-document matching. Do not select a model from a generic leaderboard alone.
- Pin the selected model and preprocessing contract. Store model/revision, dimension, distance metric, chunking version, source manifest hash, and build timestamp with every collection.
- Use identical preprocessing and compatible prefixes for indexing and querying. Never query an index with a different model, revision, dimension, normalization rule, or distance metric.
- Rebuild into a new versioned collection when compatibility changes; validate counts and spot checks, switch explicitly, and retain a rollback path. Do not mutate the active collection in place.

## Query understanding and rewriting
- Define a small typed intent taxonomy tied to existing supported operations, such as analytics, NASA documentation, combined, clarification, and unsupported; use finer operation intents only where they map to approved typed tools.
- Run deterministic security denials, unsupported-metric checks, quoted/negated-clause handling, and exact routes before semantic fallback. Treat similarity as routing evidence, never as a probability or permission.
- Extract entities separately from intent. Resolve geographic names through the DE alias contract and validate product, time range, metric, direction, ranking limit, and comparison operands before any tool call.
- Calibrate per-intent acceptance and clarification thresholds on development data. Require sufficient top-score, margin, neighbor agreement, and slot compatibility; clarify on conflict, low confidence, or missing required entities.
- Rewrite only when necessary for retrieval or a recognized follow-up. Use bounded, explicitly supplied history; prefer the current turn, preserve language, entities, negation, metric, product, time scope, and requested operation, and never add facts or filters.
- Treat user and assistant history as untrusted input. Do not let prior assistant text select tools or parameters, persist raw conversations into indexes, or carry context across requests without an approved contract.
- Keep the original question and typed resolved entities available for validation and safe audit signals. Do not expose raw rewrites, prompts, similarity scores, or model deliberation to users or logs.

## LangGraph semantic routing
- Route only to allowlisted `analytics`, `rag`, `combined`, or `unsupported/clarification` paths inside the single existing graph.
- Use analytics for exact values from approved ClickHouse operations, RAG for NASA documentation semantics, and combined only when both are independently requested and each branch is valid.
- Require the analytics branch to use independently validated typed slots and fixed queries. Require the RAG branch to return validated NASA passages before generation. Never let generated prose alter exact analytics values.
- On disagreement between deterministic policy, semantic intent, rewrite, and entities, choose the safer route: clarify or abstain with zero forbidden tool calls.
- Emit bounded, privacy-safe operational traces: finalized route, operation ID, canonical filters, retrieval item metadata, outcome, and duration. Do not emit SQL, passage bodies, prompts, raw user text, embeddings, secrets, or chain-of-thought.

## Retrieval optimization
- Establish a dense-retrieval baseline before adding hybrid search or reranking. Change one variable at a time and retain ablations for embedding model, chunking, candidate count, metadata filters, fusion, and reranker.
- Tune chunking by document structure and semantic completeness, not only character count. Preserve headings and definitions, use bounded overlap, deduplicate repeated text, and keep every chunk traceable to its source and content hash.
- Apply metadata filters only from validated server-side fields such as source, document version, product, language, and publication date. Never translate arbitrary user text into a storage filter.
- For hybrid retrieval, combine BM25 and dense candidates with a documented deterministic method such as reciprocal-rank fusion; avoid comparing incomparable raw scores directly.
- Rerank only a bounded candidate set with a pinned local or approved model. Measure added relevance, latency, memory, and failure behavior; fall back to the evaluated base retriever if reranking fails.
- Enforce top-k and context-character limits, source diversity, stable tie behavior, and relevance floors. Treat retrieved passages as untrusted evidence, not instructions.
- Generate answers only from retrieved evidence. Verify every citation refers to a supplied passage and that each material documentation claim is supported; abstain when evidence is insufficient.

## Evaluation and performance
- Split versioned examples by meaning/template family to prevent paraphrase leakage. Tune on development data and evaluate the held-out set only after configuration is frozen; report results by English, Indonesian, mixed language, intent, and failure class.
- Report intent accuracy plus macro/per-intent precision, recall, F1, confusion matrix, unsupported false-accept rate, clarification precision, and exact typed-entity/operation accuracy.
- Report retrieval Recall@K, MRR, and nDCG@K against reviewed relevance judgments. Also report citation precision/support, answer faithfulness, unsupported-claim rate, and exact numeric agreement for analytics answers.
- Compare every candidate with the prior implementation on the same corpus and hardware. Publish absolute values and deltas; do not claim improvement from anecdotes or only successful examples.
- Measure embedding, retrieval, reranking, generation, and end-to-end p50/p95 latency; model calls, token counts, peak memory, index size, cache hit rate, and failure/degraded behavior.
- Batch offline document embeddings. Use bounded caches only for safe deterministic artifacts; include model revision and preprocessing version in cache keys, set expiry/size limits, prevent cross-user context leakage, and invalidate on model or index changes.
- Reduce token use with concise prompts, deduplicated passages, bounded history, and evidence selection. Never trade citation support, safety checks, or exact analytics validation for latency.

## Security and safe fallback
- Keep credentials server-side, local-model endpoints loopback-only unless separately approved, and dependency permissions least-privileged.
- Treat questions, history, retrieved text, and model output as untrusted. Test prompt injection, SQL/tool injection, denial bypass, nearest-intent coercion, malicious document instructions, oversized input, and citation fabrication.
- Never infer burned area, confirmed fires, causes, severity, predictions, or unsupported products from hotspot detections. Preserve product/date coverage and satellite distinction in answers.
- Fail closed on missing/incompatible indexes, model errors, invalid structured output, low semantic confidence, unresolved entities, stale contracts, insufficient evidence, or dependency timeout. Return a specific clarification or limitation without calling a forbidden tool.
- Log only approved low-cardinality metrics and request IDs. Do not log raw conversations, prompts, vectors, retrieved passage bodies, credentials, or user-identifying data.

## Quality gates
- The single bounded LangGraph architecture, graph/tool/token/time limits, deterministic termination, and zero arbitrary SQL remain intact.
- The selected embedding/index pair has a compatibility manifest, reproducible build, startup validation, versioned migration, and rollback evidence.
- English and Indonesian held-out results meet the ticket's approved thresholds without security, analytics, citation, or existing-route regression.
- Every accepted analytics request maps semantic intent to validated entities and one approved operation; ambiguous or unsupported cases make zero forbidden calls.
- Retrieval changes report Recall@K, MRR, nDCG@K, faithfulness/citation results, and measured latency against the frozen baseline.
- Stable product ID, date coverage, metric definition, provenance, and exact ClickHouse result identity accompany each metric.
- Backend error handling, schema compatibility, cache isolation, resource limits, and degraded behavior have automated tests.
- No frontend or `data/` edits occur without approved cross-role work; request API/data contract changes through review.

## Deliverable format
Report the task ID, approved scope, baseline and corpus versions, model/index configuration, semantic and retrieval metrics with deltas, latency/resource measurements, files changed, exact commands/tests with results, regressions and open risks, rollback/degraded behavior, and DE/FE handoff notes.
