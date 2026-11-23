# I02 Live API Integration Review

**Ticket:** I02 — Replace UI mocks with live API  
**Implementation status:** Ready for lead review  
**Scope:** `frontend/` only; no backend or shared-contract changes

## Outcome

The dashboard now uses the frozen v1 metadata, summary, GeoJSON, and chat contracts through a real-mode client that fails closed. Synthetic fixtures remain available only when `WILDFIRE_FRONTEND_API_MODE=mock` is set explicitly. Real mode rejects metadata, summary, or map payloads labeled `mock`, rather than silently substituting fixture data.

Runtime configuration is served by the dynamic same-origin `/api/runtime-config` route. It reads `WILDFIRE_FRONTEND_API_MODE` and `WILDFIRE_PUBLIC_API_BASE_URL` at request time; only a credential-free HTTP(S) public API URL is returned. The browser still calls FastAPI directly, preserving backend per-client controls. FastAPI must allowlist the exact frontend origin through `WILDFIRE_CORS_ORIGINS`.

## Integrated behavior

- Metadata drives product, province, and UTC date filters.
- Summary values drive metric cards and the Recharts series without numeric fallback.
- GeoJSON drives the bounded MapLibre layer and exposes `truncated` status.
- Chat renders answers, nullable metrics, chart/map evidence counts, NASA citation links, and limitations.
- Complete zero is distinguished from partial or wholly unavailable coverage.
- Known-gap dates remain unavailable, never zero-filled.
- Typed 429, 503, and 504 responses have distinct, actionable UI messages.
- Runtime guards reject a wrong API version or malformed metadata, summary, map, and chat success payload without exposing payload contents.
- A failed runtime-config lookup is evicted from the client cache so the user-facing retry path can recover.
- Map popups use DOM text nodes rather than HTML interpolation.
- A map update received before MapLibre's delayed `load` event installs the newest GeoJSON, not stale initial props.
- Mock/verified labels derive from response provenance instead of build-time assumptions.

## Verification

Run from `frontend/`:

| Check | Result |
|---|---|
| `npm test` | 8 files, 24 tests passed |
| `npm run typecheck` | Passed |
| `npm run lint` | Passed |
| `NODE_ENV=production npm run build` | Passed; `/` static and `/api/runtime-config` dynamic |
| Browser bundle secret/config scan | No OpenAI key, ClickHouse password/reader identity, client salt, or key-shaped token matched |

The HTTP-client suite is the reproducible integration-equivalent harness. It exercises metadata → summary → map → chat, a NASA HTTPS citation, an exact numeric API payload (`687`), explicit empty/gap/truncation payloads, non-verified-response rejection, wrong-version and malformed-success rejection, and typed 429/503/504 errors. Separate regressions cover recovery after runtime-config failure and the delayed MapLibre load race. Existing contract and component tests remain green.

## Discrepancies and limitations

- No persistent public FastAPI/ClickHouse/Qdrant deployment was available in this frontend task, so this report does not claim a browser run against a continuously hosted service or production latency.
- Playwright is not installed in the frontend package. Contract-level Vitest journeys are the current equivalent; full browser E2E remains appropriate for Q01/deployment.
- The live citation path is contract-tested with an HTTPS NASA-shaped response, but this run does not repeat B04's live Qdrant retrieval validation.
- Public deployments must set an exact CORS origin and review OSM tile capacity/terms. The development `tile.openstreetmap.org` endpoint is not asserted suitable for public production traffic.
- The UI currently visualizes the deterministic dashboard chart/map. Chat-provided chart/map payloads are disclosed as bounded evidence counts rather than rendered as a second visualization.

## Files changed

- `.env.example`, `README.md`
- `src/app/api/runtime-config/route.ts` and test
- `src/lib/api/{index,http-client,runtime-config,types,validation}.ts` and integration tests
- `src/components/dashboard/{dashboard,metric-cards,trend-chart,hotspot-map}.tsx`
- `src/components/chat/chat-panel.tsx` and its test setup
- this review report
