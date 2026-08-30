# CRM Stage 5A Frappe App and API Foundation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 把空的 `backend/apps/rayher_crm` 变成可构建、可安装、可测试的 Frappe v15 custom app；建立服务端角色/能力权威、稳定响应 envelope、bootstrap/health API，并把新本地栈切换到只包含 Frappe/ERPNext/`rayher_crm` 的全新自定义镜像。

**Architecture:** 官方 ERPNext v15 digest 仅作为不可变 base image；Compose 内可审计的 `dockerfile_inline` 将 `rayher_crm` 安装到 bench，并构建新的 `rayher-crm-stage1:v15-local` 镜像后幂等执行 install/migrate。API 使用 `/api/method/rayher_crm.api.v1.*`，响应统一为 `{data, meta, warnings}`；身份只取 `frappe.session.user`，角色/能力只由服务端角色映射产生。Stage 5A 不建业务 DocType、不接前端 adapter，先冻结可部署与安全基座。

**Tech Stack:** Frappe 15.116.1、ERPNext 15.118.3、Python 3.11（镜像运行时）、MariaDB 10.6、Redis 6.2、Pytest/FrappeTestCase、Docker Compose。

**Execution Status:** Complete (2026-08-04).

## Global constraints

- 权威契约：`docs/CRM-后端数据库对接契约-2026-08-04.md`；Stage 4 计划和隔离约束继续有效。
- 不使用 bind-mounted Python 源码冒充部署；custom app 必须进入新镜像，保证 Ubuntu 可复制。
- 不引用或重建旧 `rayher-crm:v16.28.0-local`；只重建新项目 `rayher-crm-stage1-local` 的应用容器，新数据库卷保持不变。
- App 只依赖 Frappe/ERPNext；不加入 HRMS、`rayher_hr_payroll`、OCR 或新第三方 Python 依赖。
- `frappe.session.user` 是 user id 唯一来源；客户端不得提交角色或 capability。
- `Administrator` 在本地基座映射为 CRM Manager；普通用户必须拥有恰好一个 CRM 角色，角色冲突失败关闭。
- Stage 5A 保持前端 `VITE_API_ADAPTER=mock` 默认值和 `createFrappeApi()` 的 No-Go；真实业务接口尚未完成，不能提前切换。
- 使用 TDD；不 reset、stash、checkout、clean、commit。

---

### Task 1: Freeze the app packaging contract

**Files:**
- Create: `backend/tests/app-package-contract.ps1`
- Modify: `backend/.env.example`
- Modify: `backend/compose.yaml`

- [x] Write RED checks for required app metadata, pinned base image, new custom image name, no old image, and install/migrate one-shot services.
- [x] Add a Linux-compatible inline Dockerfile that copies and editable-installs `apps/rayher_crm` as the non-root `frappe` user.
- [x] Split `FRAPPE_BASE_IMAGE` (digest-pinned) from `CRM_IMAGE` (new local build output); preserve Stage 4 DB/Redis/image pins and volume names.
- [x] Add idempotent `install-app` and `migrate` services; long-running services depend on successful migrate.

### Task 2: Scaffold a minimal valid Frappe v15 app

**Files:**
- Create: `backend/apps/rayher_crm/pyproject.toml`
- Create: `backend/apps/rayher_crm/MANIFEST.in`
- Create: `backend/apps/rayher_crm/README.rst`
- Create: `backend/apps/rayher_crm/rayher_crm/__init__.py`
- Create: `backend/apps/rayher_crm/rayher_crm/hooks.py`
- Create: `backend/apps/rayher_crm/rayher_crm/modules.txt`
- Create: `backend/apps/rayher_crm/rayher_crm/patches.txt`
- Create minimal package directories and `__init__.py` files for `api/v1`, `permissions`, `services`, `setup`, and `tests`.

- [x] Keep metadata compatible with Frappe v15/Python >=3.10 and package discovery.
- [x] Register `after_install`/`after_migrate` setup hooks only for idempotent roles/config, never demo business data.
- [x] Confirm package contract GREEN before image build.

