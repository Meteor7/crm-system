# Installed Tool Lifecycle Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build real Installed Tool lifecycle advancement, version/configuration history, warranty/service history, master-data completeness, and server-enforced Manager/assigned-Engineer permissions across every API layer.

**Architecture:** Keep `CRM Installed Tool` as the current snapshot and add three append-only child-history DocTypes. All mutations are command-style service calls guarded by a shared server authorization helper, CAS locking, and savepoints; list returns summaries while a new detail endpoint returns the three real histories and server-computed permissions. Vue uses three focused modals and always reloads detail after mutations.

**Tech Stack:** Vue 3, TypeScript, Vitest, Frappe v15/Python, MariaDB, Docker Compose.

## Global Constraints

- Lifecycle order is exactly `FAT → Shipment → Installation → SAT → Warranty`; no skipping, rollback, or repeat completion.
- Only CRM Manager or the current `engineer_owner` may update/advance/add version/add service; Sales and other Engineers are denied server-side.
- Engineer may never reassign ownership; Manager may reassign through master-data edit only.
- Histories are append-only and ordinary CRM roles receive read-only DocType permissions.
- Every mutation requires `expectedModified`, locks the Installed Tool, and performs snapshot/history writes in one savepoint.
- Production code continues to use the Frappe adapter; mock behavior exists only for tests and must match real permissions/state rules.
- No new third-party dependencies and no unrelated refactoring.
- All project writes must use the machine's trusted plaintext-writer workflow from AGENTS.md.

---

### Task 1: Canonical schema and idempotent migration

**Files:**
- Modify: `backend/apps/rayher_crm/rayher_crm/tests/test_stage5b_schema.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/rayher_crm/doctype/crm_installed_tool/crm_installed_tool.json`
- Create: `backend/apps/rayher_crm/rayher_crm/rayher_crm/doctype/crm_installed_tool_lifecycle_history/__init__.py`
- Create: `backend/apps/rayher_crm/rayher_crm/rayher_crm/doctype/crm_installed_tool_lifecycle_history/crm_installed_tool_lifecycle_history.py`
- Create: `backend/apps/rayher_crm/rayher_crm/rayher_crm/doctype/crm_installed_tool_lifecycle_history/crm_installed_tool_lifecycle_history.json`
- Create: `backend/apps/rayher_crm/rayher_crm/rayher_crm/doctype/crm_installed_tool_version_history/__init__.py`
- Create: `backend/apps/rayher_crm/rayher_crm/rayher_crm/doctype/crm_installed_tool_version_history/crm_installed_tool_version_history.py`
- Create: `backend/apps/rayher_crm/rayher_crm/rayher_crm/doctype/crm_installed_tool_version_history/crm_installed_tool_version_history.json`
- Create: `backend/apps/rayher_crm/rayher_crm/rayher_crm/doctype/crm_installed_tool_service_history/__init__.py`
- Create: `backend/apps/rayher_crm/rayher_crm/rayher_crm/doctype/crm_installed_tool_service_history/crm_installed_tool_service_history.py`
- Create: `backend/apps/rayher_crm/rayher_crm/rayher_crm/doctype/crm_installed_tool_service_history/crm_installed_tool_service_history.json`
- Create: `backend/apps/rayher_crm/rayher_crm/patches/v1_0/migrate_installed_tool_lifecycle.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/patches.txt`

**Interfaces:**
- Produces main fields `lifecycle_stage: Select`, date-typed warranty fields, and three history DocTypes.
- Produces idempotent `execute()` migration consumed by Docker migrate.

- [ ] **Step 1: Write failing schema tests**

Add assertions that main metadata contains `lifecycle_stage`, `warranty_start`, `warranty_end`, `last_service` with correct field types, and that all three history DocTypes expose the exact fields and only Manager/Sales/Engineer read permissions.

```python
self.assertEqual(installed_tool.get_field("lifecycle_stage").options, "FAT\nShipment\nInstallation\nSAT\nWarranty")
self.assertEqual(installed_tool.get_field("warranty_start").fieldtype, "Date")
for doctype in HISTORY_DOCTYPES:
    permissions = frappe.get_meta(doctype).permissions
    self.assertTrue(all(row.read and not row.write and not row.create and not row.delete for row in permissions))
```

- [ ] **Step 2: Run schema test and verify RED**

Run in backend container:

```powershell
docker compose --env-file backend/.env.example -f backend/compose.yaml exec backend bench --site rayher-crm.localhost run-tests --app rayher_crm --module rayher_crm.tests.test_stage5b_schema
```

