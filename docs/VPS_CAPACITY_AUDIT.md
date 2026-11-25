# R01-A — VPS capacity audit

**Status:** Incomplete: configured VPS SSH target unavailable in this environment
**Recommendation:** **NO-GO** for private deployment until host measurements and a reviewed capacity budget exist
**Scope:** Read-only audit only; Q01 no-go and R01 `BACKLOG` unchanged

## Access and evidence

The user authorized read-only SSH to the existing Biznet Gio VPS. The only entry in the local SSH config is `github-jamboredev`; `ssh -G github-jamboredev` resolves to `github.com`, user `ridhotr27`, port 22. It is not a VPS target. No other configured VPS alias was found, so no SSH connection was attempted. No host or Docker measurement below is claimed as observed. No keys, secrets, container environment, or logs were read.

| Resource | User-provided or repository evidence | Measured on VPS |
|---|---|---|
| RAM and swap | User reports 4 GiB RAM, 2 GiB swap | Unavailable |
| CPU, load, memory pressure | Unknown | Unavailable |
| Disk | User reports approximately 58 GB total; free space unknown | Unavailable |
| Portfolio and shared Caddy | User reports live `ridho-portfolio` and `shared-edge` Compose projects with HTTPS | Container usage and limits unavailable |
| Docker networks and ports | Wildfire proposes external `wildfire_edge`; shared Caddy network and port ownership unknown | Unavailable |

## Preliminary budget from repository configuration

`docker-compose.prod.yml` and `.env.production.example` currently cap ClickHouse at 3 GiB, FastAPI/RAG at 1 GiB, frontend at 512 MiB, and optional Ollama at 1 GiB. Runtime caps total **4.5 GiB without Ollama** and **5.5 GiB with Ollama**, before Ubuntu, Docker, the live portfolio, shared Caddy, kernel cache, and initialization jobs. Caps are ceilings, **not measured idle or peak consumption**. Swap cannot be treated as available working RAM for reliable inference or portfolio response time.

| Service | Current cap | Provisional private-test ceiling to evaluate, **not approved** | Main risk |
|---|---:|---:|---|
| ClickHouse | 3 GiB | 1 GiB | Startup, parts/merges and ingestion may exceed cap |
| FastAPI + local RAG | 1 GiB | 768 MiB | Index loading and request concurrency |
| Frontend | 512 MiB | 384 MiB | Next.js runtime peak |
| Ollama, one small quantized model | 1 GiB | 768 MiB | Model plus KV cache and CPU latency; 1 GiB may already be insufficient |
| **Wildfire total** | **5.5 GiB** | **2.875 GiB** | Leaves only 1.125 GiB of reported RAM for OS, Docker, Caddy, portfolio and headroom |

The provisional ceilings are an arithmetic stress case, not a recommendation to apply. There is no defensible safe per-service limit or peak safety margin until host measurements and isolated service tests establish actual peaks. Keep Ollama disabled by default, one loaded model and one parallel request in any later approved experiment, and use a bounded context. Do not lower ClickHouse or application limits blindly to force this stack onto the host. A larger VPS or separate private inference host is likely necessary; off-host Ollama also requires a reviewed backend change.

Disk feasibility is likewise unknown. The audit must measure free space, inodes, Docker images/volumes, portfolio data, ClickHouse data/log growth, RAG index, model cache, and room for image pulls and rollback. The backup destination must be off-host and verified. Network compatibility cannot be confirmed until the actual Caddy container network, Docker subnets, port bindings, and Wildfire edge-network collision risk are inspected.

## Safe manual collection on the VPS

Run these commands yourself in an existing trusted VPS session, or provide the configured VPS SSH alias so this read-only audit can resume. Share redacted output only. These commands do not print container environment variables, secrets, private keys, or full Compose configuration.

```bash
date -u
hostnamectl --static
nproc
uptime
free -h
swapon --show
df -h
df -i
docker compose ls
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.BlockIO}}'
docker network ls
ss -ltn
docker system df
```

For container-specific limits and network membership without environment values:

```bash
docker inspect --format '{{.Name}} memory_bytes={{.HostConfig.Memory}} cpus_quota={{.HostConfig.NanoCpus}} networks={{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}' $(docker ps -q)
```

Capture at least idle and representative portfolio traffic snapshots at different times without generating load. Redact hostnames, image repository names, public IPs, and internal network details if sharing beyond the project team. Do not run `docker inspect` without the restricted format above; full output may include secrets. Do not run configuration rendering or benchmark/load commands during this audit.

## Decision and next action

**NO-GO for private deployment on the current evidence.** This is an evidence blocker, not proof that the physical host can never run a reduced profile. The current configured caps exceed reported RAM, the portfolio baseline is unknown, free disk is unknown, and shared-network compatibility is unverified. The next action is to provide the existing VPS SSH alias or the safe command output above. Then record actual idle/peak use, headroom, proposed tested limits, disk budget, and portfolio availability before requesting separate private-deployment approval. Public release still requires Q01/R01 gate disposition.
