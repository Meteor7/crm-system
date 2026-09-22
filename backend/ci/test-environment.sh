#!/usr/bin/env bash
# Exercise destructive-command guards with a fake Docker CLI; never contact a daemon.
set -euo pipefail
cd "$(dirname "$0")/../.."
ci_test_dir=$(mktemp -d)
trap 'rm -f "$ci_test_dir/docker-calls" "$ci_test_dir/expected-failure.log" "$ci_test_dir/expected-success.log"; rmdir "$ci_test_dir"' EXIT
export CRM_CI_TEST_CALLS=$ci_test_dir/docker-calls
id() { if [[ $1 == -un ]]; then echo "${CRM_CI_TEST_USER:-crm-ci}"; else echo 1002; fi; }
docker() {
  printf '%s\n' "$*" >> "$CRM_CI_TEST_CALLS"
  case "$*" in
    'info --format {{json .SecurityOptions}}') echo '["name=rootless"]' ;;
    'info --format {{.DockerRootDir}}') echo /home/crm-ci/.local/share/docker ;;
    'ps -aq --filter label=com.docker.compose.project') printf '%s\n' ci-container staging-container ;;
    'volume ls -q --filter label=com.docker.compose.project') printf '%s\n' ci-volume staging-volume ;;
    'network ls -q --filter label=com.docker.compose.project') printf '%s\n' ci-network staging-network ;;
    inspect*ci-container|*inspect*ci-volume|*inspect*ci-network) echo crm-ci-12-1 ;;
    inspect*staging-container|*inspect*staging-volume|*inspect*staging-network) echo rayher-crm-stage1-staging ;;
    'rm -f ci-container'|'volume rm ci-volume'|'network rm ci-network'|'image prune -af --filter until=168h'|'builder prune -f --filter until=48h --keep-storage 15GB') ;;
    *) echo "Unexpected Docker call: $*" >&2; return 90 ;;
  esac
}
export -f id docker
export CRM_CI_PROJECT=crm-ci-12-1 DOCKER_HOST=unix:///run/user/1002/docker.sock
export COMPOSE_PROJECT_NAME=production CRM_IMAGE=production SITE_NAME=production HTTP_BIND_ADDRESS=0.0.0.0 HTTP_PORT=4174 ALLOW_TESTS=false
bash -c 'source backend/ci/environment.sh; [[ $COMPOSE_PROJECT_NAME == crm-ci-12-1 && $CRM_IMAGE == crm-ci-test:12-1 && $SITE_NAME == rayher-crm.test && $HTTP_BIND_ADDRESS == 127.0.0.1 && $HTTP_PORT == 0 && $ALLOW_TESTS == true ]]'
for case_name in project user socket; do
  : > "$CRM_CI_TEST_CALLS"
  case "$case_name" in
    project) if CRM_CI_PROJECT=production bash -c 'source backend/ci/environment.sh' 2>/dev/null; then exit 1; fi ;;
    user) if CRM_CI_TEST_USER=plancksemicon bash -c 'source backend/ci/environment.sh' 2>/dev/null; then exit 1; fi ;;
    socket) if DOCKER_HOST=unix:///var/run/docker.sock bash -c 'source backend/ci/environment.sh' 2>/dev/null; then exit 1; fi ;;
  esac
  [[ ! -s $CRM_CI_TEST_CALLS ]] || { echo "Unsafe $case_name reached Docker" >&2; exit 1; }
done
: > "$CRM_CI_TEST_CALLS"
bash backend/ci/cleanup.sh --stale
grep -Fx 'rm -f ci-container' "$CRM_CI_TEST_CALLS"
grep -Fx 'volume rm ci-volume' "$CRM_CI_TEST_CALLS"
grep -Fx 'network rm ci-network' "$CRM_CI_TEST_CALLS"
! grep -E '(^rm|^volume rm|^network rm).*staging' "$CRM_CI_TEST_CALLS"
echo 'CI environment contract passed: override isolation, 3 refusal paths, scoped stale cleanup.'
reports=$ci_test_dir
source backend/ci/phase.sh
if phase expected-failure bash -c 'echo expected-failure; exit 7'; then
  echo 'Phase wrapper masked an exit code.' >&2; exit 1
else
  [[ $? == 7 ]]
fi
phase expected-success echo expected-success
grep -Fx expected-failure "$reports/expected-failure.log"
echo 'CI phase contract passed: preserve failure status in conditional execution.'