Expected: FAIL because new fields/DocTypes do not exist.

- [ ] **Step 3: Add minimal schema files**

Use Link/User/Date/Select/Small Text/JSON field types specified by the approved design. Keep history autoname `hash`, sort by `at desc`, and omit create/write/delete permissions.

- [ ] **Step 4: Add idempotent migration test and patch**

Test two executions produce the same history count and normalize placeholder dates to null. Migration derives Current milestone first, then status mapping, then FAT; it creates legacy rows only when no matching `(installed_tool,to_stage,comment='Legacy milestone migration')` exists.

- [ ] **Step 5: Run schema and migration tests GREEN**

Expected: all assertions pass with no duplicate migration rows.

- [ ] **Step 6: Commit Task 1**

```powershell
git add backend/apps/rayher_crm/rayher_crm/rayher_crm/doctype backend/apps/rayher_crm/rayher_crm/patches backend/apps/rayher_crm/rayher_crm/patches.txt backend/apps/rayher_crm/rayher_crm/tests/test_stage5b_schema.py
git commit -m "feat: add installed tool audit schema"
```

### Task 2: Detail serialization and shared operation authorization

**Files:**
- Modify: `backend/apps/rayher_crm/rayher_crm/services/installed_tools.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/api/v1/installed_tools.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/tests/test_installed_tool_api.py`

**Interfaces:**
- Produces `_assert_installed_tool_operator(doc) -> str`.
- Produces `get_installed_tool(name) -> dict` with `lifecycleHistory`, `versionHistory`, `serviceHistory`, `canOperate`, `canReassign`.
- Keeps list serializer light and stable.

- [ ] **Step 1: Write failing authorization/detail tests**

Assert Manager and assigned Engineer receive `canOperate=True`; Sales and other Engineer cannot mutate; detail histories are ordered newest-first and cross-scope IDs are denied.

```python
frappe.set_user(self.engineer)
detail = get_installed_tool(tool["id"])
self.assertTrue(detail["canOperate"])
self.assertFalse(detail["canReassign"])
frappe.set_user(self.other_engineer)
with self.assertRaises(CrmApiException) as denied:
    get_installed_tool(tool["id"])
self.assertEqual(denied.exception.code, "INSTALLED_TOOL_SCOPE_DENIED")
```

- [ ] **Step 2: Verify RED**

Expected: import or assertion failure because detail service and endpoint are missing.

- [ ] **Step 3: Implement serializers and authorization helper**

The helper resolves role after read-scope check and allows only Manager or exact `engineer_owner`. It raises `INSTALLED_TOOL_OPERATION_DENIED` for a visible but non-operating user. Serialization reads history with explicit field lists and stable ordering.

- [ ] **Step 4: Add endpoint envelope test**

Call `get_installed_tool` API endpoint and assert `data`, `warnings`, `meta.requestId`, and all history arrays.

- [ ] **Step 5: Run installed tool tests GREEN**

- [ ] **Step 6: Commit Task 2**

```powershell
git add backend/apps/rayher_crm/rayher_crm/services/installed_tools.py backend/apps/rayher_crm/rayher_crm/api/v1/installed_tools.py backend/apps/rayher_crm/rayher_crm/tests/test_installed_tool_api.py
git commit -m "feat: add installed tool detail api"
```

### Task 3: Lifecycle transition command

**Files:**
- Modify: `backend/apps/rayher_crm/rayher_crm/services/installed_tools.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/api/v1/installed_tools.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/tests/test_installed_tool_api.py`

**Interfaces:**
- Produces `transition_installed_tool(name, payload, expected_modified, failure_injector=None) -> dict`.
- Input fields: `completedAt`, `result`, `openIssues`, `customerSignoff`, `comment`, `evidence`.

- [ ] **Step 1: Write failing happy-path state-machine test**

Advance a converted tool five times and assert exact from/to history, status mapping, milestone state, completeness changes, final Warranty completion, and no next stage.

- [ ] **Step 2: Verify RED**

Expected: transition function missing.

- [ ] **Step 3: Implement minimal state machine**

Define immutable order and status map. Validate all fields before savepoint, lock with `lock_document`, re-check operator after locking, insert history, update snapshot, and reload.

- [ ] **Step 4: Write permission and invalid-transition RED tests**

Cover Manager, assigned Engineer, Sales, other Engineer, stale `expectedModified`, repeated Warranty, invalid evidence entries, and missing required fields. Assert failed operations do not change main row or history count.