### Task 3: Implement the server-owned identity, role, and capability foundation

**Files:**
- Create: `backend/apps/rayher_crm/rayher_crm/permissions/roles.py`
- Create: `backend/apps/rayher_crm/rayher_crm/setup/install.py`
- Create: `backend/apps/rayher_crm/rayher_crm/tests/test_roles.py`

- [x] Define `CRM Manager`, `CRM Sales`, `CRM Engineer` and a frozen server capability matrix matching the frontend roles.
- [x] Resolve `frappe.session.user`; map Administrator to Manager and fail closed for missing/conflicting CRM roles.
- [x] Install roles idempotently without creating demo users or passwords.
- [x] Test role creation, Administrator mapping, normal mapping, no-role denial, and multi-role conflict.

### Task 4: Implement response envelope and bootstrap/health APIs

**Files:**
- Create: `backend/apps/rayher_crm/rayher_crm/api/v1/responses.py`
- Create: `backend/apps/rayher_crm/rayher_crm/api/v1/bootstrap.py`
- Create: `backend/apps/rayher_crm/rayher_crm/api/v1/health.py`
- Create: `backend/apps/rayher_crm/rayher_crm/tests/test_api_foundation.py`

- [x] Generate a server request ID and ISO timestamp; return `{data, meta, warnings}` with no secret/session leakage.
- [x] Bootstrap returns stable `user.id`, display name, initials, CRM role/team, capabilities, and app version from server state.
- [x] Health endpoint is guest-safe and reveals only status/app/version, not DB credentials, site config or installed-user data.
- [x] Test authenticated bootstrap, unauthorized/no-role behavior, response shape, request IDs and health redaction.

### Task 5: Build, install, migrate, and run real Frappe tests

**Files:**
- Modify only files above if real build/test evidence exposes a defect.

- [x] Run Compose/app package contracts.
- [x] Build `rayher-crm-stage1:v15-local` from the pinned official v15 base; inspect image/app path and confirm old image is not referenced.
- [x] Run idempotent install/migrate against `rayher-crm.localhost`; verify `rayher_crm` appears in `bench list-apps`.
- [x] Run `bench --site rayher-crm.localhost run-tests --app rayher_crm` and require all tests pass.
- [x] Call health and Administrator bootstrap through HTTP, verify envelope and no sensitive fields.
- [x] Re-run install/migrate and confirm idempotence; verify backend/frontend healthy and HTTP 200.
- [x] Re-run frontend `pnpm.cmd typecheck`, full tests and build because shared contracts remain authoritative.

### Task 6: Close Stage 5A and plan the first business vertical slice

**Files:**
- Update: `docs/CRM-持续执行审计日志-2026-08-04.md`
- Update: this plan
- Create next plan: `docs/superpowers/plans/2026-08-04-crm-stage5b-account-contact-lead.md`

- [x] Record every packaging/role/API choice, build issue, container replacement and verification result without credentials.
- [x] Mark Stage 5A complete only after fresh Docker, Frappe test and frontend regression evidence.
- [x] Keep contract B/A items unchecked unless their full acceptance criteria are actually satisfied.
- [x] Mirror the audit log to Desktop and continue to Account/Contact/Lead vertical slice.

## Stage 5A acceptance Gate

1. `rayher_crm` is installed on `rayher-crm.localhost` from the new repository-built image.
2. App install/migrate is repeatable; all new long-running services use the custom image and remain healthy/running.
3. Roles/capabilities are server-owned and covered by real Frappe tests; no role trusts client input.
4. Health/bootstrap endpoints use the frozen envelope and expose no secret material.
5. Frappe app tests and frontend typecheck/full tests/build pass.
6. Old project/image/volumes remain untouched; Stage 4 isolation contract remains GREEN.
7. Frontend remains Mock by default until business APIs and E2E Gate are complete.
