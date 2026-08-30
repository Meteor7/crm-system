# CRM Staging Full-Stack Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the current database-backed Frappe/ERPNext v15 CRM stack on `203.0.113.58:4174`, verify it fully, and then retire the static Mock service on port 4173.

**Architecture:** Build the Vue application in Frappe mode, package the `rayher_crm` app through the protected-file-safe ZIP builder, and deploy the repository Compose topology as an isolated staging project. Cut over only after local gates and remote preflight pass; use fresh staging volumes and never touch unrelated Docker resources.

**Tech Stack:** Vue 3, TypeScript, Vite, Frappe/ERPNext v15, MariaDB 10.6, Redis 6.2, ClamAV 1.4.5, Docker Compose v2, Ubuntu systemd, Windows OpenSSH.

## Global Constraints

- Target is `plancksemicon@203.0.113.58`; the user enters SSH passwords interactively.
- Entry point is `http://203.0.113.58:4174/crm` on the trusted LAN.
- Do not preserve a rollback backup of the old static service, per user instruction.
- Do not delete or reuse unrelated containers, volumes, networks, sites, or databases.
- Clone the current local Frappe site database, public files, private files, users, roles, and permissions; do not migrate browser Mock/localStorage/IndexedDB data.
- Do not log credentials or expanded secret values.
- Stop before remote cutover if any local gate or remote ownership check fails.

---

### Task 1: Validate and Rebuild the Release

**Files:**
- Modify generated assets: `backend/apps/rayher_crm/rayher_crm/public/crm/**`
- Modify generated archive: `backend/build/rayher_crm.zip`
- Verify: `backend/tests/frappe-frontend-contract.ps1`
- Verify: `backend/tests/app-package-contract.ps1`
- Verify: `backend/tests/compose-contract.ps1`

**Interfaces:**
- Consumes: current Vue source, Frappe app source, `backend/compose.yaml`.
- Produces: verified Frappe frontend assets and plaintext `backend/build/rayher_crm.zip` with recorded SHA-256.

- [ ] **Step 1: Render Compose without exposing secrets**

Run: `docker compose --env-file backend/.env.example -f backend/compose.yaml config --quiet`

Expected: exit code 0.

- [ ] **Step 2: Run static deployment contracts**

Run each script with `powershell.exe -NoProfile -ExecutionPolicy Bypass -File`:

```powershell
backend/tests/compose-contract.ps1
backend/tests/app-package-contract.ps1
```

Expected: `Compose contract passed.` and `App package contract passed.`

- [ ] **Step 3: Build the frontend in Frappe mode**

Run: `pnpm.cmd run build:frappe`

Expected: TypeScript passes and Vite writes the Frappe assets without Mock seed leakage.

- [ ] **Step 4: Validate the generated Frappe frontend**

Run: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File backend/tests/frappe-frontend-contract.ps1`

Expected: `Frappe frontend contract passed` with file, byte, and Mock-guard counts.

- [ ] **Step 5: Recreate and inspect the application ZIP**

Run: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File backend/scripts/prepare-app-build-context.ps1`

Then calculate: `Get-FileHash backend/build/rayher_crm.zip -Algorithm SHA256`.

Expected: archive opens, entry count matches source, and no `%TSD-Header-###%` wrapper exists.

### Task 2: Run Focused Local Verification

**Files:**
- Verify: `src/api/frappe-adapter.test.ts`
- Verify: `src/app/AppShell.frappe.test.ts`
- Verify: `src/stores/app.frappe-runtime.test.ts`
- Verify: `backend/apps/rayher_crm/rayher_crm/tests/**`

**Interfaces:**
- Consumes: rebuilt Frappe frontend and application package.
- Produces: evidence that adapter, web entry, contracts, and backend tests pass before upload.

- [ ] **Step 1: Run focused frontend Frappe tests**

Run Vitest for the three Frappe runtime test files with the project-local Vitest executable.

Expected: all selected tests pass.

- [ ] **Step 2: Run typecheck and package diff checks**

Run: `pnpm.cmd run typecheck` and `git diff --check`.

Expected: both exit 0, with unrelated pre-existing worktree changes preserved.

- [ ] **Step 3: Run the packaged backend tests if the local Compose stack is available**

Run Frappe tests inside the isolated local stack for `rayher_crm`, or use the already-proven package contract if the local runtime is unavailable.

Expected: backend tests pass; otherwise deployment stops with the exact runtime blocker.

- [ ] **Step 4: Create and verify the current local site backup**

Run `bench --site rayher-crm.localhost backup --with-files --compress` inside the local backend container. Resolve the newest database, public-file, private-file, and backup metadata files, record their SHA-256 values and representative CRM record counts, and export the site encryption key through a restricted temporary channel without printing it.

Expected: all backup components exist, hashes are stable, the source site remains healthy, and the key is never written to logs.

### Task 3: Establish Interactive SSH and Perform Remote Preflight

**Files:**
- Create locally: `.codex-tmp/staging-ssh-control` control socket only.
- No remote writes during preflight.

**Interfaces:**
- Consumes: user-entered SSH password.
- Produces: a short-lived authenticated SSH master session and read-only server inventory.

- [ ] **Step 1: Open the SSH master login window**

Start visible PowerShell with:

```powershell
ssh -M -S C:\Users\PlanckSemicon\Desktop\semiconductor-crm\.codex-tmp\staging-ssh-control -o ControlPersist=900 plancksemicon@203.0.113.58
```

Expected: user enters the password and receives the remote shell prompt.

- [ ] **Step 2: Verify the reusable control session**

