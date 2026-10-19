# Continuous integration gates

> 本作品集仓库的 GitHub CI 仅运行前端检查与打包，均使用 GitHub 托管 Runner。原服务器的后端自动任务已移除，后端验证与部署脚本仍可按需执行。下文保留原项目完整发布检查的设计记录。

The required GitHub check remains **release-gate**. It passes only when all three jobs succeed. Failed, cancelled, or skipped jobs block it, including backend jobs refused for fork PRs.

| Job | Runs on | Checks |
| --- | --- | --- |
| frontend | GitHub Ubuntu | Frozen dependency installation, TypeScript, Vitest, per-case JUnit |
| package | GitHub Ubuntu | Frappe build, Compose/frontend/package contracts, report-validator regression cases, reproducible production/test archives, SHA-256 manifest tied to the checked-out commit |
| backend | staging `crm-staging-01` | Fresh rootless Docker stack, native Frappe JUnit, all six Stage 5B–5G HTTP acceptance suites, separate verified production image build |

Frontend and packaging run in parallel. Backend starts only after both pass and downloads the exact archives produced in the same run. It verifies their commit and SHA-256 values before building. The test image adds only the hash-pinned native JUnit writer; the production image is built from the production archive without this dependency.

The verified archive artifact has a stable name within a workflow run. Re-running only failed backend jobs reuses the successful packaging job's artifact; re-running packaging overwrites that artifact. Diagnostic artifacts remain separated by attempt number.

## Triggers and permissions

PRs targeting any branch are checked, including stacked PRs. Pushes run only for `main`, avoiding the duplicate push/PR runs for feature branches. Manual dispatch is available after the workflow is on the default branch. New runs cancel older runs for the same PR/ref. The token has `contents: read`; checkouts do not persist credentials. External Actions are pinned to commits.

Only same-repository PRs can reach the staging runner. A fork PR receives frontend/package checks and a failed aggregate gate because backend is skipped. Review and import trusted changes into a repository branch when needed; do not use `pull_request_target` to run fork code.

## Reports and isolation

Every run retains frontend, package and backend diagnostic artifacts for 14 days, including native JUnit, per-phase logs, container health/logs, image ID and cleanup outcome. Backend report validation rejects zero executed tests, all-skipped runs, missing/duplicate summaries, nonzero exits, tracebacks and any stdout/XML inconsistency. It validates actual test cases, not a synthetic XML summary.

Each backend run uses `crm-ci-<run ID>-<attempt>` for its project and distinct test/production image tags. Explicit environment isolation prevents operator settings from redirecting Compose. A `.test` site, loopback-only HTTP port and fresh named volumes are mandatory. Docker allocates an available port at startup; CI then pins that port before testing so service restarts keep the same endpoint. Startup waits for initialization/migration and health checks with a 15-minute bound. Six HTTP suites run sequentially against this stack, including file scanning/report generation and restart persistence.

HTTP RPC helpers explicitly declare form content types so a preceding JSON or multipart request cannot change how the next request is interpreted. DateTime values parsed from API responses are encoded as ISO timestamps with timezone and full precision in both form and multipart bodies. A loopback HTTP fixture regression-tests all six RPC and three multipart helpers, including reused sessions, Unicode/form escaping and timestamp round trips. All HTTP suites produce a result even when an earlier suite fails; any failure still blocks the gate.

Cleanup runs in the shell EXIT trap and an `always()` workflow step. The next job recovers CI-labelled resources left by a hard cancellation or reboot. Cleanup refuses the host Docker socket and touches only the dedicated rootless daemon. Reports are collected before resource removal; a cleanup failure fails the job. The pipeline does not deploy the CRM to staging or production.

## Merge record

PR #6 and PR #9 landed on `main` together as one squash commit, followed by the staging runner PR #8. The sequence this section originally recommended — merge #6, then retarget #9 to `main` — does not work: #9 forked from a commit preceding #6's merge-from-main, so retargeting conflicts on `test_stage5g_dashboard_stakeholders.py`, `run-release-gate.ps1` and `seven-page-workspace.test.ts`, the last as a whole-file conflict because the two sides disagree on line endings. #9 was merged into `codex/fix-release-gate` first instead, which is conflict-free, and the combined branch was then squashed onto `main`.

The squash commit carrying #6 and #9 was created with the placeholder title `probe`. Its body is intact and its content is the change described throughout this document.

Measured on the final merged content: 802 frontend tests across 118 files, 265 backend tests with zero skips, all six HTTP acceptance suites passing, reproducible production package, isolated production image build and clean teardown. Earlier figures quoted in the pull request descriptions (694 frontend tests) were measured before PR #4 and PR #7 were merged in, and PR #6's claim of stabilized date-sensitive calendar and dashboard tests does not correspond to any change in that branch.

`main` requires the `release-gate` context through repository ruleset "Protect main", with strict up-to-date checks and linear history. Because that context now depends on the single self-hosted runner, the repository owner is registered as a bypass actor in pull-request mode: a pull request can still be merged when the runner is unavailable, but direct pushes to `main` remain blocked.

## Known gaps

These are real and unfixed. They are recorded so that a green gate is not read as a stronger guarantee than it is.

- Neither the frontend nor the backend report has a minimum test-count floor. Deleting or skipping most of the suite still passes, as long as at least one test executes. The frontend JUnit is produced and uploaded but not validated at all.
- `docker image prune -af --filter until=168h` in `backend/ci/cleanup.sh` filters on image creation time, not last use, so it evicts the digest-pinned `frappe/erpnext`, `mariadb`, `redis` and `clamav` images at the start of every backend run. Each run then re-pulls several GB, and a registry outage fails the gate repository-wide.
- The report-tools build retags its parent image, leaving one dangling multi-GB image per run that cleanup does not remove.
- The self-hosted runner is not registered with `--ephemeral` and no environment approval gate protects the backend job. `actions/checkout` cleans the worktree but not `.git/`, so state planted by one run can execute during later checkouts. The fork guard is correct and complete; this gap concerns same-repository branches.
- The Frappe app archive is not byte-identical across Windows and Linux, because .NET stamps the host byte in the zip central directory. The SHA-256 manifest binds an archive to a commit but is computed from the same artifact it validates, so it detects corruption in transit rather than substitution.
- Negative assertions in the HTTP acceptance suites compare status codes only and do not inspect `exc_type`, so an unrelated permission regression can satisfy a 403 expectation. In `http-stage5f` the `OtherSales` session is never exercised with a successful call, so three of its checks could pass for the wrong reason.

Local validation of report handling: `pwsh -NoProfile -File backend/tests/backend-test-report-contract.ps1`. Run `bash backend/ci/test-environment.sh` to exercise environment/cleanup guards with a fake Docker CLI. Validate workflow syntax with `actionlint`; custom labels are listed in `.github/actionlint.yaml`. The local unified `run-release-gate.ps1 -StartBackend` command also installs the JUnit writer in its test image and retains native reports under `backend/build/ci-reports`.

Future separate work: coverage baselines, browser E2E, dependency/security scanning and CD promotion/rollback. These are not represented as completed gates here.
