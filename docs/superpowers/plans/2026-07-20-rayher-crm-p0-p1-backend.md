# QIHENG Demo CRM P0/P1 Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在本地 Docker 中运行 Frappe/ERPNext v16、MariaDB 和自定义 `rayher_crm` App，并将现有 Vue P0/P1 页面接入真实数据库、权限、流程和私有文件服务。

**Architecture:** 使用固定 `frappe/erpnext:v16.28.0` 构建自定义镜像，一个 `rayher.localhost` Site 安装 ERPNext 与 `rayher_crm`。ERPNext 提供通用主数据，`rayher_crm` 提供 Sales、Demo、Controlled Documents 和 Installed Tool 专用 DocType；Vue 作为同域登录后工作台调用 `/api/method/rayher_crm.api.v1.*`。

**Tech Stack:** Frappe v16、ERPNext v16、Python 3.14、MariaDB、Redis、Docker Compose、Vue 3、TypeScript、Vitest、pypdf/reportlab。

## Global Constraints

- 只实施 `docs/superpowers/specs/2026-07-20-rayher-crm-p0-p1-backend-design.md` 的 P0/P1。
- 本地入口固定为 `http://localhost:2223`，Site 固定为 `rayher.localhost`，App 固定为 `rayher_crm`。
- 镜像固定为 `frappe/erpnext:v16.28.0`；禁止使用 `latest` 或浮动 `v16`。
- 时区固定为 `Asia/Shanghai`；Dashboard 使用自然季度和人民币报表金额。
- 密码、Token、Cookie 和数据库凭据不得写入源码、文档、测试、日志或回复。
- 业务权限必须由服务端执行；前端隐藏按钮不构成授权。
- 主文件必须使用 Frappe private file；普通下载不得返回主文件永久 URL。
- 当前目录不是有效 Git 仓库，计划中的 Commit 步骤记录变更边界但不执行 Git 命令。

---

## File Structure

```text
backend/
├── Dockerfile                      # rayher_crm 自定义 ERPNext 镜像
├── compose.yaml                    # 本地完整服务拓扑
├── .dockerignore                   # 镜像构建排除项
├── README.md                       # 不含凭据的本地操作说明
├── scripts/
│   ├── wait-for-site.ps1           # 条件式等待 Site 就绪
│   ├── copy-admin-password.ps1     # 密码只进入剪贴板
│   └── verify-stack.ps1            # 容器、Site、队列、持久化检查
└── apps/rayher_crm/
    ├── pyproject.toml
    ├── hooks.py
    ├── modules.txt
    ├── patches.txt
    └── rayher_crm/
        ├── api/v1/                 # 统一 API、响应和错误边界
        ├── permissions/            # 行级权限与角色范围
        ├── setup/                  # Roles、Custom Fields、Workflow、种子命令
        ├── sales/doctype/          # Site、Opportunity、Stakeholder、Action、Change
        ├── demo/doctype/           # Request、Wafer、Execution、Test Run、Conclusion
        ├── documents/doctype/      # Document、Version、Access Request、Audit
        ├── installed_base/doctype/ # Installed Tool
        ├── services/               # 编码、汇率、状态机、水印、Dashboard、Excel
        └── tests/                  # 跨模块、权限和 API 测试
```

---

### Task 1: Docker Foundation and Frappe App Scaffold

**Files:**
- Create: `backend/Dockerfile`
- Create: `backend/compose.yaml`
- Create: `backend/.dockerignore`
- Create: `backend/README.md`
- Create: `backend/scripts/wait-for-site.ps1`
- Create: `backend/scripts/copy-admin-password.ps1`
- Create: `backend/apps/rayher_crm/**`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: Docker Engine、Compose、端口 2223。
- Produces: `rayher-crm:v16.28.0-local`、`rayher.localhost`、可安装的 `rayher_crm` App。

- [ ] **Step 1: Verify image and port prerequisites**

Run:

```powershell
docker manifest inspect frappe/erpnext:v16.28.0
Get-NetTCPConnection -LocalPort 2223 -State Listen -ErrorAction SilentlyContinue
```

Expected: 镜像 manifest 包含 `linux/amd64`；端口无监听记录。

- [ ] **Step 2: Generate the standard Frappe app scaffold**