- [ ] **Step 5: Add failure-injection atomicity tests**

Inject after history insert and after tool update; both must roll back.

- [ ] **Step 6: Implement validation/rollback and run GREEN**

- [ ] **Step 7: Add endpoint envelope test and commit Task 3**

```powershell
git add backend/apps/rayher_crm/rayher_crm/services/installed_tools.py backend/apps/rayher_crm/rayher_crm/api/v1/installed_tools.py backend/apps/rayher_crm/rayher_crm/tests/test_installed_tool_api.py
git commit -m "feat: advance installed tool lifecycle"
```

### Task 4: Version/configuration and warranty/service commands

**Files:**
- Modify: `backend/apps/rayher_crm/rayher_crm/services/installed_tools.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/api/v1/installed_tools.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/tests/test_installed_tool_api.py`

**Interfaces:**
- Produces `add_installed_tool_version_record(name,payload,expected_modified,failure_injector=None)`.
- Produces `add_installed_tool_service_record(name,payload,expected_modified,failure_injector=None)`.

- [ ] **Step 1: Write failing version command tests**

For all four `changeType` values, assert `fromValue` comes from server snapshot, `toValue` updates the matching main field, actor/date/reason are stored, and client-forged `fromValue` is ignored.

- [ ] **Step 2: Verify version tests RED, then implement minimal command**

Use a fixed map from public change type to DocType field. Reject unknown types and blank/no-op values. Perform history and snapshot in one savepoint.

- [ ] **Step 3: Write failing service command tests**

Assert service record append, `last_service`, optional warranty/contract/PM snapshot changes, and conditional owner/due validation when next action exists.

- [ ] **Step 4: Verify service tests RED, then implement minimal command**

Validate service type enum and Date values. Do not allow service payload to update unrelated main fields.

- [ ] **Step 5: Add four-role, CAS, endpoint envelope, and failure-injection tests**

Run the same permission matrix against both commands and assert full rollback.

- [ ] **Step 6: Run installed tool backend suite GREEN and commit Task 4**

```powershell
git add backend/apps/rayher_crm/rayher_crm/services/installed_tools.py backend/apps/rayher_crm/rayher_crm/api/v1/installed_tools.py backend/apps/rayher_crm/rayher_crm/tests/test_installed_tool_api.py
git commit -m "feat: track installed tool versions and service"
```

### Task 5: Frontend types and every API transport layer

**Files:**
- Modify: `src/types/workspaces.ts`
- Modify: `src/api/contracts.ts`
- Modify: `src/api/frappe-adapter.ts`
- Modify: `src/api/frappe-adapter.test.ts`
- Modify: `src/api/mock-adapter.ts`
- Modify: `src/api/mock-adapter.test.ts`

**Interfaces:**
- Produces `InstalledToolSummaryDto`, `InstalledToolDetailDto`, three history DTOs, and three mutation input types.
- Adds CrmApi methods `getInstalledTool`, `transitionInstalledTool`, `addInstalledToolVersionRecord`, `addInstalledToolServiceRecord`.

- [ ] **Step 1: Write Frappe adapter RED tests**

Assert exact method names, POST/GET transport, public field names, and `expectedModified` for every new method.

```ts
await api.transitionInstalledTool('CRM-TOOL-00001', input, 'v1')
expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('installed_tools.transition_installed_tool'), expect.objectContaining({ method: 'POST' }))
```

- [ ] **Step 2: Verify RED, then add types/contracts/adapter mapping**

Do not use `any`; optionality must match server validation.

- [ ] **Step 3: Write mock RED tests for state and four-role permissions**

Test Manager, assigned Engineer, other Engineer and Sales for all three mutations, CAS, history append, and snapshot changes.

- [ ] **Step 4: Implement mock parity only after RED**

Use the same lifecycle order and server-owned from-value rules. Do not add mock fallback to production runtime.

- [ ] **Step 5: Run adapter and mock suites GREEN, then typecheck**

```powershell
npx.cmd vitest run src/api/frappe-adapter.test.ts src/api/mock-adapter.test.ts
npm.cmd run typecheck
```

- [ ] **Step 6: Commit Task 5**

```powershell
git add src/types/workspaces.ts src/api/contracts.ts src/api/frappe-adapter.ts src/api/frappe-adapter.test.ts src/api/mock-adapter.ts src/api/mock-adapter.test.ts
git commit -m "feat: add installed tool audit api contracts"
```

### Task 6: Installed Tool detail UI and mutation modals

