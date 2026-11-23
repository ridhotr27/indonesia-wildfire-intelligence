# A01 frontend contract alignment

**Status:** Frontend compatibility evidence accepted; A01 approved 2026-10-22  
**Date:** 2026-10-22  
**Contract candidate:** API v1.0.0

## Outcome

Frontend transport types and visibly synthetic mock fixtures now match the v1.0.0 API
candidate. Metadata field names, source attribution, nullable summary totals,
period/response completeness, coverage issues, bounded GeoJSON metadata and sanitized
properties, typed chat payloads, and error codes align with FastAPI.

The dashboard safely displays an unavailable total and partial-coverage label. Mock mode
remains the default and does not imply that NASA observations, live analytics, Qdrant,
or an LLM were used.

## Shared fixture evidence

`frontend/src/lib/api/contract-fixture.test.ts` reads the same committed fixture used by
backend tests. It covers:

- explicitly synthetic/versioned metadata;
- complete nonzero and complete zero responses;
- partial coverage with available-only totals;
- wholly unavailable coverage with null totals/counts;
- WGS84 bounded and empty GeoJSON results;
- unsupported chat and typed error examples.

## Boundaries

- I02 owns real browser-to-backend integration and remains blocked.
- Accessibility and end-to-end release evaluation remain Q01 scope.
- A01 and G2 require separate Tech Lead decisions.
