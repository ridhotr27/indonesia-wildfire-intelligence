# Indonesia Wildfire Intelligence — Frontend

Next.js dashboard for exploring Indonesia satellite hotspot detections. Real API mode is the fail-closed default; a clearly labeled synthetic mode remains available only when explicitly configured.

## Requirements

- Node.js 20 or newer
- npm 10 or newer

## Local development

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). The frontend reads API configuration at request time, so one build can be promoted between environments. No credentials are needed for mock mode.

## API modes

The browser talks only to the FastAPI service; it never connects directly to ClickHouse, Qdrant, NASA APIs, or an LLM provider.

```dotenv
# Default: verified FastAPI responses only
WILDFIRE_FRONTEND_API_MODE=real
WILDFIRE_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1

# Explicit local fixture mode
WILDFIRE_FRONTEND_API_MODE=mock
```

`WILDFIRE_PUBLIC_API_BASE_URL` is intentionally returned to the browser and must contain only an HTTP(S) origin/path without credentials. Configure FastAPI `WILDFIRE_CORS_ORIGINS` with the exact frontend origin (for example `http://localhost:3000`). Never put database, model, vector-store, or API credentials in frontend configuration.

Real mode accepts metadata, summary, and map responses only when their provenance is `verified`. A mock or mislabeled analytics response causes an honest dependency error; the UI never substitutes fixtures after a live failure.

Mock mode includes optional error scenarios for manual QA: ask a chat message containing `rate limit` or `timeout`. Asking about burned `hectares` exercises the unsupported-query response. Mock mode is not suitable for deployment or evaluation evidence.

## Quality checks

```bash
npm test
npm run lint
npm run typecheck
npm run build
```

## Structure

```text
src/
├── app/                  # Next.js App Router shell and global styles
├── components/
│   ├── chat/             # Conversation, citations, limitations, errors
│   ├── dashboard/        # Filters, metrics, MapLibre map, Recharts trend
│   └── ui/               # Small reusable visual primitives
├── lib/api/              # Mirrored v1 types, HTTP client, mock client/fixtures
└── test/                 # Shared Vitest setup
```

## Data and map notes

- All mock counts and coordinates are synthetic UI fixtures and are visibly labeled.
- Hotspots are satellite thermal-anomaly detections, not confirmed wildfire incidents or burned-area estimates.
- Real filter options and available date coverage are loaded from `GET /metadata`.
- Complete zero results are labeled separately from unavailable or partially covered ranges.
- The UI surfaces backend truncation and preserves nullable totals/chart points for known satellite gaps.
- The v1 contract distinguishes complete zero results, partial coverage, and wholly unavailable ranges; unavailable totals remain `null`, never synthetic zeroes.
- GeoJSON coordinates follow WGS84 `[longitude, latitude]` order and point responses are capped.
- The basemap uses OpenStreetMap tiles and displays provider attribution. Production deployment must review the selected tile provider's usage policy and capacity.
