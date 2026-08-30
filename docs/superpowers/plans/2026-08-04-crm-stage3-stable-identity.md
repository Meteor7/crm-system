# CRM Stage 3 Stable Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 完成契约 A3 的前端/Mock 身份改造：内部 Owner、Actor、Approver、CreatedBy、PreparedBy、UploadedBy 统一存 Frappe User `name`（email），显示名只用于 UI；短身份别名只用于 Mock 切换；产出可审计迁移映射表。

**Architecture:** `BootstrapDto.user.id` 与所有内部人员引用共享同一 `UserId` 空间。`src/demo/personnel.ts` 模拟服务端人员目录，按 User ID 校验角色并提供纯展示解析；`src/demo/identity-migration.ts` 仅承担旧 seed/导入数据的一次性归一，不参与权限判断。客户联系人、外部审批人和组织责任主体不得进入 User ID 空间，使用原有业务 label 或显式外部 label。

**Tech Stack:** Vue 3、TypeScript、Pinia、Vitest、Mock repositories；未来后端目标为 Frappe User/Employee Link 与 `frappe.session.user`。

**Execution Status:** 2026-08-04 完成；`pnpm.cmd typecheck`、76/76 测试文件、489/489 测试、`pnpm.cmd build` 与范围 `git diff --check` 全部通过。

## Global Constraints

- 权威契约为 `docs/CRM-后端数据库对接契约-2026-08-04.md`，路线图为 `docs/superpowers/specs/2026-08-04-crm-backend-delivery-roadmap-design.md`。
- 不信任客户端提交的显示名、角色、Owner、Actor 或审批人；真实后端阶段必须由 `frappe.session.user` 覆盖审计身份。
- `PersonnelIdentity.id` 使用 Frappe User `name`；新增 `demoIdentityId` 仅供 Mock 身份切换，不得写入业务记录或通知收件人。
- 旧姓名 seed 只能通过受控迁移映射进入 repository；未知、重复、角色冲突值必须失败，不得静默保留为内部人员引用。
- UI 必须显示人员姓名而不是 email；筛选值和提交值仍是稳定 ID。
- 不把客户联系人、`Customer QE`、部门名或流程状态文案强制映射为 User；这类值必须保持为外部/组织 label，并在数据字典中登记。
- 不引入依赖，不改无关状态机；不 reset、stash、checkout、clean、commit。
- 使用 TDD；完整 Gate 为 `pnpm.cmd typecheck`、全量 `pnpm.cmd test`、`pnpm.cmd build`、范围 `git diff --check`。

---

### Task 1: Freeze the stable User ID directory contract

**Files:**
- Modify: `src/types/crm.ts`
- Modify: `src/demo/personnel.ts`
- Modify: `src/demo/identities.ts`
- Modify: `src/demo/personnel.test.ts`
- Modify: `src/demo/identities.test.ts`
- Create: `src/demo/stable-identity-contract.test.ts`

- [x] Add `UserId` alias and assert Bootstrap/user references share the same ID format.
- [x] Change personnel IDs to explicit ASCII Frappe User names; preserve Mock switch aliases in `demoIdentityId`.
- [x] Replace name-based helpers with `personnelById`, `personnelDisplayName`, `preferredPersonnelId`, `isPersonnelId`, and ID-based role validation.
- [x] Confirm RED for legacy name assignment and GREEN for stable IDs, including the internal-person/customer-contact same-name case.

### Task 2: Build the controlled migration data product

**Files:**
- Create: `src/demo/identity-migration.ts`
- Create: `src/demo/identity-migration.test.ts`
- Create: `docs/CRM-人员显示名到Frappe用户ID迁移映射-2026-08-04.csv`
- Create: `docs/CRM-人员身份字段与外部标签边界-2026-08-04.md`

- [x] Inventory every legacy internal identity value and classify it as active user, alias, orphan, external person, organization, or workflow label.
- [x] Freeze one-to-one legacy display-name/alias to User ID mappings with role and disposition; duplicates or unknown internal values fail closed.
- [x] Document external/organization labels that are intentionally not Link→User.
- [x] Add tests proving every backend-facing seed identity resolves and that customer contact `演示员工14` remains in the Contact ID namespace.

### Task 3: Migrate repository state and API authorization to User IDs

**Files:**
- Modify: `src/api/mock-data.ts`
- Modify: `src/demo/leads-data.ts`
- Modify: `src/demo/operations-data.ts` only for backend-facing internal identity fields
- Modify: `src/demo/demo-repository.ts`
- Modify: `src/demo/sales-repository.ts`
- Modify: `src/api/mock-adapter.ts`
- Modify focused repository/API tests

- [x] Normalize legacy seed snapshots before they become repository state; repository snapshots and API responses may not contain display names in internal identity fields.
- [x] Pass `userId` into `createMockApi`; scope and assignment comparisons use IDs, never `userName`.
- [x] Validate owner role by ID; reject display names and unknown IDs with existing error codes.
- [x] Set server-owned Actor/Approver/CreatedBy/UploadedBy from active `userId`; ignore or omit client identity values where applicable.
- [x] Preserve existing role capabilities, row scope, transactions, state transitions, and relation synchronization.

### Task 4: Keep UI labels human-readable while form/filter values remain IDs

**Files:**
- Modify: `src/design-system/PersonnelSelect.vue`
- Modify affected owner/actor pages and feature components
- Modify focused UI tests

- [x] Personnel selects bind User ID and render display name/team.
- [x] Owner/actor/approver labels resolve through `personnelDisplayName`, with safe fallback only for documented external/organization labels.
- [x] Search matches both stable ID and display name; filters compare stable IDs.
- [x] Assert rendered CRM screens do not leak `@crm.example.invalid` where a human label is expected.

### Task 5: Unify Bootstrap, identity switching, mentions, and notifications

**Files:**
- Modify: `src/stores/app.ts`
- Modify: `src/stores/notifications.ts`
- Modify: `src/api/notifying-api.ts`
- Modify: `src/pages/DemoDetailPage.vue`
- Modify related tests

- [x] Bootstrap returns the explicit active `userId`; Mock switch key remains separate.
- [x] Notification `recipientId` stores User ID and visibility compares User ID only; `recipient` remains a presentation label and is not an authorization fallback.
- [x] Mention selections submit/resolve User IDs while showing names.
- [x] Assert users with identical display names in different namespaces cannot receive or mutate each other's notifications.

### Task 6: Complete Stage 3 Gate and contract registration

**Files:**
- Modify: `docs/CRM-后端数据库对接契约-2026-08-04.md`
- Modify: `docs/CRM-持续执行审计日志-2026-08-04.md`
- Modify this plan's Execution Status

- [x] Static scan: no name-based permission comparison and no business record contains a Mock switch alias.
- [x] Run typecheck, focused tests, full tests, build, and scoped diff check.
- [x] Check only a “Stage 3 contract transform completed” sub-item; keep full A3 unchecked until Frappe User/Employee Links, server assignment, and migration integration pass.
- [x] Record every material choice, issue, workaround, verification result, and remaining backend risk; mirror the audit log to Desktop.
