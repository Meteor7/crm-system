#!/usr/bin/env bash
# Sourced by both execution and cleanup; refuse host Docker before any mutation.
set -euo pipefail
[[ ${CRM_CI_PROJECT:-} =~ ^crm-ci-[0-9]+-[0-9]+$ ]] || { echo 'Invalid CI project.' >&2; exit 1; }
[[ $(id -un) == crm-ci ]] || { echo 'Use the dedicated crm-ci account.' >&2; exit 1; }
[[ ${DOCKER_HOST:-} == "unix:///run/user/$(id -u)/docker.sock" ]] || { echo 'Refusing a non-CI Docker socket.' >&2; exit 1; }
unset DOCKER_CONTEXT
docker info --format '{{json .SecurityOptions}}' | grep -q rootless
[[ $(docker info --format '{{.DockerRootDir}}') == /home/crm-ci/.local/share/docker ]]
unset ALLOW_TESTS CLAMAV_IMAGE COMPOSE_PROJECT_NAME CRM_APP_ARCHIVE CRM_APP_ARCHIVE_SHA256 CRM_IMAGE CRM_TEST_SITE FRAPPE_BASE_IMAGE HTTP_BIND_ADDRESS HTTP_PORT MARIADB_IMAGE REDIS_IMAGE SITE_NAME DOCKER_CONTEXT
export COMPOSE_PROJECT_NAME=$CRM_CI_PROJECT
export CRM_IMAGE="crm-ci-test:${CRM_CI_PROJECT#crm-ci-}"
export SITE_NAME=rayher-crm.test ALLOW_TESTS=true CRM_TEST_SITE=true HTTP_BIND_ADDRESS=127.0.0.1 HTTP_PORT=0
compose=(docker compose --project-name "$CRM_CI_PROJECT" --env-file backend/test.env.example -f backend/compose.yaml)