Run a disposable container from the pinned image, execute `bench new-app rayher_crm --no-git`, copy only the generated app into `backend/apps/rayher_crm`, then remove the disposable container. App metadata is fixed to title `QIHENG Demo CRM`、publisher `QIHENG Demo`、email `person009@legacy.example.invalid`、license `MIT`。

Expected: `backend/apps/rayher_crm/pyproject.toml` and `backend/apps/rayher_crm/rayher_crm/hooks.py` exist.

- [ ] **Step 3: Write the Compose topology**

`backend/compose.yaml` must define `secrets-init`、`db`、`redis-cache`、`redis-queue`、`configurator`、`create-site`、`backend`、`frontend`、`websocket`、`queue-short`、`queue-long`、`scheduler`. The secret initializer writes random database and Administrator passwords into a named volume only when absent. The frontend publishes `2223:8080`.

- [ ] **Step 4: Build and start the foundation**

Run:

```powershell
docker compose -f backend/compose.yaml build
docker compose -f backend/compose.yaml up -d
```

Expected: `create-site` exits 0; all long-running services are running; `http://localhost:2223/api/method/ping` returns `pong`.

- [ ] **Step 5: Verify installed apps**

Run:

```powershell
docker compose -f backend/compose.yaml exec backend bench --site rayher.localhost list-apps
```

Expected: output contains `frappe`、`erpnext`、`rayher_crm`.

---

### Task 2: P0 Roles, Shared Master Data, and Immutable Codes

**Files:**
- Create: `backend/apps/rayher_crm/rayher_crm/setup/install.py`
- Create: `backend/apps/rayher_crm/rayher_crm/setup/custom_fields.py`
- Create: `backend/apps/rayher_crm/rayher_crm/services/codes.py`
- Create: `backend/apps/rayher_crm/rayher_crm/tests/test_p0_setup.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/hooks.py`

**Interfaces:**
- Produces: `make_code(prefix: str, date: date, digits: int = 5) -> str`；六个固定角色；Customer/Item Custom Fields。

- [ ] **Step 1: Write failing setup tests**

