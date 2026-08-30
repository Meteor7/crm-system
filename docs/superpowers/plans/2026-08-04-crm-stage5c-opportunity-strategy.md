# CRM Stage 5C Opportunity Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在独立 Frappe CRM 数据库中完成 `CRM Opportunity` 策略主记录、Stakeholder、Action 与不可变历史的真实后端/API 垂直切片。

**Architecture:** 延续已批准的轻量 `CRM Opportunity`，不使用 ERPNext 标准 Opportunity/Company。Account 复用 Customer、Site 复用 Address、Contact 复用标准 Contact；Opportunity 关系使用 `rayher_crm` 自有 DocType，DTO 通过 join 派生 Account/Site/Contact 显示名。所有写入从 `frappe.session.user` 解析身份，Sales owner 不可伪造，更新使用行锁 + `expectedModified`，关系删除为软归档，历史只追加。

**Tech Stack:** Frappe Framework 15.116.1、ERPNext 15.118.3、MariaDB 10.6、Python 3.11 runtime、Docker Compose、FrappeTestCase、PowerShell HTTP acceptance。

## Global Constraints

- 不创建 ERPNext Company，不触发会计、仓储、HRMS 或 OCR 数据与服务。
- 不创建分支、不 commit、不 stash、不 reset；保留当前脏工作树和用户改动。
- 默认前端 adapter 保持 Mock；本阶段只增加后端与 HTTP 验收，不宣布 Frappe adapter 已接通。
- Create 不接受客户端 ID；Update 必须要求带时区 `expectedModified` 并在 `SELECT ... FOR UPDATE` 后比较。
- 金额使用正数 DECIMAL(20,2) 语义；币种必须存在；日期使用真实 `YYYY-MM-DD`；timestamp 输出 UTC ISO。
- Account/Site/Contact Link 必须属于同一 Account；列表与详情必须复用相同 SQL scope。
- `OpportunityDto` 与 `StrategyOpportunityDto` 的阶段统一为 `需求发现/技术确认/Demo验证/预算审批/报价/采购流程/Won/Lost`；不保留第二套冲突状态源。
- Stakeholder/Action 删除只设置 archived，不硬删历史；历史记录只追加，不提供更新/删除 API。
- 每个生产行为先写真实失败测试并观察 RED，再做最小实现和 GREEN。

---

### Task 1: Normalize CRM Opportunity schema and immutable relations

**Files:**
- Modify: `backend/apps/rayher_crm/rayher_crm/rayher_crm/doctype/crm_opportunity/crm_opportunity.json`
- Create: `backend/apps/rayher_crm/rayher_crm/rayher_crm/doctype/crm_opportunity_stakeholder/__init__.py`
- Create: `backend/apps/rayher_crm/rayher_crm/rayher_crm/doctype/crm_opportunity_stakeholder/crm_opportunity_stakeholder.py`
- Create: `backend/apps/rayher_crm/rayher_crm/rayher_crm/doctype/crm_opportunity_stakeholder/crm_opportunity_stakeholder.json`
- Create: `backend/apps/rayher_crm/rayher_crm/rayher_crm/doctype/crm_opportunity_action/__init__.py`
- Create: `backend/apps/rayher_crm/rayher_crm/rayher_crm/doctype/crm_opportunity_action/crm_opportunity_action.py`
- Create: `backend/apps/rayher_crm/rayher_crm/rayher_crm/doctype/crm_opportunity_action/crm_opportunity_action.json`
- Create: `backend/apps/rayher_crm/rayher_crm/rayher_crm/doctype/crm_opportunity_history/__init__.py`
- Create: `backend/apps/rayher_crm/rayher_crm/rayher_crm/doctype/crm_opportunity_history/crm_opportunity_history.py`
- Create: `backend/apps/rayher_crm/rayher_crm/rayher_crm/doctype/crm_opportunity_history/crm_opportunity_history.json`
- Modify: `backend/apps/rayher_crm/rayher_crm/tests/test_stage5b_schema.py`
- Modify: `backend/tests/app-package-contract.ps1`

**Interfaces:**
- Consumes: existing `CRM Opportunity.account`, `.site`, `.source_lead`, server naming and CRM roles.
- Produces: one canonical Opportunity stage field plus standalone relation DocTypes keyed by `opportunity`.

- [x] Write schema tests asserting manual Opportunity permits empty `source_lead`, `stage` has the exact eight values, and fields include forecast/probability/score/sale type/sub-region/original amount/dates/strategy text and JSON list fields.
- [x] Write schema tests asserting Stakeholder links Opportunity+Contact, Action links Opportunity+User, History links Opportunity and stores server actor/at/field/from/to; relation DocTypes use server hash names and archived flags where applicable.
- [x] Run `bench --site rayher-crm.localhost run-tests --module rayher_crm.tests.test_stage5b_schema` and require a feature-missing failure.
- [x] Implement only the tested DocType fields and role permissions; migrate the same independent site twice.
- [x] Re-run the schema module and require all assertions GREEN; assert no Company row was created by migration.

