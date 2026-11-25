# Wildfire private deployment operations

This procedure uses one Wildfire Compose project on the existing VPS. R01 remains `BACKLOG`, Q01 retains a no-go recommendation, and public release requires separate Tech Lead approval. Keep Wildfire private; do not alter DNS, shared Caddy, or portfolio services.

## Experimental low-memory profile

`docker-compose.low-memory.yml` is an opt-in overlay. The original `docker-compose.prod.yml` remains the rollback baseline. It sets container ceilings of 1024 MiB ClickHouse, 384 MiB backend, 256 MiB frontend, and 1024 MiB Ollama (1664 MiB without Ollama; 2688 MiB with it). The ClickHouse config also bounds server/query memory, caches, query threads, concurrency, and external sort/group-by spill. Backend remains one worker with four concurrent requests; Next.js uses a 160 MiB V8 heap ceiling. Ollama remains an optional profile with one loaded model, one parallel request, 2048 context, and immediate idle unload. These settings are experimental limits, not observed usage or proof that startup and queries succeed.

Validate syntax locally without revealing resolved secrets:

```bash
docker compose --env-file .env.example -f docker-compose.prod.yml -f docker-compose.low-memory.yml config --quiet
docker compose --env-file .env.example -f docker-compose.prod.yml -f docker-compose.low-memory.yml --profile local-llm config --quiet
```

After separate approval for a **private** host experiment, use the host's protected `.env.production` and the same Compose file order. Start ClickHouse, backend, frontend, then optional Ollama one service at a time with `docker compose --env-file .env.production -f docker-compose.prod.yml -f docker-compose.low-memory.yml up -d <service>`. Before and after each start and representative approved analytics/map/RAG request, record `docker stats --no-stream`, `free -h`, `swapon --show`, `docker compose --env-file .env.production -f docker-compose.prod.yml -f docker-compose.low-memory.yml ps`, container `memory.current`/`memory.peak`/`memory.events` from the cgroup, CPU, latency, and portfolio health. Inspect ClickHouse effective settings with `SELECT name, value FROM system.settings WHERE name IN ('max_memory_usage','max_threads','max_insert_threads','max_bytes_before_external_group_by','max_bytes_before_external_sort')` and confirm query parity with the approved DE reference results. Test the maximum bounded map response and representative NASA RAG questions. An Ollama test additionally requires the existing approved model and BE-approved embedding/index profile; do not pull a model or enable `local_grounded` solely to exercise this overlay. Stop the experiment at OOM, sustained swap activity, failed parity, or portfolio degradation.

Rollback the experiment by recreating Wildfire services with **only** `docker-compose.prod.yml` and the prior approved image SHA; do not delete named volumes or run `down --volumes`. DE owns any data-release rollback. Keep public routing disabled throughout the experiment.

## Prerequisites

The host must have the reviewed checkout at `/opt/indonesia-wildfire-intelligence`, a mode-0600 `.env.production` supplied through the approved secret path, private Compose networks, and an off-host backup/restore record. Keep deployment credentials and `.env.production` out of GitHub and logs. Verify the checkout SHA, passing CI, and immutable GHCR image digests before any pull. The existing CI publishes images only after successful checks on `main`; a branch build is not a deployable image.

For an approved update to the single private Wildfire project, run `infrastructure/scripts/deploy-release.sh <full-approved-main-SHA>` on the host after the preflight checks. It validates the checkout SHA, uses the low-memory overlay, pulls immutable SHA-tagged backend/frontend images, recreates those containers without dependencies or volumes, waits for container health, and restores the previous SHA on failure. The first deployment has no previous SHA; its failure requires operator intervention. Keep `.last-good-image-sha` outside Git; it is a local rollback pointer, not evidence of data compatibility. Never use `docker compose down --volumes`.

Before each dispatch, verify backup freshness and a restore test, image digests, free memory/disk, current portfolio status, ClickHouse release and grants, and schema compatibility. Do not run destructive migrations in the deploy job. After health succeeds, run private metadata, analytics, NASA citation, and frontend browser smokes, plus portfolio checks. A container health pass alone is insufficient for release acceptance. If any check fails, restore the prior SHA and use the DE append-only data rollback procedure if a separately approved data release changed.

Monitor `free -h`, `swapon --show`, `df -h`, `df -i`, `docker stats --no-stream`, `docker compose ps`, ClickHouse errors and persistent log growth, API 5xx/p95, index compatibility, Caddy certificate expiry, and portfolio availability. Set a low-cost external HTTPS probe and record alert recipient and response before public release. Off-host encrypted backups must include ClickHouse data/metadata, RAG index and manifest, deployed SHA/digests, and secrets in a separate restricted store. Test restoration into a new empty volume; never overwrite the only production copy.
