# CRM Stage 4 Independent Local Frappe Docker Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在本机建立一套全新的、与旧容器和旧卷完全隔离的 Frappe + ERPNext CRM Docker 栈，为后续 `rayher_crm` DocType/API 实现和端到端测试提供可重复环境，并保持可迁移至 Ubuntu staging/production。

**Architecture:** 对齐 PR #24 已验证的 Frappe 自定义 Python App 形态，但不复用其 HRMS、ERP 业务 App、OCR 服务或数据库。新栈使用独立 Compose project `rayher-crm-stage1-local`、独立网络、独立 MariaDB/Redis/Sites/Logs 卷，包含 database、cache、queue、backend、frontend、websocket、scheduler、short/long workers 与幂等初始化任务。旧 `rayher-crm` 容器、旧 `rayher-crm_*` 卷和旧 `rayher-crm:v16.28.0-local` 镜像保持不动且不得引用。

**Tech Stack:** Frappe/ERPNext v15 official image、MariaDB 10.6、Redis 6.2 Alpine、Docker Compose；CRM custom app 为 `rayher_crm`，后续 Stage 5 安装。基础镜像使用已验证可解析的不可变 multi-arch digest，避免浮动 tag 漂移。

**Execution Status:** 2026-08-04 completed. Static isolation contract passed; all long-running services are healthy/running; Frappe 15.116.1 and ERPNext 15.118.3 survived a controlled restart; HTTP ping returned 200.

## Evidence and version boundary

- PR #24 head `1f32ef0d32ebed1a07f38a0ab1499a82619c7851` 的 `pyproject.toml` 证明参考项目是 Frappe 自定义 Python App（`rayher_hr_payroll`，Python `>=3.10`），但该 PR 未提交基础 Frappe Compose，也未锁定 Frappe/MariaDB 版本。
- 因用户要求“不需要精确版本对齐”，本阶段只对齐 Frappe/Python App + MariaDB + Redis + workers 的技术栈与部署形态，不宣称版本与 PR #24 完全一致。
- 禁止使用已恢复的旧项目 `rayher-crm`、旧卷 `rayher-crm_*` 和旧镜像 `rayher-crm:v16.28.0-local`。
- 本阶段选用成熟 v15 线，并锁定当前已验证镜像索引：
  - `frappe/erpnext:v15@sha256:f9b97cd87143b8e8abe9cbe57fd2dd4d7fcad25ad460f5823c4c79f3580a32a8`
  - `mariadb:10.6@sha256:4066a44f4a0143c310fbe6972c254bbbb7a844a2be1418831a987fdbbc8ff8bd`
  - `redis:6.2-alpine@sha256:ec5e187c913d422cdf60f4216a5fdfb95246792c6de6fe21ff5bed75cbfc8c23`

## Global constraints

- 权威契约为 `docs/CRM-后端数据库对接契约-2026-08-04.md`，路线图为 `docs/superpowers/specs/2026-08-04-crm-backend-delivery-roadmap-design.md`。
- 不删除、不停止、不改名旧容器或卷；新项目和卷必须能与旧栈同时存在。
- MariaDB/Redis 不发布宿主端口；仅 Nginx frontend 发布本地端口。数据库访问只能经新 Compose 私有网络。
- `.env`、密码、site config、数据库文件、private files 不进入 Git；`.env.example` 只能包含占位符。
- 本地、staging、production 使用相同 Compose 结构，不硬编码 Windows 路径；Ubuntu 仅替换 env/secrets、域名、TLS/反向代理和资源参数。
- 初始化任务必须幂等；服务具备 healthcheck、restart policy、依赖健康条件和持久卷。
- 不安装 HRMS、PR #24 ERP/OA 业务 App、invoice OCR 或其他 sidecar。
- 不 reset、stash、checkout、clean、commit；只修改当前任务必要文件。

---

### Task 1: Freeze isolation and secret contracts with executable checks