### Task 2: Implement scoped Opportunity list/create/update services

**Files:**
- Create: `backend/apps/rayher_crm/rayher_crm/services/opportunities.py`
- Create: `backend/apps/rayher_crm/rayher_crm/api/v1/opportunities.py`
- Create: `backend/apps/rayher_crm/rayher_crm/tests/test_opportunity_api.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/services/leads.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/services/accounts.py`
- Modify: `backend/tests/app-package-contract.ps1`

**Interfaces:**
- Produces: `list_strategy_opportunities()`, `create_strategy_opportunity(payload)`, `update_strategy_opportunity(id, payload, expected_modified)` and stable API envelopes.
- DTO fields exactly match `StrategyOpportunityDto`; account/site names are joined at read time, list-valued strategy fields serialize as arrays, and `modified` is canonical UTC ISO.

- [x] Write RED tests for create/list/update with server ID, owner anti-forgery, Site↔Account mismatch, positive two-decimal amount, valid currency/date, integer probability/score 0..100, and exact stage/forecast enums.
- [x] Write RED tests proving Sales sees owned rows, Engineer sees assigned Account rows, Manager sees all rows, and list/detail use the same permission condition.
- [x] Write RED tests proving stale `expectedModified` returns `VERSION_CONFLICT`, successful update appends field-diff History rows with the session actor, and GET/list do not write.
- [x] Implement SQL-scoped list, serializer joins, create validation and row-locked update; never trust Sales `owner`, and never copy Account/Site display names into Opportunity.
- [x] Update Lead conversion to populate canonical strategy defaults (`需求发现`, `Pipeline`, score/probability 20, New Equipment, Account region, original amount) and one Lead Conversion history row.
- [x] Update Account 360 to return scoped Opportunity summaries derived from the same records.
- [x] Run the Opportunity, Lead, scope and Account 360 modules; require zero failures.

### Task 3: Implement Stakeholder and Action APIs with soft history

**Files:**
- Modify: `backend/apps/rayher_crm/rayher_crm/services/opportunities.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/api/v1/opportunities.py`
- Create: `backend/apps/rayher_crm/rayher_crm/tests/test_opportunity_relations.py`

**Interfaces:**
- Produces: create/update/delete methods matching `CrmApi` relation signatures; delete responses remain `{id}` while the database row is archived.
- Stakeholder DTO derives Contact name/title; Action owner resolves to a stable User ID and status is only `Open` or `Done`.

- [x] Write RED tests for Contact↔Opportunity Account match, active Contact requirement, duplicate live relation rejection, server-generated relation IDs and Sales scope.
- [x] Write RED tests for Action required title/real due date/status enum, owner anti-forgery and row-locked update.
- [x] Write RED tests proving both delete methods preserve rows with `archived=1`, hide them from DTOs, and append immutable History with session actor.
- [x] Implement relation services using the parent Opportunity permission check; revive is not implicit, and archived IDs cannot be updated.
- [x] Run relation tests and Opportunity regression; require zero failures and no hard-deleted relation rows.

### Task 4: Build, HTTP-verify, and close Stage 5C

**Files:**
- Create: `backend/tests/http-stage5c-opportunity-acceptance.ps1`
- Modify: `docs/CRM-持续执行审计日志-2026-08-04.md`
- Modify: this plan

**Interfaces:**
- HTTP methods live under `/api/method/rayher_crm.api.v1.opportunities.*` and use the existing `{data,meta,warnings,error}` envelope.

- [x] Extend the protected-source verified ZIP contract and rebuild `rayher-crm-stage1:v15-local`; run migrate twice.
- [x] Run `bench --site rayher-crm.localhost run-tests --app rayher_crm` and record exact pass count.
- [x] Run authenticated HTTP create/list/update/stale-409/foreign-scope-403/stakeholder/action/soft-delete checks with a temporary Sales user; construct non-ASCII values code-page-independently and clean exact test rows in `finally`.
- [x] Run `pnpm.cmd typecheck`, `pnpm.cmd test --maxWorkers=2`, and `pnpm.cmd build`; default adapter must remain Mock.
- [x] Restart the independent CRM services, verify health/persistence, confirm only `127.0.0.1:2224` is published and DB/Redis remain internal.
- [x] Record all choices, RED failures, fixes and evidence in the audit log; mirror it to Desktop with SHA-256 equality.

## Stage 5C Acceptance Gate

1. One canonical lightweight `CRM Opportunity` supports Lead conversion and manual strategy creation without ERP Company.
2. Account/Site/Contact relationships are server-validated; Manager/Sales/Engineer scope is identical for list/detail/relations.
3. Create IDs are server-generated, Sales owner forgery is rejected or overwritten, updates are CAS-protected, and reads are side-effect free.
4. Stakeholder/Action removal is soft, History is immutable, and client actor/time values cannot be injected.
5. Real Frappe tests, authenticated HTTP, repeated migrate, restart persistence and frontend regression all pass.
6. Frontend remains Mock and old Docker project/volumes remain untouched.
