# CRM Stage 5B Account, Contact, and Lead Vertical Slice Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans and superpowers:test-driven-development task-by-task.

**Goal:** 在独立 `rayher-crm.localhost` 数据库中交付 Account、Contact、Lead 的首个真实 Frappe 垂直切片，覆盖服务端 ID、分页、SQL 行级范围、乐观锁、联系人软删除/合并和 Lead 原子转换，并保持前端默认 Mock，直到真实 adapter 与 E2E Gate 完成。

**Architecture:** 复用 ERPNext v15 标准 `Customer`、`Contact`、`Address`、`Lead` DocType；Site 映射 Address + Customer Dynamic Link；Opportunity 使用 `rayher_crm` 自有轻量 `CRM Opportunity`，避免标准 Opportunity 强制 Company 后生成会计/仓储主数据。通过幂等 Custom Field 安装器补充 CRM 契约字段；API DTO 不直接暴露 Frappe 文档。所有身份取 `frappe.session.user`，列表范围在 SQL 条件层实施，写服务在单请求数据库事务中用行锁校验 `modified`。Account/Site 名称在关联 DTO 中通过 join 派生，禁止复制级联名称。

**Tech Stack:** Frappe 15.116.1、ERPNext 15.118.3、MariaDB 10.6、Python 3.11、FrappeTestCase、Docker Compose。

**Execution Status:** In progress.

## Frozen decisions and limits

- Account 映射标准 `Customer`；Contact/Lead 映射标准 DocType；Site 映射标准 Address；Opportunity 使用已批准的轻量 `CRM Opportunity`，不创建 ERPNext Company 或 ERP 会计/仓储数据。
- Manager 为全局范围；`teamOwners` 在 Stage 5B 明确废弃，不作为隐藏授权输入。Sales 只看 `custom_crm_owner == frappe.session.user`；Engineer 只看显式 `CRM Account Engineer Assignment`。
- 客户端 `owner`/`opportunityOwner` 只作为兼容输入读取但不得决定服务端 Owner；创建默认当前用户，Manager 可通过单独受控字段指派拥有 CRM Sales/Manager 角色的 User，Sales 只能指派自己。
- 所有 list 的 `pageSize` 范围为 1..200，返回 `PageData` 和准确 `meta.total`；GET/list 不写数据库。
- Contact 删除和合并只软删除；Link 使用 null，不写空字符串。尚未落地的 Booking/Demo 等下游引用在其切片中继续补齐，不提前勾选完整 B4。
- Lead 转换同事务生成/复用 Customer、Contact、Opportunity 并标记 Lead Converted；任何一步失败整体回滚，重复提交返回已生成的同一组 ID。
- Stage 5B 不实现文件、通知、Booking/Demo/Evaluation，也不切换 `VITE_API_ADAPTER`。

---

### Task 1: Freeze schema and endpoint contracts

**Files:**
- Create: `backend/apps/rayher_crm/rayher_crm/setup/custom_fields.py`
- Create: `backend/apps/rayher_crm/rayher_crm/rayher_crm/doctype/crm_account_engineer_assignment/*`
- Modify: `backend/apps/rayher_crm/rayher_crm/setup/install.py`
- Create: `backend/apps/rayher_crm/rayher_crm/tests/test_stage5b_schema.py`
- Modify: `backend/tests/app-package-contract.ps1`

- [x] Write RED tests for required standard DocTypes, exact CRM custom fields, Link targets, field types, unique assignment pairs and idempotent installation.
- [x] Add only fields required by current Account/Contact/Lead DTOs, using Select options from the frozen frontend unions.
- [x] Add the explicit Account↔Engineer assignment DocType and role permissions; do not create demo rows or users.
- [x] Run migrate twice and prove schema installation idempotent.

### Task 2: Implement shared API validation, pagination, serialization, and optimistic locking

**Files:**
- Create: `backend/apps/rayher_crm/rayher_crm/services/common.py`
- Create: `backend/apps/rayher_crm/rayher_crm/services/concurrency.py`
- Create: `backend/apps/rayher_crm/rayher_crm/api/v1/errors.py`
- Create: `backend/apps/rayher_crm/rayher_crm/tests/test_service_foundation.py`

- [x] Write RED tests for page/pageSize normalization, cap 200, ISO serialization, server-generated IDs, and frozen error codes.
- [x] Lock target row with `SELECT ... FOR UPDATE`, compare the canonical `modified` value inside the same transaction and return `VERSION_CONFLICT` on mismatch.
- [x] Ensure validation/permission/not-found/version errors use the frozen CRM error envelope and do not leak tracebacks or SQL.
- [x] Prove read helpers execute no INSERT/UPDATE/DELETE and preserve `modified`.