**Files:**
- Create: `backend/tests/compose-contract.ps1`
- Create: `backend/.env.example`
- Modify: `.gitignore`

- [x] Write RED checks that require project name `rayher-crm-stage1-local`, unique volume names, no old image reference, no host ports for DB/Redis, and placeholder-only env values.
- [x] Remove only the blanket `backend/` ignore rule; add explicit ignores for backend runtime secrets, sites, logs and generated data where existing global rules are insufficient.
- [x] Define non-secret local defaults: site name, published frontend port, pinned image references and explicit project name.
- [x] Run the contract check and confirm RED because Compose does not yet exist.

### Task 2: Create the independent production-shaped Compose topology

**Files:**
- Create: `backend/compose.yaml`
- Create: `backend/README.md`

- [x] Add MariaDB, Redis cache/queue, configurator, create-site, backend, frontend, websocket, scheduler and short/long worker services.
- [x] Use new named volumes under the new Compose project; never declare old volumes as external and never bind old Docker data.
- [x] Add healthchecks, restart policies, dependency conditions, init semantics, network isolation and a single configurable frontend host port.
- [x] Keep site/database/admin secrets in a new local secret volume at runtime; examples contain no secrets.
- [x] Document local lifecycle, health verification, logs, backup boundary and Ubuntu migration differences without destructive cleanup commands.

### Task 3: Validate rendered configuration and prove isolation

**Files:**
- Modify: `backend/tests/compose-contract.ps1` if validation exposes a real contract gap

- [x] Run `docker compose --env-file backend/.env.example -f backend/compose.yaml config` and require exit 0.
- [x] Run the PowerShell compose contract and require all isolation/security assertions to pass.
- [x] Compare rendered project/container/volume names against `docker ps -a` and `docker volume ls`; assert no old identifiers are referenced.
- [x] Run `git diff --check` for Stage 4 files.

### Task 4: Start only the new stack and verify independent persistence

**Files:**
- Create locally only: `backend/.env` (must remain ignored; generate fresh non-logged secrets)
- Update: `backend/README.md` only if actual commands differ

- [x] Generate fresh local-only passwords without printing them and start with explicit project name `rayher-crm-stage1-local`.
- [x] Pull/build without using the old local CRM image; wait for init jobs and long-running services.
- [x] Verify new DB/Redis/Sites volumes exist and are distinct; inspect mounts and Compose labels.
- [x] Verify MariaDB healthy, Redis ping, Frappe site availability, scheduler/workers running and frontend HTTP health.
- [x] Restart the new stack without volume deletion and prove the site/database persist; old stack state remains unchanged.
- [x] Record actual container names, health results, port and any deviations in the audit log without secrets.

### Task 5: Close Stage 4 and hand off to backend implementation

**Files:**
- Update: `docs/CRM-持续执行审计日志-2026-08-04.md`
- Update: this plan

- [x] Record PR #24 evidence limits, old-stack discovery, isolation choice, image pins, test results and remaining risks.
- [x] Mark all completed checkboxes and execution status only after fresh verification.
- [x] Do not mark backend contract B items complete: Stage 4 provides infrastructure only; DocTypes/API/migrations remain Stage 5+.
- [x] Mirror the audit log to the Desktop review file.

## Stage 4 acceptance Gate

1. Rendered Compose config is valid and contains no secret literals.
2. New containers and volumes carry project `rayher-crm-stage1-local`; none reuse `rayher-crm_*` volumes or `rayher-crm:v16.28.0-local`.
3. DB and Redis have no published host ports; only the new frontend port is exposed.
4. New MariaDB, Redis, Frappe web, websocket, scheduler and both workers are healthy/running; init tasks exit 0.
5. HTTP site probe succeeds and persistence survives a normal restart.
6. Old containers/volumes remain untouched.
7. Config/docs use Linux-compatible relative paths and externalized secrets, ready for Ubuntu environment-specific hardening.
