# G2 Technical Design Review

**Date:** 2026-10-22  
**Reviewer:** Lead Software Engineer / Project Coordinator  
**Decision state:** Approved by the Tech Lead on 2026-10-22  
**Recommendation disposition:** Accepted with the scope and exclusions below

## Inputs reviewed

- Approved G1 feasibility baseline in `docs/DATA_FEASIBILITY.md` and `docs/TASKS.md`
- Approved D04 data contract v1.0.0, JSON Schema, synthetic fixture, and handoff evidence
- Approved A01 API contract v1.0.0, OpenAPI snapshot, shared synthetic fixture, and BE/FE reports
- `docs/PRD.md`, `AGENTS.md`, DE/BE/FE role rules, current backend/frontend seams, and canonical backlog

## Review findings

| Area | Finding | Gate impact |
|---|---|---|
| Runtime topology | One bounded LangGraph runtime agent with deterministic allowlisted tools matches the PRD and backend seam | Accept |
| Product and time window | Technical design now uses approved `VNP14IMG.002_SNPP_FIRMS_SP`, calendar 2023 UTC | Accept |
| Coverage semantics | Known gaps remain null/incomplete with evidence; zero is allowed only for verified complete coverage | Accept |
| Province analytics | Exact offline point-in-polygon against the approved OSM-derived 38-province snapshot; no coercion; ODbL attribution retained | Accept |
| Data interfaces | Design names exactly the four D04 read-only interfaces and preserves contract version checks and least privilege | Accept |
| Public API | `/api/v1`, non-streaming JSON, request IDs, typed errors, capped GeoJSON, source/coverage metadata, and chat payloads align with A01 | Accept |
| Security | Server-side secrets, parameterized read-only queries, bounded tools, quotas/timeouts, prompt-injection handling, and redacted logs are assigned to later tickets | Accept |
| Role boundaries | DE writes/publishes; BE reads/serves; FE calls FastAPI only; shared contract changes remain versioned and reviewed | Accept |
| Delivery order | D05 and B02 may proceed in parallel after G2; D06/B04, I01/I02, Q01, and R01 retain their dependencies | Accept |

The pre-review technical design was stale rather than architecturally incompatible: it
still described the data model as provisional and listed the already-approved product,
window, and province geometry as open. The reconciled design removes those stale
statements without changing D04 or A01 semantics.

## Verification performed

1. DE contract validator:
   `backend/.venv/bin/python data/scripts/validate_data_contract.py --schema data/contracts/hotspot_data_contract_v1.0.0.schema.json --fixture data/contracts/fixtures/hotspot_data_contract_v1.0.0.fixture.json --boundary-provenance data/provenance/d03b_reusable_boundary.json`
   — passed; contract `1.0.0`, 38 approved provinces, 2 observations, 3 coverage rows,
   2 fixture provinces, 1 batch, and 2 reference queries validated.
2. BE consumer/API/OpenAPI tests:
   `.venv/bin/pytest tests/contract/test_d04_data_contract_consumer.py tests/contract/test_a01_api_contract.py tests/contract/test_a01_openapi_snapshot.py`
   — 29 tests passed.
3. FE shared API fixture:
   `npm test -- src/lib/api/contract-fixture.test.ts`
   — 1 file and 4 tests passed.

These checks verify current contract artifacts and consumers. They do not prove real
ingestion, physical ClickHouse DDL, live analytics, production LangGraph behavior,
end-to-end integration, performance, accessibility, deployment, or public security.

## Decisions frozen by G2 approval

- Single bounded runtime agent; no runtime multi-agent supervisor.
- D04 data contract v1.0.0 and A01 API contract v1.0.0 are the shared interfaces.
- One approved NASA product/window and approved province reference for v1.0.
- Coverage gaps and unknown coverage are not zero-filled.
- BE accesses published ClickHouse interfaces read-only with parameterized queries.
- FE communicates with FastAPI only and receives bounded/sanitized map features.
- `/api/v1` uses non-streaming JSON for v1.0.
- Implementation follows the dependency order recorded in `docs/TASKS.md`.

## Explicitly deferred decisions

The following remain owned by downstream tickets and do not need to be invented at G2:

- D06: physical ClickHouse engines, partitioning, ordering, and materialization.
- B04/B05: benchmarked model/embedding choice, final runtime budgets, and paid-service activation.
- B05/R01: public authentication, quota values, spend ceilings, and abuse controls.
- I02/R01: production map tile provider/terms and deployment environment.
- R01: Qdrant hosting, VPS size, TLS, monitoring, backup, and rollback.

Any deferred choice that changes a frozen interface must return through a versioned
contract review rather than being treated as implementation freedom.

## Approval effect

Tech Lead approval of G2 unblocks D05 and B02 only. It does not mark those tickets
implemented, approve paid services, authorize public deployment, or waive later review
and release gates.