**Files:**
- Modify: `src/pages/InstalledToolsPage.vue`
- Modify: `src/pages/InstalledToolsPage.test.ts`
- Modify: `src/features/installed-tools/InstalledToolArchiveView.vue`
- Modify: `src/features/installed-tools/InstalledToolArchiveView.test.ts`
- Modify: `src/features/installed-tools/InstalledToolEditorModal.vue`
- Create: `src/features/installed-tools/InstalledToolTransitionModal.vue`
- Create: `src/features/installed-tools/InstalledToolTransitionModal.test.ts`
- Create: `src/features/installed-tools/InstalledToolVersionModal.vue`
- Create: `src/features/installed-tools/InstalledToolVersionModal.test.ts`
- Create: `src/features/installed-tools/InstalledToolServiceModal.vue`
- Create: `src/features/installed-tools/InstalledToolServiceModal.test.ts`
- Modify: `src/pages/seven-page-workspace.test.ts`

**Interfaces:**
- Archive consumes one real `InstalledToolDetailDto` plus list summaries.
- Emits `advance`, `version`, `service`, `edit`, `document`.

- [ ] **Step 1: Write archive RED test proving hardcoded profiles are not used**

Mount with a unique API history value and assert it renders; assert old `TOOL-001` sample strings do not appear.

- [ ] **Step 2: Write four-role button visibility RED tests**

Manager/assigned Engineer see advance/version/service; Sales and other Engineer do not. Warranty-completed detail hides only advance.

- [ ] **Step 3: Write each modal's RED tests**

Assert exact required fields, conditional service fields, payload trimming, evidence parsing, current value display, and submit-disabled rules.

- [ ] **Step 4: Implement focused modals and remove `toolProfiles`**

Keep lifecycle rendering but map real histories/current milestone. Do not duplicate permission logic beyond consuming server `canOperate`.

- [ ] **Step 5: Wire page detail loading and mutations**

On selection call `getInstalledTool`; after any success reload both detail and list. Use `mapRequestError` and render Request ID. Guard stale responses when selection changes.

- [ ] **Step 6: Expand master editor**

Add OS, warranty dates, service contract, PM cycle, ownership type; remove lifecycle/status free-edit control where it could bypass state machine.

- [ ] **Step 7: Run UI tests and typecheck GREEN**

```powershell
npx.cmd vitest run src/pages/InstalledToolsPage.test.ts src/features/installed-tools/*.test.ts src/pages/seven-page-workspace.test.ts
npm.cmd run typecheck
```

- [ ] **Step 8: Commit Task 6**

```powershell
git add src/pages/InstalledToolsPage.vue src/pages/InstalledToolsPage.test.ts src/features/installed-tools src/pages/seven-page-workspace.test.ts
git commit -m "feat: add installed tool lifecycle actions"
```

### Task 7: Cross-layer adversarial verification and deployment

**Files:**
- Modify only failing in-scope files discovered by verification.

**Interfaces:**
- Proves every approved requirement from source through real HTTP.

- [ ] **Step 1: Run full relevant frontend regression**

Include adapter, mock, Installed Tool, Booking conversion, Calendar, permission revocation, and seven-page workspace tests.

- [ ] **Step 2: Run full relevant Frappe regression**

Run schema, Installed Tool API, Booking API, roles, scope, delivery integration, Dashboard and Calendar-related modules with test config restored in `finally`.

- [ ] **Step 3: Build and package production frontend/app**

Run `npm.cmd run build:frappe`, package with `backend/scripts/prepare-app-build-context.ps1`, and use the trusted plaintext rehydration path.

- [ ] **Step 4: Rebuild Docker and migrate**

```powershell
docker compose --env-file backend/.env.example -f backend/compose.yaml up -d --build
```

Assert migrate exits zero and all long-running containers are healthy.

- [ ] **Step 5: Perform real HTTP four-identity checks**

For Manager, assigned Engineer, other Engineer, and Sales, call detail and all three mutation endpoints using authenticated sessions. Assert success/403 codes, stable envelope, request ID, scope isolation, and no mutation on denied calls.

- [ ] **Step 6: Adversarial P0/P1 audit**

Try forged engineer owner, guessed tool ID, stale version, repeated advance, jump payload, invalid dates, malformed arrays, client-forged actor/from value, concurrent double-submit, and failure injection. Verify no cross-scope disclosure or partial writes.

- [ ] **Step 7: Final completion audit**

Map every section of the approved spec to a test/runtime artifact. Run `git diff --check` on in-scope files, inspect the final diff for unrelated edits, and only then mark the persistent goal complete.