#!/usr/bin/env bash
set -euo pipefail

# Run only for an approved private Wildfire update after CI and host backup checks.
sha="${1:?usage: deploy-release.sh <40-character commit SHA>}"
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || { echo 'Invalid commit SHA' >&2; exit 2; }
cd /opt/indonesia-wildfire-intelligence
[[ "$(git rev-parse HEAD)" == "$sha" ]] || { echo 'Host checkout does not match the approved image SHA' >&2; exit 2; }
[[ -f .env.production ]] || { echo 'Missing host-managed environment' >&2; exit 2; }
[[ -f .last-good-image-sha ]] && previous="$(cat .last-good-image-sha)" || previous=''
compose=(docker compose --env-file .env.production -f docker-compose.prod.yml -f docker-compose.low-memory.yml)

export IMAGE_TAG="$sha"
"${compose[@]}" config --quiet
"${compose[@]}" pull backend frontend
"${compose[@]}" up -d --no-deps backend frontend

healthy=0
for attempt in {1..24}; do
  mapfile -t containers < <("${compose[@]}" ps -q backend frontend)
  if [[ "${#containers[@]}" == 2 ]] && [[ "$(docker inspect --format '{{.State.Health.Status}}' "${containers[0]}")" == healthy ]] && [[ "$(docker inspect --format '{{.State.Health.Status}}' "${containers[1]}")" == healthy ]]; then
    healthy=1
    break
  fi
  sleep 5
done

if [[ "$healthy" != 1 ]]; then
  if [[ "$previous" =~ ^[0-9a-f]{40}$ ]]; then
    export IMAGE_TAG="$previous"
    "${compose[@]}" up -d --no-deps backend frontend
  else
    "${compose[@]}" stop backend frontend
  fi
  echo 'Deployment health check failed; previous images restored when available' >&2
  exit 1
fi

printf '%s\n' "$sha" > .last-good-image-sha
echo "Private Wildfire application containers healthy at $sha"
