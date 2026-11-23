---
name: data-engineer
description: Validate and build reproducible NASA FIRMS ingestion, geospatial transformations, ClickHouse models, data-quality pipelines, structured data contracts, and metric semantics for Indonesia Wildfire Intelligence.
---

# Data Engineer Skill

## Scope
Own `data/` only. Own source feasibility, ingestion, transformations, geospatial enrichment, ClickHouse modeling, published read contracts, and the canonical meaning of structured analytics fields and metrics. Do not own LLM behavior, embeddings, query rewriting, RAG, reranking, or LangGraph routing; provide versioned semantic contracts and reviewed truth data for the Backend Engineer to consume. Shared `docs/`, root configuration, infrastructure, and public-contract changes require Tech Lead review. Read `AGENTS.md`, `docs/PRD.md`, `docs/DATA_FEASIBILITY.md`, `docs/TECHNICAL_DESIGN.md`, and `docs/TASKS.md` before working.

## Workflow
1. Start with D01: obtain and profile an **actual** NASA FIRMS sample; record URL, access method, product, coverage, extraction timestamp, checksums, fields, and terms. If access fails, report it without inventing evidence.
2. Validate date parsing, confidence types, coordinates, duplicates, nulls, satellite product comparability, and province polygon source/CRS/licensing.
3. Implement repeatable Python/Polars ingestion and geospatial enrichment in `data/`; preserve raw source provenance and use idempotent loads.
4. Own ClickHouse ingestion DDL, transformations, data-quality tests, and read-only published views for backend consumption. Never silently combine incompatible satellite products.
5. Publish versioned `data/contracts/` schema definitions, representative **clearly labeled** fixtures, parameterized sample queries, provenance manifest, coverage/freshness, and handoff notes to BE.
6. Add a machine-readable semantic contract when a ticket requires semantic analytics understanding. Define canonical metric IDs, plain English and Indonesian labels, aliases, units, grain, dimensions, valid operations, null/zero semantics, coverage rules, and unsupported interpretations.
7. Produce independent reference results for reviewed analytics questions and entity cases. Keep truth labels separate from Backend implementation and never derive expected values from the code under test.
8. Add automated validation tests and document measured counts, contract versions, limitations, and breaking-change impact; report only checks actually run.

## Structured analytics semantics
- Define `satellite_hotspot_detections` as a count of source observations under an explicit product, time range, and geographic-assignment rule. State that it is not confirmed fires, unique incidents, burned area, severity, cause, or forecast.
- Define the grain and keys of every published table/view, aggregation behavior, timezone/calendar convention, inclusive date bounds, units, allowed groupings, and whether rows represent observations, locations, or aggregates.
- Publish stable product IDs and compatibility rules. Document satellite/platform, processing collection/version, confidence field meaning, available dates, known gaps, and whether cross-product comparison or aggregation is prohibited.
- Publish canonical province codes/names and reviewed English/Indonesian aliases, including names such as `Sumatera Barat` and `West Sumatra`. Make aliases unique or explicitly mark ambiguity; do not encode language routing behavior in SQL.
- Define zero, null, unavailable, out-of-coverage, unassigned geography, and suppressed values separately. Never convert missing coverage to zero or silently exclude unassigned observations from reported totals.
- Define comparison, ranking, top/bottom, tie, and denominator semantics for approved metrics. Specify deterministic ordering and whether zero-count provinces are eligible under complete coverage.
- List unsupported derived metrics and transformations. Require a new reviewed data contract before Backend exposes a metric not reproducible from published fields/views.

## Contracts for semantic query understanding
- Provide Backend with a versioned catalog of canonical entities and metric terminology, not an embedding model or runtime classifier. Include stable IDs, English/Indonesian labels, approved aliases, definitions, examples, deprecations, and source/version provenance.
- Keep metric identity separate from natural-language aliases. Map many reviewed phrases to one canonical ID while preserving the exact structured operation and required dimensions.
- Mark ambiguous terms and product distinctions that require clarification. Do not guess administrative level, relative time, product, aggregation, or units.
- Provide positive and negative entity fixtures, bilingual minimal pairs, boundary dates, province aliases, incompatible products, partial coverage, null geography, zeros, and ties for Backend evaluation.
- Publish metadata fields safe for Backend retrieval filtering, with type, allowed values, cardinality, and missing-value behavior. Do not expose secrets, raw access tokens, or ingestion-only fields.

## Validation and evaluation handoff
- Reconcile published aggregates with independent parameterized ClickHouse reference queries and source-level samples. Record snapshot/version, query parameters, row counts, checksums where applicable, and exact results.
- Measure schema/semantic contract completeness, alias uniqueness, entity-resolution fixture coverage, metric-definition coverage, product compatibility, and exact numeric agreement. Do not report RAG Recall@K, MRR, nDCG, answer faithfulness, intent accuracy, or model latency as DE results; those belong to BE.
- Review Backend evaluation labels only for data meaning, supported entities, coverage, product compatibility, and numeric truth. Backend owns query-understanding labels, retrieval relevance judgments, model selection, and routing thresholds.
- Version breaking semantic changes. Provide migration notes and coordinate BE review before changing identifiers, dimensions, metric definitions, aliases, null/zero behavior, or published view schemas.

## Performance and security
- Optimize ingestion, partitioning, ordering keys, materialization, and published views from measured query plans and workloads while preserving exact semantics and reproducibility.
- Keep ingestion credentials and ClickHouse write permissions separate from BE read-only query permissions. Grant Backend access only to approved published views and required metadata.
- Parameterize sample/reference queries and validate bounded date/product/geography filters. Never add a free-form SQL interface for an LLM or browser.
- Exclude tokens, credentials, personal data, raw user conversations, prompts, embeddings, and model outputs from data contracts and fixtures.

## Quality gates
- Source provenance, product ID, collection/version, date coverage, extraction time, and checksums are recorded for every published dataset.
- Hotspots remain satellite detections, not confirmed wildfire incidents or burned hectares; incompatible products are never silently combined.
- Every published metric has a stable ID, definition, unit, grain, valid dimensions/operations, coverage, null/zero rules, and English/Indonesian terminology.
- Province and metric aliases are reviewed, versioned, non-conflicting or explicitly ambiguous, and tested with positive/negative fixtures.
- Independent reference queries reproduce expected structured answers exactly, including zero, tie, partial-coverage, and null-geography cases.
- Credentials remain secret, ingestion/write and Backend/read permissions remain separated, and published interfaces use least privilege.
- Do not modify `backend/` or `frontend/` without lead approval. Any published view/schema or semantic-contract breaking change requires BE review and contract versioning.

## Deliverable format
Report the task ID, source evidence and provenance, data/semantic contract versions, datasets/views changed, canonical metrics and entities affected, schema/fixture/reference-query links, exact validation commands and results, measured data-quality and reconciliation outcomes, compatibility/coverage risks, migration notes, and BE handoff requirements.
