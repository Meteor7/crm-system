# Rayher CRM independent Frappe stack

This directory defines the new CRM-only Frappe/ERPNext environment. It is intentionally isolated from the existing `rayher-crm` containers and `rayher-crm_*` volumes.

## Local lifecycle

From the repository root:

```powershell
docker compose --env-file backend/.env.example -f backend/compose.yaml config
powershell.exe -NoProfile -ExecutionPolicy Bypass -File backend/tests/compose-contract.ps1
docker compose --env-file backend/.env.example -f backend/compose.yaml up -d
docker compose --env-file backend/.env.example -f backend/compose.yaml ps
```

The site is served only on the local loopback interface at `http://rayher-crm.localhost:2224`. MariaDB and both Redis services have no published host ports.

The first start creates two random credentials inside the new `rayher-crm-stage1-local_local-secrets` Docker volume. They are never placed in `.env`, source control, or command output. The same start creates `rayher-crm.localhost` and installs ERPNext. The CRM custom app `rayher_crm` is added and installed in the backend implementation stage; HRMS, the PR #24 ERP/OA app, and OCR are not installed.

The local `.env.example` explicitly sets `ALLOW_TESTS=true` so real Frappe integration tests can run. Ubuntu staging and production must override it to `false`; production is never a test runner.

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