```python
def test_required_roles_exist():
    expected = {
        "CRM Administrator", "管理者权限", "Sales Manager",
        "Sales User", "FAE / Application Engineer", "Document Manager",
    }
    assert expected <= set(frappe.get_all("Role", pluck="name"))

def test_customer_code_cannot_change():
    customer = make_customer("QIHENG Demo-2026-001")
    customer.rayher_customer_code = "QIHENG Demo-2026-002"
    with pytest.raises(frappe.ValidationError):
        customer.save()
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `bench --site rayher.localhost run-tests --app rayher_crm --module rayher_crm.tests.test_p0_setup`

Expected: FAIL because roles, fields and validation hooks do not exist.

- [ ] **Step 3: Implement roles, fields, and code validation**

Install hooks create the six roles idempotently. Customer receives unique `rayher_customer_code` and Account Team table; Item receives Tool Model flags. `validate_customer_code_change` compares `get_doc_before_save()` and rejects changes after insert.

- [ ] **Step 4: Run tests and migrate**

Run: `bench --site rayher.localhost migrate && bench --site rayher.localhost run-tests --app rayher_crm --module rayher_crm.tests.test_p0_setup`

Expected: PASS.

---

### Task 3: Core Sales CRM DocTypes

**Files:**
- Create: `backend/apps/rayher_crm/rayher_crm/sales/doctype/crm_site/**`
- Create: `backend/apps/rayher_crm/rayher_crm/sales/doctype/crm_opportunity/**`
- Create: `backend/apps/rayher_crm/rayher_crm/sales/doctype/crm_opportunity_stakeholder/**`
- Create: `backend/apps/rayher_crm/rayher_crm/sales/doctype/crm_action/**`
- Create: `backend/apps/rayher_crm/rayher_crm/sales/doctype/crm_opportunity_change/**`
- Create: `backend/apps/rayher_crm/rayher_crm/tests/test_sales.py`

**Interfaces:**
- Produces: `CRM Site`、`CRM Opportunity`、`CRM Opportunity Stakeholder`、`CRM Action`、`CRM Opportunity Change`。

- [ ] **Step 1: Write failing model tests**

Tests assert Site code format and uniqueness, stakeholder many-to-many behavior, fixed Forecast Category enumeration, original/group amount calculation, stage history creation, and multiple open Actions per Opportunity.

- [ ] **Step 2: Confirm RED**

Run: `bench --site rayher.localhost run-tests --app rayher_crm --module rayher_crm.tests.test_sales`

Expected: FAIL because DocTypes do not exist.

- [ ] **Step 3: Implement minimal DocTypes and controllers**

`CRM Opportunity.validate()` calculates `reporting_amount_cny = amount * exchange_rate`, validates probability `0..100`, and writes history only when tracked values change. `CRM Opportunity Stakeholder` uses Links to Opportunity and Contact with a unique pair constraint.

- [ ] **Step 4: Verify GREEN**

Run migrate and the sales test module.

Expected: PASS with no duplicate Site or stakeholder association allowed.

---

### Task 4: Demo Request, Wafer, Execution, Test Run, and Conclusion

**Files:**
- Create: `backend/apps/rayher_crm/rayher_crm/demo/doctype/crm_demo_request/**`
- Create: `backend/apps/rayher_crm/rayher_crm/demo/doctype/crm_wafer_sample/**`
- Create: `backend/apps/rayher_crm/rayher_crm/demo/doctype/crm_demo_execution/**`
- Create: `backend/apps/rayher_crm/rayher_crm/demo/doctype/crm_execution_wafer/**`
- Create: `backend/apps/rayher_crm/rayher_crm/demo/doctype/crm_test_run/**`
- Create: `backend/apps/rayher_crm/rayher_crm/demo/doctype/crm_demo_conclusion/**`
- Create: `backend/apps/rayher_crm/rayher_crm/setup/workflows.py`
- Create: `backend/apps/rayher_crm/rayher_crm/tests/test_demo.py`

**Interfaces:**
- Produces: `transition_demo_request(name: str, action: str, comment: str | None) -> dict` and `transition_execution(name: str, target: str, reason: str | None) -> dict`.

- [ ] **Step 1: Write failing workflow tests**

Tests cover Sales submit、FAE return/confirm、Manager approve/reject、one Request to multiple Executions、Wafer reuse through association、Test Run requiring Execution and Wafer、On Hold reason、Conclusion customer confirmation gate.

- [ ] **Step 2: Confirm RED**

Run the Demo test module and verify missing DocTypes/workflows cause expected failures.

- [ ] **Step 3: Implement DocTypes and server-side transitions**

Transitions reject wrong roles and invalid source states. Manager approval creates the first Execution idempotently only when requested; later Executions use explicit creation. Test Run validates Capture/False Positive `0..100` and WPH non-negative.

- [ ] **Step 4: Verify GREEN**

Run migrate and Demo tests. Expected: all transition and relationship tests pass.

---

### Task 5: Controlled Documents, Private Files, and Watermarked Downloads

**Files:**
- Create: `backend/apps/rayher_crm/rayher_crm/documents/doctype/crm_controlled_document/**`
- Create: `backend/apps/rayher_crm/rayher_crm/documents/doctype/crm_document_version/**`
- Create: `backend/apps/rayher_crm/rayher_crm/documents/doctype/crm_document_access_request/**`
- Create: `backend/apps/rayher_crm/rayher_crm/documents/doctype/crm_document_download_audit/**`
- Create: `backend/apps/rayher_crm/rayher_crm/services/documents.py`
- Create: `backend/apps/rayher_crm/rayher_crm/services/watermark.py`
- Create: `backend/apps/rayher_crm/rayher_crm/tests/test_documents.py`

**Interfaces:**
- Produces: `release_version(version_name: str) -> dict`；`request_access(...) -> dict`；`download_watermarked(version_name: str) -> frappe.Response`。

- [ ] **Step 1: Write failing security tests**

Tests assert one Current Released version, automatic Superseded state, SHA-256 checksum, private file enforcement, Catalog Visibility separate from Content Access, Restricted double approval, no master URL in API, per-page watermark text, and Download Audit creation.

- [ ] **Step 2: Confirm RED**

Run the documents test module. Expected: FAIL because document services do not exist.

- [ ] **Step 3: Implement transactional release and access workflow**

Use database locking around release, require Owner → Reviewer → Document Manager, and clear the previous Current flag in the same transaction. Store original files with `is_private=1`.

- [ ] **Step 4: Implement PDF watermarking**

Generate a temporary personalized PDF in memory, overlay every page with user/employee code、timestamp、Document ID、version/revision、confidentiality and Download ID, stream it as an attachment, then create the audit record. Never save a public copy.

- [ ] **Step 5: Verify GREEN**

Run the documents tests and confirm unauthorized users receive `frappe.PermissionError` without file URLs.

---

### Task 6: Installed Tool MVP

**Files:**
- Create: `backend/apps/rayher_crm/rayher_crm/installed_base/doctype/crm_installed_tool/**`
- Create: `backend/apps/rayher_crm/rayher_crm/installed_base/doctype/crm_installed_tool_document/**`
- Create: `backend/apps/rayher_crm/rayher_crm/tests/test_installed_tool.py`

**Interfaces:**
- Produces: immutable `serial_number` and `INST-{serial}` naming; links to Customer、Site、Item、Opportunity、Contract and current Documents.

- [ ] **Step 1: Write failing identity and lifecycle tests**

Tests assert serial uniqueness/immutability, required Customer/Site/Tool Model, lifecycle date ordering, warranty calculation, software baseline, and only Current Released documents link as applicable.

- [ ] **Step 2: Confirm RED, implement, and verify GREEN**

Run the Installed Tool test module before and after implementation. Expected final result: PASS.

---

### Task 7: Permission Queries and API v1

**Files:**
- Create: `backend/apps/rayher_crm/rayher_crm/permissions/query.py`
- Create: `backend/apps/rayher_crm/rayher_crm/permissions/document.py`
- Create: `backend/apps/rayher_crm/rayher_crm/api/v1/response.py`
- Create: `backend/apps/rayher_crm/rayher_crm/api/v1/bootstrap.py`
- Create: `backend/apps/rayher_crm/rayher_crm/api/v1/sales.py`
- Create: `backend/apps/rayher_crm/rayher_crm/api/v1/demo.py`
- Create: `backend/apps/rayher_crm/rayher_crm/api/v1/documents.py`
- Create: `backend/apps/rayher_crm/rayher_crm/api/v1/installed_tools.py`
- Create: `backend/apps/rayher_crm/rayher_crm/api/v1/dashboard.py`
- Create: `backend/apps/rayher_crm/rayher_crm/tests/test_permissions.py`
- Create: `backend/apps/rayher_crm/rayher_crm/tests/test_api_contract.py`

**Interfaces:**
- Produces: `ok(data, meta=None, warnings=None)`；`fail(code, message, field_errors=None)`；all `/api/method/rayher_crm.api.v1.*` methods.

- [ ] **Step 1: Write failing role matrix and response tests**

Parameterize six roles against list/read/write/approve/download operations. Assert every success response has `data/meta/warnings`, every handled error has code/message/field_errors/request_id.

- [ ] **Step 2: Confirm RED**

Run permission and API contract modules. Expected: FAIL because query hooks and methods do not exist.

- [ ] **Step 3: Implement permissions and endpoints**

Management role is global read-only; Sales Manager is team-scoped; Sales User is owner/Account Team scoped; FAE is assignment scoped; Document Manager is document-domain scoped. Every write endpoint rechecks role, row scope and current workflow state.

- [ ] **Step 4: Verify GREEN**

Run the two modules. Expected: all role combinations and error shapes pass.

---

### Task 8: Development Seed and CUSTOMER06 Import

**Files:**
- Create: `backend/apps/rayher_crm/rayher_crm/setup/seed.py`
- Create: `backend/apps/rayher_crm/rayher_crm/setup/import_tsmc.py`
- Create: `backend/apps/rayher_crm/rayher_crm/tests/test_seed.py`
- Read: `C:/Users/PlanckSemicon/Downloads/CUSTOMER06_演示_Customer_360_2026-07-17.xlsx`

**Interfaces:**
- Produces: `seed_development_data() -> dict[str, int]` and `import_tsmc_workbook(path: str) -> dict[str, int]`.

- [ ] **Step 1: Write failing idempotency tests**

Run seed twice and assert the second run reports updates/skips without increasing unique record counts.

- [ ] **Step 2: Implement deterministic upserts**

Use fixed external IDs from existing Mock data and customer codes from the workbook. Mark all imported records `is_development_data=1`; never overwrite non-development records without an explicit matching external ID.

- [ ] **Step 3: Verify workbook mapping and idempotency**

Expected: Customer 360 relationships remain connected and repeated imports create zero duplicates.

---

### Task 9: Vue Frappe Adapter and P1 Page Integration

**Files:**
- Modify: `src/api/contracts.ts`
- Modify: `src/api/frappe-adapter.ts`
- Modify: `src/api/index.ts`
- Modify: `src/pages/OpportunityStrategyPage.vue`
- Modify: `src/pages/DemoWorkflowPage.vue`
- Modify: `src/pages/InstalledToolsPage.vue`
- Modify: `src/pages/DocumentCenterPage.vue`
- Create: `src/api/frappe-adapter.test.ts`
- Modify: `src/pages/seven-page-workspace.test.ts`

**Interfaces:**
- Consumes: API v1 endpoints from Task 7.
- Produces: all P0/P1 pages load real data in Frappe mode while tests can inject explicit test clients.

- [ ] **Step 1: Write failing adapter contract tests**

Tests assert endpoint names, GET/POST semantics, CSRF on writes, response unwrapping, error mapping, and that P1 pages no longer import `@/demo/operations-data`.

- [ ] **Step 2: Confirm RED**

Run: `pnpm vitest run src/api/frappe-adapter.test.ts src/pages/seven-page-workspace.test.ts`

Expected: FAIL because P1 adapter methods do not exist and pages still use direct demo imports.

- [ ] **Step 3: Implement minimal adapter and page loading states**

Extend `CrmApi` with opportunity strategy、Demo workflow、Installed Tool and document methods. Preserve request identity guards and permission/error states. Production Frappe build has no runtime Mock fallback.

- [ ] **Step 4: Verify GREEN**

Run focused tests, then `pnpm typecheck` and `pnpm build`.

---

### Task 10: Package Vue Assets into Frappe Desk

**Files:**
- Modify: `vite.config.ts`
- Modify: `backend/apps/rayher_crm/rayher_crm/hooks.py`
- Create: `backend/apps/rayher_crm/rayher_crm/public/crm/.gitkeep`
- Create: `backend/apps/rayher_crm/rayher_crm/rayher_crm/page/rayher_crm/rayher_crm.json`
- Create: `backend/apps/rayher_crm/rayher_crm/rayher_crm/page/rayher_crm/rayher_crm.js`

**Interfaces:**
- Produces: Frappe Desk route `/app/rayher-crm` mounting the Vue bundle; API remains same-origin.

- [ ] **Step 1: Add a production asset test**

Build with `VITE_API_ADAPTER=frappe` and assert generated asset paths are relative to `/assets/rayher_crm/crm/` and no development server URL is present.

- [ ] **Step 2: Copy the built bundle and run Frappe asset build**

Run the project build, copy generated files into the app public directory using the repository build script, rebuild the custom image, and execute `bench build --app rayher_crm`.

- [ ] **Step 3: Verify the Desk page**

Expected: authenticated users with a CRM role can open `/app/rayher-crm`; users without a CRM role receive a server-side permission error.

---

### Task 11: Full Verification and Local Handoff

**Files:**
- Create: `backend/scripts/verify-stack.ps1`
- Modify: `backend/README.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: complete Docker stack, backend tests, frontend build.
- Produces: repeatable verification report and local operating instructions without secrets.

- [ ] **Step 1: Run all backend tests**

Run: `docker compose -f backend/compose.yaml exec backend bench --site rayher.localhost run-tests --app rayher_crm`

Expected: zero failures.

- [ ] **Step 2: Run all frontend checks**

Run: `pnpm test; pnpm typecheck; pnpm build`

Expected: zero failures and successful production build.

- [ ] **Step 3: Run HTTP and browser smoke tests**

Verify login、Dashboard、Customer、Opportunity、Demo、Wafer/Test Run、Installed Tool、Document catalog、Access Request and watermarked download at `http://localhost:2223` with the allowed role matrix. Confirm browser console has no errors.

- [ ] **Step 4: Verify persistence**

Create a uniquely identified development record and private test file, restart the Compose project without deleting volumes, then assert both still exist and the private file is not accessible by direct public URL.

- [ ] **Step 5: Copy the local Administrator password to clipboard**

Run `backend/scripts/copy-admin-password.ps1`; the script must write only a success message and never print the password.

- [ ] **Step 6: Record final state**

Document container names、start/stop/rebuild/migrate/test commands、port 2223 and data volume names. Do not include credentials.
