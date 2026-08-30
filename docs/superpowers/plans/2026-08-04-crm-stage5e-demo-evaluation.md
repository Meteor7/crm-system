# CRM Stage 5E Demo Request and Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans, superpowers:test-driven-development and superpowers:systematic-debugging task-by-task.

**Goal:** 在独立 Frappe CRM 数据库中实现 Demo Request、角色状态机、Comment、Evaluation 与 Test Run 的真实持久化垂直切片。

**Architecture:** 使用 `rayher_crm` 自有 `CRM Demo Request`、`CRM Demo Request History`、`CRM Demo Comment`、`CRM Evaluation`、`CRM Test Run`。Demo 表单 canonical 数据保存为服务端校验后的 JSON，同时把 Account/Contact/Opportunity/Owner/状态等查询字段结构化。Manager approve 在一个事务中生成唯一 Evaluation 并更新 Request；文件 Artifact、PDF 发布与通知推迟到 Stage 5F。

**Tech Stack:** Frappe Framework 15.116.1、ERPNext 15.118.3、MariaDB 10.6、Python 3.11、Docker Compose、FrappeTestCase、PowerShell HTTP acceptance。

## Global Constraints

- 不创建 ERP Project、Task、Quality Inspection、Company、Asset 或库存/会计单据。
- 前端 adapter 保持 Mock；本阶段不接入文件字节、报告 PDF 或客户端通知 Proxy。
- Demo Request ID `CRM-DR-{#####}`、Evaluation `CRM-EVAL-{#####}`、Test Run `CRM-RUN-{#####}` 均由服务端生成；History/Comment 使用 hash。
- 身份只取 `frappe.session.user`；Sales owner/createdBy、Engineer owner、Manager approvedBy 不接受客户端伪造。
- Sales 仅写自己的 Draft/Returned/Rejected Request；Engineer 仅审查分配给自己的 Request/Evaluation；Manager 全局。
- 状态机严格匹配冻结 `DemoRequestCommand`；非法角色或非法起始状态先拒绝，不产生部分写入。
- Manager approve 在同一 savepoint 内：锁 Request → 校验 → 创建 Evaluation → 更新 Request → 写 History；重复 approve 返回 `EVALUATION_EXISTS`，注入失败整体回滚。
- GET/List/Workflow/Comment list 均只读；FormData 的 contactPerson 显示文本读取时从 Contact 派生，不作为外键权威。
- Evaluation 状态按冻结顺序转换；Test Run 独立 server ID，指标必须全空或全填，汇总 wafer 数服务端计算。
- Artifact/report readiness 相关字段先保留 canonical 默认值；实际文件、版本锁、发布 Gate 在 Stage 5F 完成前不得宣称可发布报告。

---

### Task 1: Add Demo/Evaluation schema, scope and immutable history

- [x] Write RED schema tests for exact links/options/server naming, standalone Test Run IDs, immutable History and soft-safe Comment.
- [x] Write RED SQL scope tests for Manager/Sales/Engineer/Guest and list/detail parity across Demo Request and Evaluation.
- [x] Implement five DocTypes, explicit DocPerm, permission query conditions/has-permission hooks and lock whitelist; migrate twice.
- [x] Assert schema/migrate creates no ERP Project/Task/Quality Inspection/business rows.

### Task 2: Implement Demo Request create/update/list and Comment APIs

- [x] Write RED tests for Account/active Contact/Opportunity same-account links, FormData required fields, real dates, Sales/Engineer stable owner IDs and server createdBy/time.
- [x] Write RED tests for Draft/create-and-submit, editable-state restriction, CAS conflict, server-derived Contact display, exact pagination and side-effect-free reads.
- [x] Write RED tests for scoped Comment list/add, server author/role/time, empty body rejection and mentioned User ID validation.
- [x] Implement services and `/api/v1/demo_requests.py` endpoints with stable envelopes.

### Task 3: Implement role state machine and atomic Evaluation creation

- [x] Write RED transition matrix for submit/cancel/engineer_return/engineer_approve/manager_reject/manager_approve and role denial.
- [x] Write RED tests that Engineer cannot self-reassign, Manager can assign active CRM Engineer, and History actor/time are server-owned.
- [x] Write RED duplicate approve and injected-failure tests proving Evaluation/Request/History all roll back.
- [x] Implement row-locked transitions and atomic Evaluation creation; no notification/file side effects yet.

### Task 4: Implement Evaluation/Test Run services and workflow projection

- [x] Write RED tests for Evaluation scoped list, strict forward transition graph, CAS, acceptance derivation and report lock boundary.
- [x] Write RED tests for Test Run stage gate, real date, positive integer wafers, all-or-none metrics, ranges, summary, server ID and duplicate-safe wafer total.
- [x] Implement Test Run create and deadline update using row locks; update Request tracking in the same transaction.
- [x] Implement read-only DemoWorkflow projection and Comment ordering without GET writes.

### Task 5: Build and close Stage 5E

- [x] Rebuild verified App ZIP/image, migrate twice and require full App textual `OK`.
- [x] Run authenticated Sales/Engineer/Manager HTTP state-machine, Evaluation/Test Run, scope, 409, rollback boundary and restart-persistence checks; exact cleanup in `finally`.
- [x] Re-run package/Compose contracts and frontend typecheck/489 tests/build; default adapter remains Mock.
- [x] Verify health/ports, no ERP business rows, no temp identities, old Docker project/volumes untouched.
- [x] Record every choice/failure/fix/result in repo audit and mirror Desktop copy with SHA-256 equality.

## Stage 5E Acceptance Gate

1. Demo Request/Comment/Evaluation/Test Run use server IDs, stable User IDs and independent CRM DocTypes.
2. SQL list/detail scope and command role gates match Manager/Sales/Engineer contracts.
3. Request updates and Evaluation updates use row-lock CAS; reads do not write.
4. Manager approval is atomic, one Evaluation per Request, and injected failures fully roll back.
5. Test Run metrics/date/count/state rules are server enforced; report publishing remains explicitly unavailable until Stage 5F.
6. Full Frappe, authenticated HTTP, repeated migrate, restart persistence and frontend regression pass while frontend stays Mock.
