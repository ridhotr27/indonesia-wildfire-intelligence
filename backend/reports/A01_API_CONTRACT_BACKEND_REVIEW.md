# A01 backend API contract review

**Status:** Backend compatibility evidence accepted; A01 approved 2026-10-22  
**Date:** 2026-10-22  
**Contract candidate:** API v1.0.0

## Outcome

FastAPI now generates the v1.0.0 review-candidate schema described in
`docs/API_CONTRACT.md`. The committed OpenAPI snapshot is checked byte-semantically
against `create_app().openapi()`, and backend models validate the same synthetic fixture
consumed by the frontend.

The candidate adds the D04 semantics missing from the original draft: nullable totals,
complete/partial/unavailable states, dated coverage issues with evidence, bounded
GeoJSON response metadata, sanitized point properties, typed chat payloads, stable
success request IDs, and a closed error-code set. No ClickHouse query, NASA observation,
LLM call, or live integration was introduced.

## Evidence

- `backend/tests/contract/test_a01_api_contract.py` validates all shared success/error
  fixtures and rejects gap-to-zero coercion, known gaps without evidence, invalid WGS84
  coordinates, and mismatched feature counts.
- `backend/tests/contract/test_a01_openapi_snapshot.py` verifies the committed OpenAPI
  document exactly matches the FastAPI application and contains all five v1 routes and
  required coverage/error schemas.
- Existing integration tests cover malformed inputs, semantic filter errors, request
  IDs, capped map responses, and the transparently unsupported chat scaffold.

## Boundaries

- Backend responses remain synthetic `MOCK_ONLY` data.
- B02 owns read-only ClickHouse analytics; B04 owns the bounded runtime agent.
- G2 remains separate and unapproved.
- A01 still requires explicit Tech Lead approval before this candidate is immutable.
