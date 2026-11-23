# Product Requirements Document (PRD)

## Indonesia Wildfire Intelligence Agent — v1.0

**Status:** Approved for v1.0 implementation (G0)  
**Date:** 2026-10-22  
**Product type:** Public portfolio / research exploration application  
**Target delivery:** Approximately 4 weeks (subject to data validation)

## 1. Product summary

Indonesia Wildfire Intelligence Agent is a conversational application for exploring historical satellite-detected fire hotspots in Indonesia. Users can ask natural-language questions, view maps and trends, compare geographic areas and time periods, and receive explanations grounded in NASA technical documentation.

The product combines quantitative queries over NASA FIRMS hotspot observations with retrieval-augmented generation (RAG) over NASA documentation. It is an exploratory analytical tool, **not** an emergency warning service, verified wildfire incident database, or causal prediction system.

## 2. Problem statement

Historical fire observations and their technical interpretation are difficult for nontechnical users to explore together. Users must otherwise download data, perform geospatial filtering, write analytical queries, and consult satellite documentation separately. This application brings these steps into one transparent interface.

## 3. Goals and non-goals

### Goals
- Let users investigate historical hotspot activity through natural-language questions.
- Support date and region filters, comparisons, trends, and maps.
- Explain satellite concepts and caveats with traceable NASA citations.
- Show evidence behind analytical answers: filters, data source, query summary, and observation counts.
- Demonstrate measurable LLM tool-use, retrieval, evaluation, and cost controls.

### Non-goals for v1.0
- Predicting where fires will start or spread.
- Providing emergency alerts, evacuation advice, or official incident confirmation.
- Estimating hectares burned from FIRMS hotspot counts.
- Claiming that correlation proves causes of fire activity.
- Automated operational decisions or unrestricted SQL execution.
- Multiple runtime wildfire-answering agents or continuous real-time monitoring. (The project is developed using three separate Codex coding agents: data engineer, backend engineer, and frontend engineer.)

## 4. Target users

| Persona | Need |
|---|---|
| Environmental researcher | Explore hotspot trends and satellite measurement caveats |
| Journalist / NGO analyst | Compare regions and obtain evidence-backed summaries |
| Student / general public | Understand hotspot activity without writing code |

## 5. User journeys and stories

**Journey A — Historical exploration**  
As a user, I can ask, “How many VIIRS hotspots were detected in Riau in September 2023?” and receive a count, date range, satellite product, map, and clear caveat that detections are not confirmed fires.

**Journey B — Regional comparison**  
As a user, I can ask, “Compare monthly hotspot detections in Riau and Central Kalimantan in 2023,” and receive a chart and a summary of differences.

**Journey C — Scientific explanation**  
As a user, I can ask, “What does fire radiative power mean?” and receive a concise explanation with citations to indexed NASA documentation.

**Journey D — Combined analysis**  
As a user, I can ask, “Did hotspot detections increase in Kalimantan in September 2023, and what limitations should I consider?” and receive calculated trends plus retrieved methodological context. The assistant must not invent causes.

**Journey E — Unsupported question**  
As a user, if I ask for burned hectares, confirmed wildfire incidents, or a date outside the available dataset, I receive a transparent limitation rather than fabricated numbers.

## 6. MVP scope and priorities

| ID | Feature | Priority | Acceptance criteria |
|---|---|---|---|
| F-01 | Historical NASA FIRMS ingestion | P0 | Ingest a validated Indonesia subset with source and product metadata |
| F-02 | Geographic and time filters | P0 | Correctly filter by date and supported provinces using documented boundaries |
| F-03 | Natural-language analytical queries | P0 | Answer supported count, trend, and comparison questions from actual data |
| F-04 | Interactive hotspot map | P0 | Display geographic observations or aggregated density with legend and date filters |
| F-05 | Trend and comparison charts | P0 | Visualize calculated monthly counts and region comparisons |
| F-06 | NASA-documentation RAG | P0 | Retrieve relevant passages and show original source URLs |
| F-07 | Grounded answer composition | P0 | Distinguish calculated findings from contextual explanation and uncertainty |
| F-08 | Unsupported-query handling | P0 | Reject or clarify unavailable measures, periods, and causal claims |
| F-09 | Usage limits and guardrails | P0 | Apply server-side request quotas, bounded tool calls, and read-only database access |
| F-10 | Evaluation suite | P0 | Run a reproducible benchmark and publish measured results |
| F-11 | Downloadable analytical summary | P1 | Export an analysis summary with filters and citations |
| F-12 | Near-real-time ingestion | P2 | Deferred to v1.1 |

