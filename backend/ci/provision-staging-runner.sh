#!/usr/bin/env bash
# Run as root on the dedicated staging host; registration token is read from stdin.
set -euo pipefail
[[ $EUID == 0 && $(uname -m) == x86_64 ]] || { echo 'Requires root on Linux x86_64.' >&2; exit 1; }
source /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 26.04 ]] || { echo 'Validated for Ubuntu 26.04 only.' >&2; exit 1; }
[[ $(stat -fc %T /sys/fs/cgroup) == cgroup2fs ]] || { echo 'Requires cgroup v2.' >&2; exit 1; }

ci_user=crm-ci
ci_home=/home/crm-ci
if id "$ci_user" >/dev/null 2>&1 && pgrep -u "$ci_user" -f '/Runner.Worker' >/dev/null; then
  echo 'Runner is busy; wait for the current job before provisioning.' >&2
  exit 1
fi
runner_version=2.337.0
runner_sha=70920811a4f8ad4328818682bca5c6469c1c942fab52448868071d0063816613
pwsh_version=7.6.6
pwsh_sha=ddbc4a2d113bbd46d283cfedcbcd117a70caefd7673f41f2b4e0000badf103bc
repo_url=https://github.com/kizzhang/PlanckSemicon_CRM

# Do not install/upgrade/restart the host Docker daemon or existing services.
command -v docker >/dev/null
docker compose version
docker buildx version
[[ -x /usr/share/docker.io/contrib/dockerd-rootless.sh ]]
export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=l
apt-get update -qq
apt-get install -y --no-upgrade --no-install-recommends uidmap rootlesskit slirp4netns fuse-overlayfs dbus-user-session curl ca-certificates git jq libicu78 libssl3t64 libkrb5-3 zlib1g

if ! id "$ci_user" >/dev/null 2>&1; then
  useradd --create-home --home-dir "$ci_home" --shell /bin/bash "$ci_user"
fi
[[ $(getent passwd "$ci_user" | cut -d: -f6) == "$ci_home" ]]
[[ $(id -Gn "$ci_user") == "$ci_user" ]] || { echo 'CI account must not have supplementary groups.' >&2; exit 1; }
passwd -l "$ci_user" >/dev/null
chmod 700 "$ci_home"
grep -Eq '^crm-ci:[0-9]+:[0-9]+$' /etc/subuid
grep -Eq '^crm-ci:[0-9]+:[0-9]+$' /etc/subgid
ci_uid=$(id -u "$ci_user")
ci_runtime=/run/user/$ci_uid

# The parent slice bounds runner, rootless daemon AND all its containers together.
install -d -m 755 "/etc/systemd/system/user-$ci_uid.slice.d" "/etc/systemd/system/user@$ci_uid.service.d"
cat > "/etc/systemd/system/user-$ci_uid.slice.d/crm-ci.conf" <<'EOF'
[Slice]
CPUQuota=400%
MemoryHigh=5G
MemoryMax=6G
MemorySwapMax=1G
TasksMax=8192
CPUWeight=25
IOWeight=25
EOF
cat > "/etc/systemd/system/user@$ci_uid.service.d/crm-ci.conf" <<'EOF'
[Service]
Delegate=cpu cpuset io memory pids
EOF
systemctl daemon-reload
loginctl enable-linger "$ci_user"
systemctl start "user@$ci_uid.service"
systemctl set-property "user-$ci_uid.slice" CPUQuota=400% MemoryHigh=5G MemoryMax=6G MemorySwapMax=1G TasksMax=8192 CPUWeight=25 IOWeight=25
# Ubuntu ships setup scripts in contrib, but setup expects docker alongside them.
install -d -m 755 /home/crm-ci-tools/docker
install -m 755 /usr/share/docker.io/contrib/dockerd-rootless.sh /usr/share/docker.io/contrib/dockerd-rootless-setuptool.sh /home/crm-ci-tools/docker/
ln -sf /usr/bin/docker /home/crm-ci-tools/docker/docker
as_ci() { runuser -u "$ci_user" -- env XDG_RUNTIME_DIR="$ci_runtime" DBUS_SESSION_BUS_ADDRESS="unix:path=$ci_runtime/bus" PATH=/home/crm-ci-tools/powershell:/home/crm-ci-tools/docker:/usr/local/bin:/usr/bin:/bin "$@"; }

install -d -o "$ci_user" -g "$ci_user" -m 700 "$ci_home/.config/docker" "$ci_home/.config/systemd/user" "$ci_home/actions-runner" "$ci_home/tmp"
cat > "$ci_home/.config/docker/daemon.json" <<EOF
{"data-root":"$ci_home/.local/share/docker","log-driver":"local","log-opts":{"max-size":"10m","max-file":"3"},"builder":{"gc":{"enabled":true,"defaultKeepStorage":"15GB"}}}
EOF
chown "$ci_user:$ci_user" "$ci_home/.config/docker/daemon.json"
if ! as_ci systemctl --user is-active --quiet docker; then
  as_ci /home/crm-ci-tools/docker/dockerd-rootless-setuptool.sh install --force
