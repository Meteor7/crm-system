# Staging GitHub Actions runner

Repository: `kizzhang/PlanckSemicon_CRM` (private). Runner: `crm-staging-01`.
Host: staging `203.0.113.58`, Ubuntu 26.04 x86_64. Labels: `self-hosted`, `Linux`, `X64`, `crm-staging`, `crm-rootless`.

## Installation

An administrator runs `backend/ci/provision-staging-runner.sh` as root on staging and supplies a short-lived **repository runner registration token on standard input**. Obtain the token through GitHub Settings → Actions → Runners, or `POST /repos/kizzhang/PlanckSemicon_CRM/actions/runners/registration-token`. Never commit tokens, credentials, runner `.credentials*`, or `.runner` files. The installer is for this repository and Ubuntu version only.

The script installs rootless prerequisites without upgrading the existing Docker daemon or restarting existing application services. It creates a locked `crm-ci` account with no supplementary groups, enables systemd lingering, registers the runner, and starts two user services. Downloads of the runner and PowerShell are SHA-256 verified. Runner automatic updates remain enabled.

## Isolation and capacity

| Item | Configuration |
| --- | --- |
| Unix account/home | `crm-ci`, `/home/crm-ci`, mode 0700 |
| Runner/workspace | `/home/crm-ci/actions-runner`, `_work` |
| Tools | `/home/crm-ci-tools`, owned by root |
| Docker | Rootless daemon, `/run/user/<crm-ci UID>/docker.sock` |
| Docker data | `/home/crm-ci/.local/share/docker` |
| Whole-account ceiling | 4 CPU cores, 6 GiB RAM, 1 GiB swap; memory pressure starts at 5 GiB |
| Concurrency | One registered runner, one job at a time |
| Resource priority | CPU/IO weight 25 |

The CI account cannot read the staging operator's home or use the host Docker socket. No deployment credentials or production access are installed. This is a persistent runner on the staging host, so it is intended for trusted code in this private repository. Rootless Docker is not a VM isolation boundary; do not admit untrusted fork jobs. Moving to public contributions requires dedicated disposable runner machines.

The companion CI pipeline uses unique project/image names per run and attempt, loopback HTTP with a dynamic port, cleanup on success/failure/cancellation, and stale-run recovery. It refuses any Docker socket other than this user's rootless socket. Build cache is bounded and aged out; CI refuses to start below 40 GiB free space in `/home`.

## Operations

Use the dynamically resolved UID; the initial deployment allocated UID 1002.

```bash
ci_uid=$(id -u crm-ci)
sudo -u crm-ci env XDG_RUNTIME_DIR=/run/user/$ci_uid DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$ci_uid/bus systemctl --user status docker crm-actions-runner
sudo journalctl _UID=$ci_uid --since '15 minutes ago'
sudo systemctl show user-$ci_uid.slice -p CPUQuotaPerSecUSec -p MemoryCurrent -p MemoryMax
gh api repos/kizzhang/PlanckSemicon_CRM/actions/runners --jq '.runners[] | {name,status,busy,labels:[.labels[].name]}'
```

For maintenance, wait until GitHub reports `busy=false`, then stop/restart only `crm-actions-runner` using the same `systemctl --user` command. Review available space and failed CI artifacts before removing stale resources. Never run host-level Docker prune commands. A hard kill or host reboot may leave test resources until the next job's stale cleanup.

To retire the runner: stop its user service, remove the registration in repository settings, disable the two CI user services and lingering, then archive/remove only CI-owned directories after reviewing their resolved paths. Do not alter staging application containers or volumes.

## References

- [GitHub self-hosted runners](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/add-runners)
- [Rootless Docker](https://docs.docker.com/engine/security/rootless/)
- [Rootless systemd and resource limits](https://docs.docker.com/engine/security/rootless/tips/)

Initial deployment on 2026-09-09: runner registered and online; rootless Docker and user services active; account resource limits verified; existing staging CRM remained healthy.
