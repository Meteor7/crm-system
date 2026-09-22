#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
source backend/ci/environment.sh
if [[ ${1:-} == --stale ]]; then
  # Only this single dedicated runner uses this daemon. Recover jobs killed before EXIT.
  mapfile -t containers < <(docker ps -aq --filter label=com.docker.compose.project)
  for container in "${containers[@]}"; do
    project=$(docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' "$container")
    if [[ $project =~ ^crm-ci-[0-9]+-[0-9]+$ ]]; then docker rm -f "$container"; fi
  done
  mapfile -t volumes < <(docker volume ls -q --filter label=com.docker.compose.project)
  for volume in "${volumes[@]}"; do
    project=$(docker volume inspect --format '{{index .Labels "com.docker.compose.project"}}' "$volume")
    if [[ $project =~ ^crm-ci-[0-9]+-[0-9]+$ ]]; then docker volume rm "$volume"; fi
  done
  mapfile -t networks < <(docker network ls -q --filter label=com.docker.compose.project)
  for network in "${networks[@]}"; do
    project=$(docker network inspect --format '{{index .Labels "com.docker.compose.project"}}' "$network")
    if [[ $project =~ ^crm-ci-[0-9]+-[0-9]+$ ]]; then docker network rm "$network"; fi
  done
  docker image prune -af --filter until=168h
  docker builder prune -f --filter until=48h --keep-storage 15GB
else
  "${compose[@]}" down --volumes --remove-orphans --timeout 10
  for image in "$CRM_IMAGE" "crm-ci-production:${CRM_CI_PROJECT#crm-ci-}"; do
    if docker image inspect "$image" >/dev/null 2>&1; then docker image rm "$image"; fi
  done
fi