Run: `ssh -S <control-path> -O check plancksemicon@203.0.113.58`.

Expected: master session reports running.

- [ ] **Step 3: Collect remote preflight evidence**

Check OS, identity, Docker/Compose versions, disk, memory, port 4173 ownership, `rayher-crm-staging.service`, existing Compose projects, and exact target directories.

Expected: Docker is usable, resources are sufficient, old service ownership is understood, and no unrelated resource conflicts with the new project name.

### Task 4: Upload and Validate the Release on Staging

**Files:**
- Upload repository deployment subset to: `/home/plancksemicon/apps/rayher-crm-stage1-staging/`.
- Create remote restricted file: `backend/.env.staging`.
- Upload the verified local Frappe backup set into a mode-700 staging restore directory.

**Interfaces:**
- Consumes: verified repository Compose files, scripts, app ZIP, pinned image variables, and the complete local Frappe backup set.
- Produces: server-side validated release directory and staging Compose environment.

- [ ] **Step 1: Create the exact remote release directory**

Create only `/home/plancksemicon/apps/rayher-crm-stage1-staging` and verify its resolved path remains under `/home/plancksemicon/apps`.

- [ ] **Step 2: Upload the minimal deployment inputs**

Upload `backend/compose.yaml`, `.env.example`, `build/rayher_crm.zip`, required deployment scripts/tests, and the database/public/private backup archives without expanding secrets.

- [ ] **Step 3: Create `.env.staging` with restricted permissions**

Set:

```dotenv
COMPOSE_PROJECT_NAME=rayher-crm-stage1-staging
SITE_NAME=203.0.113.58
HTTP_BIND_ADDRESS=0.0.0.0
HTTP_PORT=4173
ALLOW_TESTS=false
CRM_IMAGE=rayher-crm-stage1:v15-staging
```

Copy the four digest-pinned base image assignments from `.env.example`; set file mode 600 and never print expanded values.

- [ ] **Step 4: Revalidate server-side inputs**

Run Compose config quiet validation and compare the uploaded ZIP SHA-256 to the local recorded value.

Expected: Compose validation passes and every release/backup SHA-256 matches the locally recorded value before cutover.

### Task 5: Cut Over to the Full Stack

**Files:**
- Remove old unit after stopping: `/etc/systemd/system/rayher-crm-staging.service`.
- Remove old static application directory only after resolving and confirming its exact path.
- Create Compose resources prefixed `rayher-crm-stage1-staging_`.

**Interfaces:**
- Consumes: preflight-approved server and validated release.
- Produces: running full Frappe staging stack on port 4174, followed by retirement of the old port-4173 service only after acceptance.

- [ ] **Step 1: Build the staging CRM image while the old service remains online**

Run: `docker compose --env-file backend/.env.staging -f backend/compose.yaml build backend`.

Expected: custom image build succeeds.

- [ ] **Step 2: Keep the old static service online during restore**

Keep `rayher-crm-staging.service` serving port 4173 while the new stack restores and starts on port 4174.

- [ ] **Step 3: Start the complete Compose project and restore the cloned site**

Run Compose initialization, restore the database plus public/private file archives into site `203.0.113.58`, securely apply the source encryption key while retaining the target database credential, install or reconcile `rayher_crm`, and run migrate. Then start all long-running services.

Expected: site restore, app reconciliation, migration, frontend, workers, scheduler, websocket, Redis, MariaDB, and ClamAV complete or start successfully on port 4174; cloned users and roles are present without copied browser sessions.

- [ ] **Step 4: Check service health and migration**

Run Compose `ps`, inspect bounded logs, and execute `bench --site 203.0.113.58 migrate` once more as an idempotency check.

Expected: required long-running services are running/healthy and one-shot initialization services exit 0.

- [ ] **Step 5: Retire the old port-4173 service after acceptance**

Only after the new port-4174 HTTP and data gates pass, stop and disable `rayher-crm-staging.service`, confirm port 4173 is released, remove the exact unit, reload systemd, and remove only its confirmed old static application directory.

### Task 6: Acceptance and Handoff

**Files:**
- No source edits expected.

**Interfaces:**
- Consumes: running staging stack.
- Produces: HTTP, browser, session, and database-persistence evidence.

- [ ] **Step 1: Verify HTTP entry points**

Check `/api/method/ping`, `/crm`, and the authenticated asset entry with the correct Host header.

Expected: ping 200; Guest `/crm` reaches the Frappe login boundary.

- [ ] **Step 2: Verify browser login and representative pages**

Use a real Frappe account to open Dashboard, Account list/detail, and a representative create/edit workflow.

Expected: no Mock identity switch or seed data and no blocking console errors.

- [ ] **Step 3: Verify persistence and server-side role boundary**

Create or edit a controlled staging record, refresh, and confirm it is returned by the database-backed API. Exercise representative Manager, Sales, and Engineer authorization gates when those users exist.

Expected: persistence survives refresh and forbidden actions are rejected server-side.

- [ ] **Step 4: Reconcile cloned data and attachments**

Compare representative Customer, Contact, Lead, CRM Opportunity, Booking, Demo Request, Evaluation, Installed Tool, and Visit counts between the saved source snapshot and staging. Open one permitted public attachment and one permission-controlled private attachment when present.

Expected: counts match the source snapshot and attachment access follows the cloned permissions.

- [ ] **Step 5: Close the SSH master and report**

Run SSH control `-O exit`, report the release SHA-256, Compose project, site name, service health, acceptance evidence, and the explicit absence of an old-service backup.
