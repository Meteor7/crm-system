#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
source backend/ci/environment.sh
reports=backend/build/ci-reports
mkdir -p "$reports"
finish() {
  result=$?
  trap - EXIT INT TERM
  set +e
  "${compose[@]}" ps -a > "$reports/compose-status.txt" 2>&1
  "${compose[@]}" logs --no-color --tail 250 > "$reports/compose.log" 2>&1
  docker info --format '{{.ServerVersion}} {{.CgroupDriver}} {{json .SecurityOptions}}' > "$reports/runner.txt" 2>&1
  bash backend/ci/cleanup.sh > "$reports/cleanup.log" 2>&1
  cleanup_result=$?
  if [[ $cleanup_result != 0 && $result == 0 ]]; then result=$cleanup_result; fi
  printf 'Backend CI result: %s; cleanup result: %s\n' "$result" "$cleanup_result" >> "$reports/result.txt"
  exit "$result"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
source backend/ci/phase.sh
phase stale-cleanup bash backend/ci/cleanup.sh --stale
available_kb=$(df --output=avail /home/crm-ci | tail -1 | tr -d ' ')
[[ $available_kb -gt 41943040 ]] || { echo 'CI requires at least 40 GiB free in /home.' >&2; exit 1; }
[[ $(jq -r .commit backend/build/manifest.json) == "$(git rev-parse HEAD)" ]] || { echo 'Artifact commit does not match checkout.' >&2; exit 1; }
for archive in rayher_crm.zip rayher_crm-tests.zip; do
  hash=$(jq -er --arg name "$archive" '.archives[] | select(.name == $name) | .sha256' backend/build/manifest.json)
  [[ $hash =~ ^[a-f0-9]{64}$ ]]
  printf '%s  backend/build/%s\n' "$hash" "$archive" | sha256sum --check
done
test_hash=$(sha256sum backend/build/rayher_crm-tests.zip | cut -d' ' -f1)
production_hash=$(sha256sum backend/build/rayher_crm.zip | cut -d' ' -f1)
phase test-image "${compose[@]}" build --build-arg CRM_APP_ARCHIVE=build/rayher_crm-tests.zip --build-arg "CRM_APP_ARCHIVE_SHA256=$test_hash" backend
phase test-report-tools docker build -f backend/ci/Dockerfile.test --build-arg "CRM_TEST_BASE_IMAGE=$CRM_IMAGE" -t "$CRM_IMAGE" backend/ci
# --wait waits for health checks, plus completed init/migration jobs, before testing.
phase startup "${compose[@]}" up -d --no-build --wait --wait-timeout 900 backend frontend websocket scheduler queue-short queue-long
endpoint=$("${compose[@]}" port frontend 8080)
[[ $endpoint =~ ^127\.0\.0\.1:[0-9]+$ ]] || { echo 'CI HTTP listener must be loopback only.' >&2; exit 1; }
# Docker reallocates ephemeral host ports on restart. Pin the allocated port before
# acceptance suites restart the frontend, and pass it through their Compose calls.
export HTTP_PORT=${endpoint##*:}
phase pin-http-port "${compose[@]}" up -d --no-build --no-deps --force-recreate --wait --wait-timeout 300 frontend
[[ $("${compose[@]}" port frontend 8080) == "$endpoint" ]] || { echo 'CI HTTP port changed while pinning it.' >&2; exit 1; }
printf '%s\n' "$endpoint" > "$reports/http-endpoint.txt"
base_url="http://$endpoint"
phase forwarded-https bash backend/ci/forwarded-https.sh "$base_url"
phase frappe-tests pwsh -NoProfile -File backend/tests/run-backend-tests.ps1 -ProjectName "$CRM_CI_PROJECT" -ReportDirectory "$reports"
acceptance=(
  http-stage5b-acceptance.ps1
  http-stage5c-opportunity-acceptance.ps1
  http-stage5d-booking-installed-tool-acceptance.ps1
  http-stage5e-demo-evaluation-acceptance.ps1
  http-stage5f-files-reports-notifications-acceptance.ps1
  http-stage5g-read-models-visits-acceptance.ps1
)
http_failures=0
for script in "${acceptance[@]}"; do
  if phase "${script%.ps1}" pwsh -NoProfile -File "backend/tests/$script" -ProjectName "$CRM_CI_PROJECT" -BaseUrl "$base_url"; then
    printf '%s: passed\n' "$script" >> "$reports/http-summary.txt"
  else
    http_failures=$((http_failures + 1))
    printf '%s: FAILED\n' "$script" >> "$reports/http-summary.txt"
  fi
done
# Build the production archive too, under a separate tag. It cannot run test code.
export CRM_IMAGE="crm-ci-production:${CRM_CI_PROJECT#crm-ci-}"
phase production-image "${compose[@]}" build --build-arg CRM_APP_ARCHIVE=build/rayher_crm.zip --build-arg "CRM_APP_ARCHIVE_SHA256=$production_hash" backend
docker image inspect --format '{{.Id}}' "$CRM_IMAGE" > "$reports/production-image-id.txt"
cat "$reports/http-summary.txt"
[[ $http_failures == 0 ]]
