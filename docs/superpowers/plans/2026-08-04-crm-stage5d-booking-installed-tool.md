# CRM Stage 5D Booking and Installed Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans and superpowers:test-driven-development task-by-task.

**Goal:** 在独立 Frappe CRM 数据库中实现 Booking CRUD、Booking 到 Installed Tool 的原子转换、Installed Tool 范围读取与更新。

**Architecture:** Booking 与 Installed Tool 均使用 `rayher_crm` 自有 DocType，不创建 Sales Order、Delivery Note、Asset、Company、仓储或会计记录。Booking 关联标准 Customer/Contact、自有 CRM Opportunity；Installed Tool 关联 Customer/Address/Booking/Opportunity。所有显示名读取时派生，所有 ID 由服务端生成，更新使用行锁与 `expectedModified`。

**Tech Stack:** Frappe Framework 15.116.1、ERPNext 15.118.3、MariaDB 10.6、Python 3.11、Docker Compose、FrappeTestCase、PowerShell HTTP acceptance。

## Global Constraints

- 前端 adapter 保持 Mock；本阶段只增加后端/API，不宣布 Frappe 对接完成。
- Booking 金额在数据库使用 Currency/DECIMAL 语义并保存 `currency`；冻结前端输入尚无 currency，因此本阶段服务端固定为 `CNY`，不得跨币种生成 pipeline 合计。
- `source=Opportunity` 必须关联同 Account 的 Won Opportunity；`source=Upsell` 必须不带 Opportunity。
- `Completed` 只能由转换事务产生；已转换 Booking 不可再编辑，重复转换必须幂等拒绝。
- 转换只生成 `CRM Installed Tool`，不生成 ERPNext Asset、Item、Sales Order、Delivery Note、Serial No 或 Company 数据。
- 转换在同一 savepoint/事务中：锁 Booking → 校验 Site/Engineer/serial → 创建 Tool → 更新 Booking；任一步失败全部回滚。
- Installed Tool Engineer 只能查看/更新分配给自己的记录且不能自助改派；Manager 可改派，Sales 仅通过转换创建、按 Account scope 读取。
- 所有生产行为先观察真实 RED，再最小实现并 GREEN。

---

### Task 1: Add Booking and Installed Tool schema and permission scope

**Files:**
- Create: `backend/apps/rayher_crm/rayher_crm/rayher_crm/doctype/crm_booking/*`
- Create: `backend/apps/rayher_crm/rayher_crm/rayher_crm/doctype/crm_installed_tool/*`
- Modify: `backend/apps/rayher_crm/rayher_crm/permissions/scope.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/hooks.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/tests/test_stage5b_schema.py`
- Modify: `backend/tests/app-package-contract.ps1`

- [x] Write RED schema tests for exact fields, server naming, unique serial/source Booking, no Company/ERP transaction links, and role permissions.
- [x] Write RED scope tests for Manager global, Sales Account/owner, Engineer assigned Account/installed-tool ownership, and Guest none.
- [x] Implement only schema, query conditions, has-permission hooks and explicit DocPerm; migrate twice.
- [x] Re-run schema/scope tests and assert no new Company, Asset, Sales Order or Delivery Note rows.

### Task 2: Implement Booking create/update/read services

**Files:**
- Create: `backend/apps/rayher_crm/rayher_crm/services/bookings.py`
- Create: `backend/apps/rayher_crm/rayher_crm/api/v1/bookings.py`
- Create: `backend/apps/rayher_crm/rayher_crm/tests/test_booking_api.py`

- [x] Write RED tests for server ID, Account/Contact validation, positive integer quantity, non-negative two-decimal amount, real DDL, owner anti-forgery and status/source enums.
- [x] Write RED tests for Won/same-Account Opportunity source, Upsell no-source rule, one live Booking per Opportunity, derived names and GET/list read-only behavior.
- [x] Write RED tests for row-locked update, stale 409, `Completed` rejection and post-conversion lock.
- [x] Implement scoped create/get/list/update and stable API envelopes; all create/update payload fields match `UpsertBookingInput`.

### Task 3: Implement atomic conversion and Installed Tool update

**Files:**
- Create: `backend/apps/rayher_crm/rayher_crm/services/installed_tools.py`
- Create: `backend/apps/rayher_crm/rayher_crm/api/v1/installed_tools.py`
- Create: `backend/apps/rayher_crm/rayher_crm/tests/test_installed_tool_api.py`

- [x] Write RED tests for Confirmed-only conversion, Site↔Account, active CRM Engineer, case-insensitive unique serial and server-generated Tool ID.
- [x] Write RED failure-injection tests after Tool insert and after Booking update; assert Booking/Tool both roll back.
- [x] Write RED tests for Manager/Sales/Engineer list scope, Engineer update/self-reassignment denial, Manager reassignment and CAS conflict.
- [x] Implement conversion under one savepoint and row lock; append server actor/time history without client actor injection.
- [x] Implement scoped list/update endpoints and derived Account/Site names; never create ERP business documents.

### Task 4: Build and close Stage 5D

**Files:**
- Create: `backend/tests/http-stage5d-booking-installed-tool-acceptance.ps1`
- Modify: `docs/CRM-持续执行审计日志-2026-08-04.md`
- Modify: this plan

- [x] Rebuild verified App ZIP/image, migrate twice, and run full `rayher_crm` App tests with textual `OK` verification.
- [x] Run authenticated HTTP Booking create/update/409/source validation/convert/repeat-convert/Installed Tool scope/update/restart-persistence; clean exact test rows in `finally`.
- [x] Re-run package/Compose contracts and frontend typecheck/489 tests/build; keep default adapter Mock.
- [x] Verify only `127.0.0.1:2224` is published, DB/Redis internal, old Docker project/volumes untouched, and ERP business-document counts unchanged.
- [x] Record every choice/failure/fix/result in repo audit and synchronize Desktop mirror with SHA-256 equality.

## Stage 5D Acceptance Gate

1. Booking and Installed Tool persist in independent CRM DocTypes and do not create ERP business records.
2. Account/Contact/Site/Opportunity/User links are server-validated and list/detail scopes are identical.
3. IDs are server-generated, Sales owner cannot be forged, all updates are CAS-protected and reads are side-effect free.
4. Booking conversion is one transaction, Confirmed-only, duplicate-safe and fully rolls back at injected failure points.
5. Engineer ownership limits Installed Tool visibility/update; Engineer cannot self-reassign.
6. Full Frappe, authenticated HTTP, repeated migrate, restart persistence and frontend regression are green while frontend remains Mock.