P0 = required for v1.0; P1 = stretch; P2 = future.

## 7. Data requirements and assumptions

### Primary structured source
- **NASA FIRMS:** historical VIIRS active-fire/hotspot detections. Start with a manageable 2020–2024 or 2020–2025 subset, depending on archive access and completeness.
- Expected fields to validate: coordinates, acquisition date/time, source/satellite, confidence, and fire radiative power (product-dependent).
- Record provenance, extraction date, temporal coverage, satellite product, and any quality filters.
- Use a consistent satellite product for comparisons where possible; do not silently merge instruments with different detection characteristics.

### RAG source
- Official NASA FIRMS product guides, definitions, known limitations, and relevant NASA educational/scientific materials.
- Store document title, URL, publication/update date if available, retrieval date, and chunk identifiers for citations.

### Reference geography
- Province boundary polygons are necessary for province-level analysis. This is reference geometry, not a second wildfire observation source. Identify a suitable legally reusable boundary dataset during feasibility validation.

### Data feasibility gate
Before committing to full implementation, download and inspect an actual sample; verify archive access, coverage, fields, licensing/attribution, coordinate systems, province joins, and at least 10 sample user questions. If validation fails, revise scope and this PRD.

## 8. Functional behavior

1. **Question interpretation:** identify time period, location, requested metric, and whether the question needs analytics, document retrieval, or both.
2. **Analytical execution:** run parameterized, read-only, allowlisted queries/functions against validated hotspot data. Return counts, aggregates, and geospatial coordinates as appropriate.
3. **Document retrieval:** search indexed NASA documentation and provide source-linked passages to the answer generator.
4. **Answer synthesis:** distinguish observed values, methodological context, and unsupported inferences. Show relevant dates, satellite source, and filters.
5. **Visualization:** provide map and chart representations derived from validated query results; never invent plotted values.
6. **Graceful degradation:** if RAG, LLM, or quota is unavailable, keep non-AI historical exploration accessible where possible.

## 9. Proposed technology stack (subject to feasibility validation)

| Layer | Proposed technology | Purpose |
|---|---|---|
| Language | Python 3.12+ | Application, analytics and ingestion |
| Backend | FastAPI + Pydantic | Validated REST endpoints and tool interfaces |
| LLM | OpenAI API (model to be selected after benchmarking) | Natural-language interpretation and grounded responses |
| Agent orchestration | LangGraph | One bounded agent coordinating tool calls |
| RAG components | LangChain components where useful | Document processing and retrieval integration |
| Embeddings | OpenAI embedding API (configurable) | Index and search NASA documentation |
| Vector store | Qdrant | Document embeddings, metadata and retrieval |
| Analytical database | ClickHouse | NASA FIRMS hotspot observations and aggregations |
| Data transformation | Polars | Efficient CSV cleaning and preparation |
| Pipeline scheduling | Python initially; Prefect optional | Historical ingestion and later refresh jobs |
| Geospatial | GeoPandas + Shapely | Assign observations to Indonesian administrative regions |
| Frontend | Next.js + TypeScript + Tailwind CSS + MapLibre GL JS + Recharts | Chat, interactive maps, charts and source inspection |
| Deployment | Docker Compose on fixed-cost VPS | Reproducible deployment with bounded hosting cost |
| Testing | pytest | Unit, integration and security tests |
| Evaluation | Custom gold datasets; Ragas optional | Retrieval relevance, analytical accuracy and grounding |
| Observability | Structured logs; LangSmith optional | Trace tool calls, errors, latency and token usage |

**Architecture choice:** One LangGraph agent with SQL/analytics, geospatial, RAG and visualization tools. The tools are mostly deterministic functions, not separate autonomous agents.

**Budget constraints:** Keep API keys on the server, enforce per-visitor and global quotas, cap model calls per request, and configure API spending controls. ChatGPT Plus does not include OpenAI API usage.

**Data boundary:** NASA FIRMS is the sole wildfire-observation provider for v1.0; NASA technical documentation is the primary RAG source. Province-boundary geometry may come from a separate reference dataset and must be documented.

