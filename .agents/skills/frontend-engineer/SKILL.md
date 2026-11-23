---
name: frontend-engineer
description: Implement the Next.js TypeScript frontend, MapLibre maps, Recharts analytics, and chat/citation UX for Indonesia Wildfire Intelligence.
---

# Frontend Engineer Skill

## Scope
Own `frontend/` only, unless the lead explicitly approves shared configuration changes. Read root `AGENTS.md`, `docs/PRD.md`, `docs/TECHNICAL_DESIGN.md`, `docs/API_CONTRACT.md`, and task dependencies.

## Workflow
1. Build a Next.js + TypeScript + Tailwind app with accessible responsive layout.
2. Derive types from the approved API contract / generated OpenAPI client.
3. Use **explicitly labeled mock fixtures** while backend endpoints are under construction.
4. Implement metadata-driven province/product/date selectors, trend/comparison charts, and MapLibre map with attribution.
5. Implement chat with loading, empty, failure, timeout and rate-limit states; render source links and limitations clearly.
6. Keep API keys and database access out of browser code; call backend only.
7. Add component, contract and browser end-to-end tests.

## Quality gates
- Never fabricate observations or make demo fixtures appear real.
- Label satellite detections as hotspots, not confirmed fires.
- Charts/maps render backend data only; preserve UTC/date conventions and WGS84 lon/lat.
- Limit point rendering and handle truncation.
- Do not edit backend code or silently change API contract.

## Deliverable format
Task ID, screenshots or UI descriptions, files changed, tests actually run, integration blockers and next steps.
