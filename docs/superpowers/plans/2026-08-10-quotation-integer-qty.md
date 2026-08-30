# Quotation Integer QTY Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restrict quotation device and accessory quantities to positive integers in the editor and backend.

**Architecture:** Keep the rule in the existing pure quotation pricing module so draft save and publish share one server-side boundary. Mirror that constraint in the existing editor inputs for immediate browser guidance; do not round or migrate stored values.

**Tech Stack:** Python `Decimal`, Frappe services/tests, Vue 3, Vitest, Docker Compose.

## Global Constraints

- Device and Accessory QTY must be an integer greater than zero.
- Fractional values return the existing `VALIDATION_ERROR`; they are never rounded.
- Existing records are not migrated.
- Pricing, discount, versioning, PDF, and history behavior remain unchanged.
- Preserve unrelated dirty-worktree changes and use Docker Desktop WSL for plaintext writes.

---

### Task 1: Enforce the backend quantity rule

**Files:**
- Modify: `backend/apps/rayher_crm/rayher_crm/tests/test_quotation_rules.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/services/quotation_rules.py`

**Interfaces:**
- Consumes: `calculate_totals(items, discount_type, discount_value, currency='CNY')`.
- Produces: `_quantity(value) -> Decimal`, accepting only positive integral values.

- [ ] **Step 1: Write the failing rule tests**

Add a table-driven test calling `calculate_totals` with a Device quantity of `1.5` and an Included Accessory quantity of `2.5`; each call must raise `QuotationRuleError` matching `whole number`.

- [ ] **Step 2: Run the rule tests and verify RED**

Run: `python -m unittest rayher_crm.tests.test_quotation_rules -v`

Expected: the fractional-device case does not raise, and the Included Accessory case is skipped by current pricing logic.

- [ ] **Step 3: Implement minimal validation**

In `_quantity`, parse without integer rounding, reject `parsed != parsed.to_integral_value()` using `QuotationRuleError('quantity must be a whole number.')`, then require `parsed > 0`. In `calculate_totals`, call `_quantity` before the Included Accessory early return and reuse the validated quantity for subtotal multiplication.

- [ ] **Step 4: Run the rule tests and verify GREEN**

Run the same unittest command. Expected: all quotation rule tests pass.

### Task 2: Constrain both editor inputs

**Files:**
- Modify: `src/pages/QuotationDetailPage.test.ts`
- Modify: `src/features/quotations/QuotationEditor.vue`

**Interfaces:**
- Consumes: `QuotationItemDto.quantity: number`.
- Produces: Device and Accessory number inputs with `min="1"` and `step="1"`.

- [ ] **Step 1: Write the failing UI test**

Mount the real quotation detail page, add an accessory, locate `aria-label="设备数量"` and `aria-label="配件数量"`, and assert both expose `min="1"` and `step="1"`.

- [ ] **Step 2: Run the focused Vitest and verify RED**

Run: `npm.cmd test -- --run src/pages/QuotationDetailPage.test.ts`

Expected: the device minimum is `0.0001`, and the accessory input lacks the required step and labels.

- [ ] **Step 3: Implement minimal input constraints**

Change both quantity inputs to `min="1" step="1"`; add the exact accessible labels `设备数量` and `配件数量`. Keep `v-model.number`, item creation defaults, and autosave unchanged.

- [ ] **Step 4: Run focused tests and production build**

Run the focused Vitest, then `npm.cmd run build:frappe`. Expected: 0 failed tests and build exit 0.

### Task 3: Integration and LAN verification

**Files:**
- Modify: `backend/apps/rayher_crm/rayher_crm/tests/test_quotation_api.py`

**Interfaces:**
- Consumes: `save_draft(name, payload, expected_modified)`.
- Produces: an integration guarantee that fractional quantities return `VALIDATION_ERROR` without a write.

- [ ] **Step 1: Add and run a failing Frappe integration test**

Create a quotation fixture, set its first item quantity to `1.5`, call `save_draft`, and assert `CrmApiException.code == 'VALIDATION_ERROR'`. Run the module in the Frappe container with `allow_tests=1`; restore `allow_tests=0` after execution.

- [ ] **Step 2: Confirm the integration test passes after Task 1**

Expected: Frappe reports the module `OK`, proving the pure rule reaches the API boundary.

- [ ] **Step 3: Build and deploy without resetting data**

Run `prepare-app-build-context.ps1`, `docker compose ... build`, and `docker compose ... up -d` using `backend/.env.lan`.

- [ ] **Step 4: Verify production state**

Confirm backend/frontend containers are healthy, `allow_tests` is false, LAN `/crm` returns HTTP 200, integer QTY saves, and a fractional QTY displays the existing save error while preserving the last preview.