The final model, embedding provider, detailed schema, API contracts, state transitions, and hosting instance will be decided in `TECHNICAL_DESIGN.md` after data validation.

### Development workflow

Three **Codex coding agents** implement the product in separate worktrees: Data Engineer owns `data/` (NASA acquisition, profiling, transformations, province joins, quality checks, ClickHouse loading); Backend Engineer owns `backend/` (FastAPI, read-only analytics services, NASA-document RAG, LangGraph, security); Frontend Engineer owns `frontend/` (Next.js UI, maps, charts, chat). These are **development agents**, not three runtime LLM agents. All follow `AGENTS.md`, shared contracts, and their respective skills. Data-to-backend interfaces must be approved before parallel integration.

## 10. Nonfunctional requirements

| Area | Requirement |
|---|---|
| Safety | Explicitly label satellite hotspots as detections, not confirmed wildfires |
| Accuracy | Numeric statements and chart points must be derived from query results |
| Security | Read-only database role, allowlisted tools, bounded inputs and retries, secrets stored server-side |
| Cost | Server-side per-visitor and global quotas; API provider spending controls; fixed-cost hosting preference |
| Performance | Initial target: p95 response time below 10 seconds for supported queries on a bounded demo dataset; measure and revise |
| Transparency | Display observation source, temporal coverage, filters, and NASA documentation citations |
| Reliability | Handle empty results, invalid locations, missing dates, failed retrieval, and exhausted quotas |
| Privacy | Avoid collecting personal information beyond minimal abuse-prevention/operational telemetry |
| Reproducibility | Version data extracts, prompts, evaluation datasets, and dependency lockfiles |

## 11. Evaluation and success metrics

Create a manually reviewed benchmark with at least 50 questions for v1.0, spanning counts, trends, region comparisons, NASA concepts, unsupported questions, and adversarial prompts.

| Metric | Initial target |
|---|---|
| Analytical result accuracy | ≥ 90% on supported benchmark questions |
| Retrieval Recall@5 | ≥ 85% on annotated documentation questions |
| Citation support | ≥ 95% of sampled cited factual claims supported by cited sources |
| Unsupported-question handling | ≥ 95% correct abstention/clarification |
| Unsafe query executions | 0 |
| Public demo availability | Usable documented deployment with quotas and graceful fallback |

These are proposed targets, not observed results. Publish actual measurements and failure cases. Evaluate against deterministic reference queries and reviewed documents rather than LLM judgment alone.

## 12. Dependencies and risks

| Risk | Mitigation |
|---|---|
| Historical archive access or coverage differs from expectations | Validate a real extract before architecture commitment |
| Hotspot count mistaken for wildfire count | Persistent UI caveat and explicit metric naming |
| Geographic misclassification | Validate province polygons, boundary joins, and sample points |
| Instrument/product comparability | Track product provenance; avoid unqualified cross-sensor comparisons |
| Unsupported causal explanations | Require supporting evidence; use qualified language |
| LLM hallucination | Ground numbers in SQL and explanations in retrieved sources |
| Unexpected public API costs | Enforce quotas, token budgets, concurrency caps, and provider hard limits where available |
| Small VPS memory pressure | Limit data size, preaggregate, benchmark, and upgrade only if necessary |

## 13. Milestones and release gates

1. **PRD approval:** confirm core user journeys and non-goals.
2. **Data feasibility:** validate a real NASA extract, NASA documents, and province boundaries.
3. **Analytical vertical slice:** real hotspot question → validated calculation → map/chart.
4. **RAG vertical slice:** documentation question → retrieved evidence → cited answer.
5. **Agent integration:** combined questions with bounded tool calls and honest limitations.
6. **Evaluation and security:** benchmark results, adversarial checks, and usage quotas.
7. **Release:** public demo, reproducible setup, README, architecture diagram, and known limitations.

## 14. Open decisions

- Which VIIRS product and historical date range can be accessed reliably?
- Which province boundary dataset and administrative vintage should be used?
- Is province-level analysis sufficient, or are district-level boundaries necessary?
- What is the maximum public demo usage allowance and API spend?
- Is report export necessary for v1.0, or can it wait?

## 15. Definition of done

v1.0 is complete when a new user can ask supported Indonesia hotspot questions, inspect real results on a map/chart, retrieve NASA-grounded explanations with working citations, and encounter clear limits for unsupported questions; the project is deployed with safeguards and includes reproducible evaluation results.
