# Biznet Gio Deployment Guide

This guide prepares a manual first deployment of Indonesia Wildfire Intelligence to an Ubuntu VPS. It does not authorize a production release, provision infrastructure, modify the separate portfolio repository, or enable automated deployment.

## Recommended starting VPS

For the default extractive/hashing profile and the currently documented dataset scale, start with:

- 4 vCPU
- 8 GiB RAM
- 160 GiB SSD/NVMe, with disk monitoring and a growth plan
- Ubuntu 24.04 LTS
- A separate backup destination outside the VPS

The Compose defaults reserve up to 3 GiB for ClickHouse, 1 GiB for FastAPI/RAG, 512 MiB for Next.js, and 256 MiB for the optional project Caddy. The remainder is needed by the kernel, Docker, filesystem cache, backup operations, and the existing portfolio application. If the portfolio has meaningful load, use at least 16 GiB RAM or separate the workloads.

The optional `qwen2.5:1.5b` plus `all-minilm` Ollama profile is not part of this baseline. CPU inference can materially increase latency and memory pressure; start testing it only on at least 8 vCPU and 16 GiB RAM, measure the actual model allocation, and consider a separate inference host. The current backend rejects non-loopback Ollama URLs, and it has no external cloud-LLM adapter, so moving inference off-host requires a reviewed application change.

## 1. Ubuntu and SSH preparation

Create a non-root operator with sudo access, install security updates, and use SSH keys:

```bash
sudo apt update
sudo apt full-upgrade -y
sudo adduser deploy
sudo usermod -aG sudo deploy
sudo install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
```

Copy and verify the operator's public key before changing SSH policy. Then set the following in `/etc/ssh/sshd_config.d/99-hardening.conf`:

```text
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
AllowUsers deploy
```

Validate and reload without closing the current session:

```bash
sudo sshd -t
sudo systemctl reload ssh
```

Enable automatic security updates and a firewall:

```bash
sudo apt install -y unattended-upgrades ufw fail2ban ca-certificates curl
sudo dpkg-reconfigure -plow unattended-upgrades
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 443/udp
sudo ufw enable
```

Only the shared reverse proxy should bind ports 80/443. Do not open ClickHouse 8123/9000, FastAPI 8000, Next.js 3000, or Ollama 11434.

## 2. Install Docker Engine and Compose

Use Docker's official Ubuntu repository rather than the distribution's legacy `docker.io` package:

```bash
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo \"$VERSION_CODENAME\") stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker deploy
sudo systemctl enable --now docker
```

Log out and back in, then verify:

```bash
docker version
docker compose version
```

Membership in the `docker` group is root-equivalent. Restrict the deploy account and its SSH keys accordingly.

## 3. Repository and GHCR access

Use a fixed deployment directory:

```bash
sudo install -d -m 0750 -o deploy -g deploy /opt/indonesia-wildfire-intelligence
cd /opt/indonesia-wildfire-intelligence
git clone https://github.com/ridhotr27/indonesia-wildfire-intelligence.git .
```

Public GHCR packages can be pulled anonymously. If packages are private, create a GitHub token with only `read:packages`, keep it out of shell history where possible, and log in:

```bash
read -rsp 'GHCR token: ' GHCR_TOKEN
printf '%s' "$GHCR_TOKEN" | docker login ghcr.io -u ridhotr27 --password-stdin
unset GHCR_TOKEN
```

Select an immutable commit SHA from the successful CI run. Never deploy a mutable `latest` tag.

## 4. Production environment

```bash
cp .env.production.example .env.production
chmod 600 .env.production
```

Replace every `CHANGE_ME` value. Generate independent secrets:

```bash
openssl rand -base64 48
```

Set `IMAGE_TAG` to the exact Git SHA published by CI. Keep the stable volume names unchanged between releases. Validate that no secret is accidentally staged:

```bash
git status --short
git check-ignore -v .env.production
```

Docker Compose environment files are not a full secret manager: values can be visible to privileged Docker operators and in container metadata. Restrict host access, rotate credentials after suspected exposure, and adopt Docker secrets or an external secret manager before expanding operator access.

## 5. DNS and shared reverse proxy

Create an `A` record:

```text
wildfire.ridhotrivonanda.com -> VPS_PUBLIC_IPV4
```

Add `AAAA` only if IPv6 is configured and firewalled correctly. Wait for DNS propagation before requesting certificates.

### Preferred: one shared Caddy for portfolio and wildfire

Create the project-specific external network once:

```bash
docker network create --subnet 172.30.0.0/24 wildfire_edge
```

Start this project without its `caddy` profile. Its frontend and backend join `wildfire_edge` using the aliases `wildfire-frontend` and `wildfire-backend`; ClickHouse stays on the private internal data network. Keep `TRUSTED_PROXY_CIDRS` aligned with this dedicated subnet so Uvicorn trusts forwarded client addresses only from the reverse-proxy network. Do not attach untrusted containers to it.

