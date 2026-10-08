# Rayher CRM independent Frappe stack

This directory defines the new CRM-only Frappe/ERPNext environment. It is intentionally isolated from the existing `rayher-crm` containers and `rayher-crm_*` volumes.

## Local lifecycle

From the repository root:

```powershell
docker compose --env-file backend/.env.example -f backend/compose.yaml config
if ($LASTEXITCODE -ne 0) { throw 'Compose configuration validation failed.' }
pwsh -NoProfile -File backend/tests/compose-contract.ps1
if ($LASTEXITCODE -ne 0) { throw 'Compose contract failed.' }
pnpm build:frappe
if ($LASTEXITCODE -ne 0) { throw 'Frappe frontend build failed.' }
pwsh -NoProfile -File backend/scripts/prepare-app-build-context.ps1
if ($LASTEXITCODE -ne 0) { throw 'Verified app archive preparation failed.' }
$archiveHash = (Get-FileHash -LiteralPath backend/build/rayher_crm.zip -Algorithm SHA256).Hash
docker compose --env-file backend/.env.example -f backend/compose.yaml build --build-arg "CRM_APP_ARCHIVE_SHA256=$archiveHash" backend
if ($LASTEXITCODE -ne 0) { throw 'Verified backend image build failed.' }
docker compose --env-file backend/.env.example -f backend/compose.yaml up -d --no-build
if ($LASTEXITCODE -ne 0) { throw 'CRM stack startup failed.' }
docker compose --env-file backend/.env.example -f backend/compose.yaml ps
if ($LASTEXITCODE -ne 0) { throw 'CRM stack status check failed.' }
```

The tracked `.env.example` is the reproducible default template. It publishes only the frontend on `127.0.0.1:2224`, so a local stack is reachable from that machine alone; MariaDB, Redis, and ClamAV have no published host ports. The tracked `lan.env.example` is the opt-in trusted-LAN template: it differs from `.env.example` only in `HTTP_BIND_ADDRESS` and publishes the same frontend on `0.0.0.0:2224` for colleagues on the company network. Copy whichever one you need to an ignored environment-specific file before adding deployment-specific values.

The first start creates two random credentials inside the new `rayher-crm-stage1-local_local-secrets` Docker volume. They are never placed in `.env`, source control, or command output. The same start creates `rayher-crm.localhost` and installs ERPNext. The CRM custom app `rayher_crm` is added and installed in the backend implementation stage; HRMS, the PR #24 ERP/OA app, and OCR are not installed.

Both templates explicitly set `ALLOW_TESTS=false`; production is never a test runner. Isolated integration tests use `test.env.example`, loopback port `2225`, and the dedicated `.test` site.

Production serves the CRM at `https://crm.example.invalid`. Nginx on the host terminates TLS on ports 80 and 443 and proxies to the Compose frontend, which production binds to `127.0.0.1:4174` so that no plain-HTTP path to the CRM reaches the LAN. The backend trusts the scheme the frontend forwards (`FORWARDED_ALLOW_IPS`), so Frappe marks its cookies `Secure` behind that proxy. The Nginx template, the production values and the certificate procedure are in `deploy/nginx/README.md` and `docs/HTTPS-内网部署方案.md`.

The unified release gate and archive builder require PowerShell 7 (`pwsh`). Run the full gate with `pwsh -NoProfile -File backend/tests/run-release-gate.ps1 -StartBackend`; omitting `-StartBackend` fails closed instead of testing a stale stack. The gate recreates only the dedicated `rayher-crm-stage1-tests` volumes, builds test code as `rayher-crm-stage1:v15-test`, and verifies the production package as `rayher-crm-release-gate:v15`, so it cannot overwrite the LAN image tag.

## Safe inspection

```powershell
docker compose --env-file backend/.env.example -f backend/compose.yaml ps
docker compose --env-file backend/.env.example -f backend/compose.yaml logs --tail 200
docker compose --env-file backend/.env.example -f backend/compose.yaml exec redis-cache redis-cli ping
docker compose --env-file backend/.env.example -f backend/compose.yaml exec redis-queue redis-cli ping
```

Use a normal `docker compose ... restart` to prove persistence. Do not use `down --volumes` for routine operation because that deletes the isolated database, sites, and generated local credentials.

## Persistence and backup boundary

The seven named volumes are `db-data`, `redis-cache-data`, `redis-queue-data`, `sites`, `logs`, `local-secrets`, and `clamav-data`, all rendered with the `rayher-crm-stage1-local_` prefix. A recoverable backup must include at least a Frappe database dump, public/private site files, and the site configuration required to restore them. Redis and ClamAV signature data are operational state rather than the system of record.

The restore drill is intentionally more strict than a backup-only check. It creates a fresh backup, restores it into the fixed non-production site `rayher-crm-restore-check.localhost`, compares CRM schema, Company count and private-file count, then drops only that temporary site. It refuses to overwrite an existing site and validates any post-drop search-index residue before removing it. Run it from the repository root without printing secret-volume contents:

```powershell
$scriptMount = (Resolve-Path -LiteralPath backend/scripts/backup-restore-drill.sh).Path + ':/tmp/backup-restore-drill.sh:ro'
docker compose --env-file backend/.env.example -f backend/compose.yaml run --rm --no-deps -v $scriptMount -v rayher-crm-stage1-local_local-secrets:/run/crm-local-secrets:ro --entrypoint bash migrate /tmp/backup-restore-drill.sh
```

## Ubuntu staging/production handoff

Use the same Compose topology and pinned images on Ubuntu. Give each environment a different `COMPOSE_PROJECT_NAME`, site hostname, frontend binding and secret store. Put TLS and the public hostname at a reverse proxy, keep MariaDB/Redis/ClamAV private, replace the local credential volume with deployment-managed secrets, set resource limits and log rotation, and run backup/restore plus rollback drills before traffic cutover. Staging and production must never attach the local volumes.
