# Codex Repository Instructions

This repository implements **Indonesia Wildfire Intelligence Agent v1.0**. The Data Engineering, Backend, and Frontend Codex coding agents and the Lead DevOps Engineer operations agent are **development roles**; the deployed application uses **one bounded LangGraph runtime agent**.

## Read first
1. `docs/PRD.md` — product scope and acceptance criteria.
2. `docs/DATA_FEASIBILITY.md` — dataset verification gate and source constraints.
3. `docs/TECHNICAL_DESIGN.md` — architecture and stack.
4. `docs/API_CONTRACT.md` — backend/frontend contract.
5. `docs/TASKS.md` — canonical ticket status, lifecycle, owners, dependencies, acceptance, and approval record.

## Non-negotiable rules
- Do not invent NASA data, dataset coverage, citations, metrics, successful downloads or test results.
- Satellite hotspots are **detections**, not confirmed wildfire incidents or burned hectares.
- NASA FIRMS is the only wildfire-observation provider for v1.0; province polygons are separate reference geometry.
- Do not bypass the data-feasibility gate or silently mix satellite products.
- Use typed contracts, tests, least privilege, parameterized queries and server-side secrets.
- Never expose LLM keys or database credentials to the browser.
- No out-of-scope features without approval.
- Work in task-sized commits/PRs; summarize tests actually run and limitations.

## Ownership and collaboration
- **Data Engineer Codex:** `data/`, NASA data feasibility, ingestion, transformations, geospatial joins, ClickHouse data modeling, data quality, and data tests. Follow `.agents/skills/data-engineer/SKILL.md`.
- **Backend Codex:** `backend/`, API services, read-only analytics interfaces, RAG, LangGraph, and backend tests. Follow `.agents/skills/backend-engineer/SKILL.md`.
- **Frontend Codex:** `frontend/`, typed client, UI, maps/charts and frontend tests. Follow `.agents/skills/frontend-engineer/SKILL.md`.
- **Lead DevOps Engineer Codex:** infrastructure preparation, Docker/Compose, CI/GHCR, shared Caddy/VPS integration, persistence/backups, security, monitoring, rollback, and release-readiness evidence. Follow `.agents/skills/lead-devops-engineer/SKILL.md`; the native subagent is `.codex/agents/lead-devops-engineer.toml`. Do not change production without explicit user/Tech Lead approval.
- **Shared:** `docs/`, `infrastructure/`, root configuration and contract changes require lead review. Never concurrently edit shared files in multiple worktrees.
- DE, BE, FE, and DevOps work on separate branches/worktrees when implementing assigned tickets. DE publishes versioned data contracts and sample fixtures for BE; FE uses API contract fixtures until endpoints are available. Data ingestion credentials and database write access belong only to DE. BE gets read-only analytics access.

## Workflow
1. Read the ticket and lifecycle rules in `docs/TASKS.md`; do not restart implemented or completed tickets.
2. Claim only a `READY` ticket (or perform explicitly requested review work on an `IN_REVIEW` ticket) in the role's own branch/worktree.
3. Confirm required decisions have been approved; ask before changing scope, architecture, shared documentation, or a contract.
4. Implement the minimal testable vertical slice and keep mock/proposal artifacts visibly labeled.
5. Run relevant checks; do not claim checks you did not run.
6. Move implementation only to `IN_REVIEW` and report changed files, exact test results, limitations, and next dependency. Only the Tech Lead may record `DONE` or approve a gate/shared contract.

## Skills
Project skill definitions live in `.agents/skills/`. They provide specialized workflows; they **do not automatically spawn separate Codex sessions**. Load the relevant skill in each session or use Codex's supported skill discovery behavior. The Lead DevOps Engineer additionally has a project-scoped native Codex subagent definition; ask Codex to spawn `lead-devops-engineer` for an assigned infrastructure task.
