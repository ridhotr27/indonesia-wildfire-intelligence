#!/usr/bin/env bash
set -euo pipefail

# CD updates only the Wildfire application images; GHCR token arrives on stdin.
[[ $# == 8 ]] || { echo 'Expected SHA, two digests, owner, GHCR user and three Compose checksums' >&2; exit 2; }
sha=$1 backend_digest=$2 frontend_digest=$3 owner=$4 ghcr_user=$5
prod_sum=$6 low_sum=$7 images_sum=$8
[[ $sha =~ ^[0-9a-f]{40}$ && $backend_digest =~ ^sha256:[0-9a-f]{64}$ && $frontend_digest =~ ^sha256:[0-9a-f]{64}$ ]] || exit 2
[[ $owner =~ ^[a-z0-9-]+$ && $ghcr_user =~ ^[A-Za-z0-9-]+$ ]] || exit 2
for sum in "$prod_sum" "$low_sum" "$images_sum"; do [[ $sum =~ ^[0-9a-f]{64}$ ]] || exit 2; done

cd /opt/indonesia-wildfire-intelligence
[[ -f .env.production && $(stat -c %a .env.production) == 600 ]] || { echo 'Protected environment missing or not mode 600' >&2; exit 2; }
[[ $(sha256sum docker-compose.prod.yml | cut -d' ' -f1) == "$prod_sum" ]] || { echo 'Production Compose drift' >&2; exit 2; }
[[ $(sha256sum docker-compose.low-memory.yml | cut -d' ' -f1) == "$low_sum" ]] || { echo 'Low-memory Compose drift' >&2; exit 2; }
[[ $(sha256sum infrastructure/compose-images.yml | cut -d' ' -f1) == "$images_sum" ]] || { echo 'Image overlay drift' >&2; exit 2; }

BACKEND_IMAGE_REF="ghcr.io/$owner/indonesia-wildfire-intelligence-backend@$backend_digest"
FRONTEND_IMAGE_REF="ghcr.io/$owner/indonesia-wildfire-intelligence-frontend@$frontend_digest"
compose() {
  sudo -n env BACKEND_IMAGE_REF="$BACKEND_IMAGE_REF" FRONTEND_IMAGE_REF="$FRONTEND_IMAGE_REF" docker compose \
    --env-file .env.production -f docker-compose.prod.yml -f docker-compose.low-memory.yml \
    -f infrastructure/compose-images.yml "$@"
}
healthy() {
  local id
  id=$(compose ps -q "$1")
  [[ -n $id && $(sudo -n docker inspect --format '{{.State.Health.Status}}' "$id") == healthy ]]
}
public_ok() {
  curl -fsS --max-time 12 --resolve "wildfire.ridhotrivo.com:443:127.0.0.1" \
    "https://wildfire.ridhotrivo.com$1" >/dev/null
}
portfolio_ok() { curl -fsS --max-time 12 https://ridhotrivo.com/ >/dev/null; }
dataset_count() {
  sudo -n docker exec "$(compose ps -q clickhouse)" sh -c \
    'clickhouse-client --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" --query "SELECT count() FROM wildfire.analytics_hotspot_observations_v1"' 2>/dev/null
}
wait_healthy() {
  local attempt
  for attempt in {1..24}; do
    if healthy backend && healthy frontend; then return 0; fi
    sleep 5
  done
  return 1
}
resource_ok() {
  [[ $(awk '/MemAvailable:/ {print $2}' /proc/meminfo) -ge 786432 ]] || return 1
  [[ $(df -Pk . | awk 'NR==2 {print $4}') -ge 2097152 ]] || return 1
  local service id
  for service in backend frontend; do
    id=$(compose ps -q "$service")
    [[ $(sudo -n docker inspect --format '{{.State.OOMKilled}}' "$id") == false ]] || return 1
  done
}

compose config --quiet
healthy clickhouse && healthy backend && healthy frontend || { echo 'Wildfire baseline unhealthy' >&2; exit 1; }
portfolio_ok && public_ok /api/v1/health || { echo 'Public baseline unhealthy' >&2; exit 1; }
[[ $(dataset_count) == 253388 ]] || { echo 'Dataset count mismatch' >&2; exit 1; }
[[ $(awk '/MemAvailable:/ {print $2}' /proc/meminfo) -ge 1048576 ]] || { echo 'Insufficient available RAM' >&2; exit 1; }
[[ $(df -Pk . | awk 'NR==2 {print $4}') -ge 2097152 ]] || { echo 'Insufficient disk space' >&2; exit 1; }

old_backend=$(sudo -n docker inspect --format '{{.Config.Image}}' "$(compose ps -q backend)")
old_frontend=$(sudo -n docker inspect --format '{{.Config.Image}}' "$(compose ps -q frontend)")
clickhouse_id=$(compose ps -q clickhouse)
ollama_id=$(sudo -n docker ps -q --filter 'name=^/indonesia-wildfire-intelligence-ollama-1$')
caddy_id=$(sudo -n docker ps -q --filter 'name=^/shared-edge-caddy-1$')
[[ -n $clickhouse_id && -n $ollama_id && -n $caddy_id ]] || { echo 'Infrastructure baseline incomplete' >&2; exit 1; }

rollback_needed=0
tmp_config=$(mktemp -d)
cleanup() {
  local status=$?
  trap - EXIT
  if (( status != 0 && rollback_needed == 1 )); then
    BACKEND_IMAGE_REF=$old_backend FRONTEND_IMAGE_REF=$old_frontend
    compose up -d --no-build --no-deps --pull never --force-recreate backend frontend || true
    wait_healthy || true
    echo 'Application rollback attempted; inspect health before further action' >&2
  fi
  rm -rf "$tmp_config"
  exit "$status"
}
trap cleanup EXIT

IFS= read -r token || [[ -n ${token:-} ]]
[[ -n ${token:-} ]] || { echo 'Missing GHCR token' >&2; exit 2; }
printf '%s' "$token" | sudo -n docker --config "$tmp_config" login ghcr.io -u "$ghcr_user" --password-stdin >/dev/null
unset token
sudo -n docker --config "$tmp_config" pull "$BACKEND_IMAGE_REF"
sudo -n docker --config "$tmp_config" pull "$FRONTEND_IMAGE_REF"
for ref in "$BACKEND_IMAGE_REF" "$FRONTEND_IMAGE_REF"; do
  [[ $(sudo -n docker image inspect --format '{{.Os}}/{{.Architecture}}' "$ref") == linux/amd64 ]] || { echo 'Wrong image platform' >&2; exit 1; }
done

rollback_needed=1
compose up -d --no-build --no-deps --pull never --force-recreate backend frontend
wait_healthy || { echo 'Application health failed' >&2; exit 1; }
[[ $(compose ps -q clickhouse) == "$clickhouse_id" ]] || { echo 'ClickHouse changed' >&2; exit 1; }
[[ $(sudo -n docker ps -q --filter 'name=^/indonesia-wildfire-intelligence-ollama-1$') == "$ollama_id" ]] || { echo 'Ollama changed' >&2; exit 1; }
[[ $(sudo -n docker ps -q --filter 'name=^/shared-edge-caddy-1$') == "$caddy_id" ]] || { echo 'Caddy changed' >&2; exit 1; }
[[ $(dataset_count) == 253388 ]] || { echo 'Dataset changed' >&2; exit 1; }
public_ok / && public_ok /api/v1/health && public_ok /api/v1/metadata && portfolio_ok || { echo 'Public smoke failed' >&2; exit 1; }
resource_ok || { echo 'Resource/OOM safety check failed' >&2; exit 1; }
printf '%s\n%s\n' "$BACKEND_IMAGE_REF" "$FRONTEND_IMAGE_REF" > .last-good-image-refs.tmp
mv .last-good-image-refs.tmp .last-good-image-refs
rollback_needed=0
echo "Deployed application images for $sha; infrastructure and dataset preserved"