### Task 3: Implement SQL-layer scope for Customer, Contact, Lead, and CRM Opportunity

**Files:**
- Create: `backend/apps/rayher_crm/rayher_crm/permissions/scope.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/hooks.py`
- Create: `backend/apps/rayher_crm/rayher_crm/tests/test_scope.py`

- [x] Register `permission_query_conditions` and `has_permission` hooks for all four standard DocTypes.
- [x] Test Manager global, Sales owner-only, Engineer assigned-account-only, Guest denial, and list/detail equivalence using real SQL queries.
- [x] Test that client owner fields cannot widen scope and that ambiguous/no CRM roles fail closed.
- [x] Record the `teamOwners` removal decision in the audit and contract log; do not silently retain a dead authorization field.

### Task 4: Implement Account and Contact APIs

**Files:**
- Create: `backend/apps/rayher_crm/rayher_crm/services/accounts.py`
- Create: `backend/apps/rayher_crm/rayher_crm/services/contacts.py`
- Create: `backend/apps/rayher_crm/rayher_crm/api/v1/accounts.py`
- Create: `backend/apps/rayher_crm/rayher_crm/api/v1/contacts.py`
- Create: `backend/apps/rayher_crm/rayher_crm/tests/test_account_contact_api.py`

- [x] Implement list/create/update/get Account with server IDs, SQL scope, pagination/total, owner enforcement and `expectedModified` conflict tests.
- [x] Implement list/get/create/update Contact with Customer Link validation, hierarchy cycle rejection and derived account/site labels.
- [x] Implement Contact merge/delete in one transaction, soft-delete duplicate/history, null Link discipline and injected-failure rollback tests.
- [x] Keep Account rename free of copied `accountName` cascades by deriving names through joins; verify GET/list are read-only.

### Task 5: Implement Lead APIs and atomic conversion

**Files:**
- Create: `backend/apps/rayher_crm/rayher_crm/services/leads.py`
- Create: `backend/apps/rayher_crm/rayher_crm/api/v1/leads.py`
- Create: `backend/apps/rayher_crm/rayher_crm/tests/test_lead_api.py`

- [x] Implement list/get/create/update Lead with frozen enums, server owner, pagination and optimistic locking.
- [x] Implement idempotent Lead conversion that reuses or creates Customer/Contact and creates one lightweight `CRM Opportunity` within one transaction.
- [x] Validate positive DECIMAL(20,2) opportunity amount, currency and Shanghai date-only close date; never trust `opportunityOwner`.
- [x] Inject a failure after each conversion sub-write and prove complete rollback; repeat conversion returns the original IDs without duplicate rows.

### Task 6: Build, migrate, and verify the backend vertical slice

**Files:**
- Modify only files above if real build/test evidence exposes a defect.

- [x] Re-run Compose/app package contracts and verified ZIP generation.
- [x] Rebuild `rayher-crm-stage1:v15-local`, migrate the existing independent site twice, and inspect standard/custom schema.
- [x] Run all `rayher_crm` tests and require real test counts plus zero failures.
- [x] Exercise authenticated HTTP list/create/update/conflict/scope/convert paths without printing credentials.
- [x] Verify container health, old-stack isolation, DB/Redis non-exposure and controlled restart persistence.

### Task 7: Preserve frontend boundary and prepare Stage 5C

**Files:**
- Update: `docs/CRM-持续执行审计日志-2026-08-04.md`
- Update: `docs/CRM-后端数据库对接契约-2026-08-04.md` only for gates with complete evidence.
- Update: this plan
- Create next plan only after Stage 5B evidence identifies the next smallest vertical slice.

- [x] Run frontend typecheck, complete tests with a resource-stable worker limit, and production build.
- [x] Keep default adapter Mock and keep `createFrappeApi()` No-Go until its own HTTP/error/CSRF/E2E slice.
- [x] Record every schema/security/transaction choice and every failed attempt without credentials.
- [x] Mirror the audit log to Desktop and continue autonomously.

## Stage 5B acceptance Gate

1. Standard Customer/Contact/Lead extensions, lightweight `CRM Opportunity`, and assignment DocType are installed idempotently in the new CRM database without creating ERP Company/accounting/warehouse data.
2. Manager/Sales/Engineer SQL-layer scope is consistent for list/detail and client role/owner input cannot widen access.
3. Account/Contact/Lead APIs use stable envelopes, server IDs, page cap/total and real optimistic-lock conflicts.
4. Contact merge/delete and Lead conversion have injected-failure rollback tests; no empty Link or hard-deleted contact history.
5. Frappe tests, authenticated HTTP checks, repeated migrate, restart persistence and frontend regression all pass.
6. Old Docker project/volumes remain untouched; frontend remains Mock by default.