The existing portfolio Caddy container must also join `wildfire_edge`. Add the following site block to the shared Caddy configuration in the portfolio deployment—without changing this repository's service names or exposing ports:

```caddyfile
wildfire.ridhotrivonanda.com {
    encode zstd gzip
    request_body {
        max_size 1MB
    }
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
        Permissions-Policy "camera=(), microphone=(), geolocation=()"
        -Server
    }
    @api path /api/v1/* /docs* /openapi.json
    handle @api {
        reverse_proxy wildfire-backend:8000
    }
    handle {
        reverse_proxy wildfire-frontend:3000
    }
}
```

The portfolio keeps `ridhotrivonanda.com`; the wildfire project uses only the subdomain. Compose project names, aliases, networks, and volumes are explicitly scoped to prevent collisions.

### Alternative: wildfire owns the public ports

Use the bundled Caddy only when no other process binds ports 80/443:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml --profile edge up -d
```

This mode conflicts with an existing portfolio reverse proxy and therefore is not the recommended shared-VPS mode.

## 6. Validate Compose and pull images

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml config --quiet
docker compose --env-file .env.production -f docker-compose.prod.yml pull backend frontend clickhouse
```

Review the rendered configuration carefully. Do not publish or paste it because resolved secrets may be present.

## 7. Persistent volumes

The deployment uses stable named volumes:

- `wildfire_clickhouse_data`: ClickHouse tables and metadata
- `wildfire_clickhouse_logs`: ClickHouse service logs
- `wildfire_rag_indexes`: NASA and optional semantic indexes
- `wildfire_caddy_data` and `wildfire_caddy_config`: used only in standalone Caddy mode

Inspect them before and after changes:

```bash
docker volume ls --filter name=wildfire_
docker volume inspect wildfire_clickhouse_data wildfire_rag_indexes
```

Never run `docker compose down --volumes`, `docker volume prune`, or delete these volume names during an application update.

## 8. First database initialization

Start only ClickHouse:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml up -d clickhouse
docker compose --env-file .env.production -f docker-compose.prod.yml ps
docker compose --env-file .env.production -f docker-compose.prod.yml logs --tail=200 clickhouse
```

The first initialization applies the versioned migrations and creates two separate identities:

- `wildfire_backend`: `SELECT` only on the four approved analytics views
- `wildfire_ingestor`: bounded `SELECT`/`INSERT` access for DE-owned tables and release controls

Initialization scripts run only on an empty ClickHouse data volume. Changing a password in `.env.production` does not rotate an existing database user; perform an explicit reviewed `ALTER USER` operation and restart dependent services.

## 9. Load a verified dataset

Do not copy arbitrary CSV files into ClickHouse. Generate or transfer one checksum-verified batch produced by the existing ingestion pipeline. Place it outside the Git checkout, owned by the deploy operator, and set its absolute path as `DATA_BATCH_DIR`.

For a v1.0 batch:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml \
  --profile initialize run --rm data-loader
```

The loader verifies the manifest, file sizes, SHA-256 hashes, row counts, contract and product identity, uses a single-writer lock, and publishes the batch row last. Follow `data/OPERATIONS_RUNBOOK.md` for D08 v1.1 multi-year hidden loading, authorization, activation, audit, and append-only rollback; the simple `data-loader` command does not replace that release procedure.

Run the documented reconciliation queries after loading and verify that the backend identity cannot access raw tables or write data.

## 10. Build the persistent RAG index

The default production baseline uses deterministic hashing embeddings and extractive grounded answers. Build the index once before starting the API:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml \
  --profile initialize run --rm rag-init
```

This job fetches only the allowlisted NASA URLs, creates a versioned compatibility manifest, and publishes the index atomically into `wildfire_rag_indexes`. The API never rebuilds indexes at startup. Back up this volume or rebuild it from the approved sources after verifying source availability and hashes.

## 11. First application deployment

For the shared-proxy topology:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml \
  up -d clickhouse backend frontend
docker compose --env-file .env.production -f docker-compose.prod.yml ps
```

Reload the shared portfolio Caddy only after validating its combined configuration. Then check:

```bash
curl -fsS https://wildfire.ridhotrivonanda.com/api/v1/health
curl -fsS https://wildfire.ridhotrivonanda.com/api/v1/metadata
curl -fsSI https://wildfire.ridhotrivonanda.com/
```

The health endpoint proves process availability, not ClickHouse/RAG correctness. Run the documented metadata, analytics, retrieval, and permission smoke checks before accepting traffic.

## 12. Updates and rollback

Before every update:

1. Confirm a recent off-host backup and restoration test.
2. Record the running `IMAGE_TAG` and Git SHA.
3. Review schema migrations separately; application rollback cannot undo a destructive database migration.
4. Pull the new immutable images.

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml pull backend frontend
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --no-deps backend frontend
docker compose --env-file .env.production -f docker-compose.prod.yml ps
```

To roll back application containers, restore the prior `IMAGE_TAG` and recreate only frontend/backend. Do not recreate or remove ClickHouse volumes:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --no-deps backend frontend
```

Use the data pipeline's append-only release rollback for D08 dataset activation. Never delete rows manually without following the documented interrupted-load recovery procedure.

## 13. Backup and restoration

At minimum, back up:

- ClickHouse data and metadata
- RAG indexes and manifests
- `.env.production` in an encrypted secret backup
- The deployed Git SHA, image digests, and dataset release/ingestion manifests

For a consistent filesystem-level backup on a single-node demonstration deployment, stop application writes, stop ClickHouse cleanly, snapshot/archive the volume to an encrypted off-host target, then restart it. A sample maintenance sequence is:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml stop backend
docker compose --env-file .env.production -f docker-compose.prod.yml stop clickhouse
docker run --rm -v wildfire_clickhouse_data:/source:ro -v /srv/backups/wildfire:/backup \
  alpine:3.21 tar -C /source -czf /backup/clickhouse-$(date -u +%Y%m%dT%H%M%SZ).tgz .
docker compose --env-file .env.production -f docker-compose.prod.yml up -d clickhouse backend
```

Protect `/srv/backups`, copy archives off-host, record checksums, define retention, and test restoration on a separate volume. For larger or continuously available deployments, use ClickHouse-native backup/storage procedures rather than relying on a stopped filesystem archive.

Restore only into a new empty test volume first. Verify ownership, server version, table integrity, active release, published counts, read-only grants, and API responses before switching volume names. Never overwrite the only production copy during a restoration test.

## 14. Monitoring and health

Monitor:

- Host CPU, memory, swap activity, load, disk space, inode usage, and filesystem latency
- Container restarts, health state, memory limit events, and log growth
- ClickHouse query latency, errors, parts, merges, disk growth, and failed inserts
- FastAPI 4xx/5xx rates, dependency status, timeouts, rate limits, and request duration
- RAG/index startup compatibility failures and retrieval abstentions
- Caddy certificate renewal and upstream errors

Useful commands:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml ps
docker stats --no-stream
df -h
docker system df
docker compose --env-file .env.production -f docker-compose.prod.yml logs --since=30m --tail=500
```

The JSON logging driver rotates each container's logs. ClickHouse's own persistent log volume still needs monitoring and retention configuration before long-running production use.

## 15. Future automated deployment

The initial GitHub Actions workflow tests and publishes immutable GHCR images but contains no deploy job. Add deployment only after manual deployment, backups, restore, rollback, shared Caddy integration, and release gates are accepted.

A future job should use a protected GitHub Environment, require manual approval, verify host keys, transfer only the target SHA, authenticate to GHCR with read-only credentials, run `docker compose config`, pull immutable images, recreate application containers without volumes, execute smoke checks, and roll back automatically on failure. Do not store a root SSH key or database password in an unprotected repository secret.

## Troubleshooting

### Backend will not start

- Verify `WILDFIRE_CLIENT_ID_SALT` and ClickHouse credentials are populated.
- Confirm ClickHouse is healthy and the reader can query only `analytics_*` views.
- Confirm `wildfire_rag_indexes` contains the expected local-hashing manifest and collection.
- Check that chunking, retrieval, collection, and embedding settings match the index manifest.

### Frontend reports unavailable data

- Confirm `WILDFIRE_PUBLIC_API_BASE_URL` is the public HTTPS `/api/v1` URL.
- Check `/api/runtime-config`, API metadata, Caddy routing, and DNS.
- The frontend intentionally rejects mock or unverified data in real mode.

### Caddy certificate fails

- Verify DNS resolves to the VPS and ports 80/443 reach the shared proxy.
- Confirm only one reverse proxy binds the ports.
- Check Caddy logs and ACME rate-limit messages before retrying repeatedly.

### ClickHouse appears empty after an update

- Stop immediately and inspect the rendered volume name.
- Compare `CLICKHOUSE_DATA_VOLUME` with the previous deployment.
- Reattach the original named volume; do not initialize a replacement and assume data was migrated.

### RAG answers abstain

- Verify the offline index job completed and the API opened the same named volume.
- Inspect manifest compatibility and source hashes.
- Abstention on insufficient evidence is expected and must not be bypassed.

### Shared VPS name or port conflict

- Do not start the wildfire `edge` profile.
- Ensure only the portfolio/shared Caddy publishes 80/443.
- Confirm both proxies are not competing and each project uses distinct networks, aliases, project names, and volumes.
