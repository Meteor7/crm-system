# CRM Staging Full-Stack Deployment Design

## Goal

Replace the static Mock-only service on `203.0.113.58` with the repository's current Frappe/ERPNext v15 CRM stack and verify real database-backed behavior.

## Approved Scope

- Target host: `203.0.113.58`.
- SSH user: `plancksemicon`; the user enters the password interactively and it must not be logged or stored.
- User entry point: `http://203.0.113.58:4174/crm` on the trusted internal network.
- Deployment unit: `backend/compose.yaml`, including Frappe/ERPNext v15, MariaDB, Redis, ClamAV, workers, scheduler, websocket, and the `rayher_crm` app.
- Seed staging from a complete clone of the current local Frappe site at `http://203.0.113.10:2224/crm`: database, public files, private files, users, roles, and permissions. Browser Mock/localStorage/IndexedDB data is not migrated.
- Stop and remove the old `rayher-crm-staging.service` and its old static application directory. The user explicitly declined a rollback backup of that service.
- Do not delete, reuse, or modify unrelated containers, Compose projects, databases, networks, or volumes.
- Do not add a domain, public exposure, or TLS in this deployment. Port 4174 is for trusted-LAN staging access only.

## Build and Packaging

Build the Vue application in Frappe mode so `VITE_API_ADAPTER=frappe` behavior and Frappe-only aliases are embedded in `backend/apps/rayher_crm/rayher_crm/public/crm`. Recreate `backend/build/rayher_crm.zip` from the current app tree and record its SHA-256 before upload.

Because this machine uses transparent file encryption, validate the generated archive independently before upload: the ZIP must open, contain plaintext HTML/Python/JSON assets, contain valid binary assets, and contain no `%TSD-Header-###%` wrappers. Never strip or rewrite protected wrappers as a repair technique.

## Remote Architecture and Cutover

Use an isolated Compose project and fresh named volumes owned by this deployment. Bind the new CRM HTTP entry to host port 4174. Before any write, inspect Docker/Compose availability, free disk and memory, port ownership, the old systemd service, and existing Compose project names.

Before upload, create a fresh `bench backup --with-files --compress` from local site `rayher-crm.localhost`, record database/public/private archive hashes and source record counts, and preserve the source site's encryption key without exposing it. After preflight passes, upload only the validated release inputs and backup set, render the staging environment file without printing secrets, build the backend image, and start the stack on 4174. Let the stack create the target site, restore the database and both file archives, install or reconcile `rayher_crm`, restore the encryption key, and run migrations. Keep the old static service online on 4173 until the new 4174 service passes health, data, and HTTP acceptance; only then stop and remove the old service.

## Authentication and Data Flow

The browser must authenticate through a real Frappe session. The frontend calls same-origin `/api/method/...` endpoints through the Frappe adapter. Service methods enforce roles and scope, then write to MariaDB-backed standard ERPNext records and CRM DocTypes. The deployment must not expose the Mock identity switch or static Mock seed data.

Users, roles, and permission assignments are cloned from the current local Frappe database. Password hashes may be cloned, but active browser sessions and local administrator cookies must not be copied. The target site must use its own generated database credential while retaining the source encryption key required to read encrypted application fields.

## Failure Handling

- If local verification or archive inspection fails, do not upload or change the server.
- If the source backup is incomplete, any archive hash changes during transfer, or the source encryption key cannot be handled without disclosure, do not cut over.
- If remote preflight finds a port, project, or volume ownership conflict, stop and report the exact conflict.
- If image build or initial startup fails before migrations complete, leave the failed Compose project stopped for diagnosis and do not delete unknown resources.
- If migrations complete but acceptance fails, keep staging isolated and report the failed gate. Do not attempt a schema downgrade or destructive volume reset.
- The requested deployment has no old-service backup; this limitation must be stated in the final handoff.

## Acceptance Gates

Deployment is successful only when all of the following are verified:

1. Every required Compose service is running or healthy.
2. `/api/method/ping` returns HTTP 200.
3. Guest access to `/crm` reaches the Frappe login boundary, not a Mock dashboard.
4. An authenticated CRM user can open the dashboard and representative list/detail pages.
5. At least one controlled create/read/update flow persists through refresh and is visible in the database-backed API.
6. Manager, Sales, and Engineer sessions respect their server-side role boundaries.
7. No known Mock customer, request seed, or identity-switch control appears in the Frappe build.
8. Browser console and application logs contain no deployment-blocking errors.
9. Representative source and target record counts match after restore, and public/private attachment probes open successfully under the expected permissions.

## Out of Scope

- Production deployment.
- Importing historical browser-local Demo data; only the current local Frappe site is cloned.
- DNS, public ingress, or TLS certificate setup.
- Refactoring unrelated frontend or backend code.
- Deleting unrelated server resources.