fi
as_ci systemctl --user enable docker
as_ci docker --host "unix://$ci_runtime/docker.sock" info --format '{{json .SecurityOptions}}' | grep -q rootless
[[ $(as_ci docker --host "unix://$ci_runtime/docker.sock" info --format '{{.CgroupDriver}}') == systemd ]]

# Both archives come from upstream release assets and are verified before extraction.
install -d -m 755 /home/crm-ci-tools /home/crm-ci-tools/powershell
fetch_verified() {
  local url=$1 sha=$2 target=$3
  curl --fail --location --retry 3 --connect-timeout 20 "$url" -o "$target"
  printf '%s  %s\n' "$sha" "$target" | sha256sum --check --status
}
if [[ ! -x /home/crm-ci-tools/powershell/pwsh ]]; then
  fetch_verified "https://github.com/PowerShell/PowerShell/releases/download/v$pwsh_version/powershell-$pwsh_version-linux-x64.tar.gz" "$pwsh_sha" /home/crm-ci-tools/powershell.tar.gz
  tar xzf /home/crm-ci-tools/powershell.tar.gz -C /home/crm-ci-tools/powershell
  chmod 755 /home/crm-ci-tools/powershell/pwsh
  rm /home/crm-ci-tools/powershell.tar.gz
fi
if [[ ! -x "$ci_home/actions-runner/config.sh" ]]; then
  fetch_verified "https://github.com/actions/runner/releases/download/v$runner_version/actions-runner-linux-x64-$runner_version.tar.gz" "$runner_sha" /home/crm-ci-tools/runner.tar.gz
  as_ci tar xzf /home/crm-ci-tools/runner.tar.gz -C "$ci_home/actions-runner"
  rm /home/crm-ci-tools/runner.tar.gz
fi

if [[ ! -f "$ci_home/actions-runner/.runner" ]]; then
  read -r registration_token
  [[ -n $registration_token ]] || { echo 'A short-lived repository registration token is required on stdin.' >&2; exit 1; }
  # Do not put tokens in files, scripts, shell history or process arguments.
  cd "$ci_home/actions-runner"
  export ACTIONS_RUNNER_INPUT_TOKEN=$registration_token
  as_ci ./config.sh --unattended --url "$repo_url" --name crm-staging-01 --labels crm-staging,crm-rootless --work _work
  unset ACTIONS_RUNNER_INPUT_TOKEN registration_token
fi
# svc.sh normally copies this launcher while installing a system-wide service.
# Use the same launcher in the user manager so the parent CI resource cap applies.
install -o "$ci_user" -g "$ci_user" -m 755 "$ci_home/actions-runner/bin/runsvc.sh" "$ci_home/actions-runner/runsvc.sh"
# runsvc.sh restores .path captured during registration, overriding systemd's PATH.
printf '%s\n' /home/crm-ci-tools/powershell:/home/crm-ci-tools/docker:/usr/local/bin:/usr/bin:/bin > "$ci_home/actions-runner/.path"
chown "$ci_user:$ci_user" "$ci_home/actions-runner/.path"
cat > "$ci_home/.config/systemd/user/crm-actions-runner.service" <<EOF
[Unit]
Description=CRM GitHub Actions runner (staging, rootless Docker)
After=network-online.target docker.service
Requires=docker.service
[Service]
WorkingDirectory=$ci_home/actions-runner
ExecStart=$ci_home/actions-runner/runsvc.sh
Environment=PATH=/home/crm-ci-tools/powershell:/usr/share/docker.io/contrib:/usr/local/bin:/usr/bin:/bin
Environment=DOCKER_HOST=unix://$ci_runtime/docker.sock
Environment=TMPDIR=$ci_home/tmp
Environment=DOTNET_CLI_TELEMETRY_OPTOUT=1
Environment=POWERSHELL_TELEMETRY_OPTOUT=1
UMask=0077
Restart=always
RestartSec=10
KillMode=control-group
TimeoutStopSec=120
[Install]
WantedBy=default.target
EOF
chown "$ci_user:$ci_user" "$ci_home/.config/systemd/user/crm-actions-runner.service"
as_ci systemctl --user daemon-reload
as_ci systemctl --user enable --now crm-actions-runner
as_ci systemctl --user is-active docker crm-actions-runner
as_ci /home/crm-ci-tools/powershell/pwsh -NoProfile -Command '$PSVersionTable.PSVersion.ToString()'
echo 'Runner installed. Verify status and labels using the GitHub repository runners API.'
