# Quotation Strict Word Template Fidelity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the approximate quotation HTML preview with one template-faithful, multi-page PDF pipeline used by draft preview, publication, download, and history.

**Architecture:** Frappe remains the single rendering authority. A pure context builder prepares template values, one HTML template reproduces the retained Word/PDF layout, and one `render_quotation_pdf(master, version) -> bytes` function serves both the temporary preview endpoint and formal publication. The Vue page fetches the preview as a PDF Blob and displays its object URL, so the visible preview and published file use identical bytes-generation logic.

**Tech Stack:** Frappe v15, Jinja, `frappe.utils.pdf.get_pdf`, Vue 3, TypeScript, Vitest, Docker Compose, Poppler/pdfplumber for visual QA.

## Global Constraints

- `Format.doc` and `Format.pdf` are the sole visual authority; conflicting prior layout decisions are discarded.
- Every A4 page repeats the full header: QIHENG DEMO logo, right-aligned `Ref. No.`, and the horizontal rule.
- The device table has exactly four columns: Items, Description, QTY, Unit price（RMB）.
- QTY is always a positive integer.
- The PDF amount block shows only the template's single-unit total, total device-count price, and tax note.
- Only delivery months, warranty months, and validity months are editable commercial clauses.
- No watermark and no new dependency.
- Existing quotation records and historical PDFs must not be deleted, reset, or backfilled.
- Preview generation failure must not lose saved draft data; publication failure must not create a Published version.
- All source writes must use the machine's trusted WSL/cmd writer path because of TipRay transparent encryption.

---

### Task 1: Lock the retained template contract with failing tests and a branded asset

**Files:**
- Create: `backend/apps/rayher_crm/rayher_crm/public/images/quotation-planck-logo.png`
- Modify: `backend/apps/rayher_crm/rayher_crm/tests/test_quotation_backend_contract.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/tests/test_quotation_api.py`
- Reference only: `C:\Users\PlanckSemicon\Desktop\Week 4\Format.pdf`

**Interfaces:**
- Consumes: the retained two-page reference PDF.
- Produces: a committed logo asset and executable assertions for template structure and PDF behavior.

- [ ] **Step 1: Extract the retained logo without redrawing it**

Use Poppler's bundled `pdfimages` against page 1, convert the repeated `IM14` image to PNG when needed, and save the resulting transparent/white-background logo as `quotation-planck-logo.png`. Verify with Pillow that width and height are non-zero and visually inspect it before committing.

- [ ] **Step 2: Add failing template-contract assertions**

Add assertions equivalent to:

```python
template = TEMPLATE.read_text(encoding="utf-8")
self.assertIn("quotation-planck-logo.png", template)
self.assertIn("Ref. No.: {{ refNo }}", template)
self.assertIn("Items", template)
self.assertIn("Description", template)
self.assertIn("QTY", template)
self.assertIn("Unit price", template)
self.assertNotIn("Amount（RMB）", template)
self.assertIn("单台总价（折扣后）", template)
self.assertIn("台总价（RMB）", template)
self.assertNotIn("报价小计", template)
self.assertNotIn("整单折扣", template)
```

Also assert that `quotations.py` defines one `render_quotation_pdf` function and that preview/publication both call it.

- [ ] **Step 3: Add failing Frappe integration coverage**

Extend `test_quotation_api.py` with a multi-page payload containing two parent devices and several accessories. Assert:

```python
self.assertEqual(context["deviceCount"], 3)
self.assertEqual(context["singleUnitTotal"], "15000.00")
self.assertEqual(context["total"], "45000.00")
self.assertEqual(context["items"][0]["displayIndex"], 1)
self.assertEqual(context["items"][1]["displayIndex"], "")
self.assertEqual(context["items"][0]["quantity"], 2)
```

Request the draft preview PDF and published PDF; assert both begin with `%PDF`, contain at least two pages, and use the same renderer spy.

- [ ] **Step 4: Run the red tests**

Run:

```powershell
npm.cmd test -- --run src/pages/QuotationDetailPage.test.ts src/api/frappe-adapter.test.ts
& 'C:\Users\PlanckSemicon\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest backend/apps/rayher_crm/rayher_crm/tests/test_quotation_backend_contract.py -v
```

Expected: backend contract fails because the logo/four-column/template-total contract and unified PDF renderer do not exist.

- [ ] **Step 5: Commit the contract test and asset**

```powershell
git add backend/apps/rayher_crm/rayher_crm/public/images/quotation-planck-logo.png backend/apps/rayher_crm/rayher_crm/tests/test_quotation_backend_contract.py backend/apps/rayher_crm/rayher_crm/tests/test_quotation_api.py
git commit -m "test: lock quotation Word template contract"
```

### Task 2: Build the exact template context and four-column Word layout

**Files:**
- Modify: `backend/apps/rayher_crm/rayher_crm/services/quotations.py`
- Replace in place: `backend/apps/rayher_crm/rayher_crm/templates/quotation/quotation.html`
- Test: `backend/apps/rayher_crm/rayher_crm/tests/test_quotation_backend_contract.py`
- Test: `backend/apps/rayher_crm/rayher_crm/tests/test_quotation_api.py`

**Interfaces:**
- Consumes: `CRM Quotation`, `CRM Quotation Version`, serialized items, exact decimal totals.
- Produces: `_pdf_context(master, version) -> dict[str, Any]` containing `deviceCount`, `singleUnitTotal`, `items[*].displayIndex`, and the fixed template text.

- [ ] **Step 1: Add failing context tests for parent/child mapping and total rows**

Test the intended values:

```python
context = quotations._pdf_context(master, version)
self.assertEqual([row["displayIndex"] for row in context["items"]], [1, "", 2])
self.assertEqual(context["deviceCount"], 3)
self.assertEqual(context["singleUnitTotal"], "15000.00")
self.assertEqual(context["deviceCountLabel"], "3台总价（RMB）")
```

Use exact decimal division with two-place ROUND_HALF_UP; reject a zero-device context as `VALIDATION_ERROR`.

- [ ] **Step 2: Implement the minimal context transformation**

Add focused helpers:

```python
def _template_items(version_data: dict[str, Any]) -> list[dict[str, Any]]:
    device_number = 0
    rows = []
    for item in version_data["items"]:
        row = dict(item)
        if item["lineType"] == "Device":
            device_number += 1
            row["displayIndex"] = device_number
        else:
            row["displayIndex"] = ""
        rows.append(row)
    return rows

def _single_unit_total(total: str, device_count: int) -> str:
    if device_count <= 0:
        raise CrmApiException("VALIDATION_ERROR", "At least one device is required.")
    return decimal_string(Decimal(total) / Decimal(device_count))
```

Count devices with `sum(int(item["quantity"]) for item in items if item["lineType"] == "Device")`.

- [ ] **Step 3: Replace the template with measured A4 layout**

Implement:

- an `@page` header reservation matching the reference;
- a fixed repeated `.page-header` containing the retained logo, Ref. No., and rule;
- the centered title and two-column customer/company block;
- the reference's double equals separator;
- a four-column table with measured widths;
- parent device rows and indented accessory rows;
- only the two template totals and tax note;
- fixed terms in the exact reference order and wording;
- footer company/date block;
- CSS2.1-compatible layout only, avoiding flex/grid in PDF-critical blocks.

Use a Frappe-resolvable absolute asset URL or an embedded data URI so wkhtmltopdf cannot drop the logo.

- [ ] **Step 4: Run backend tests**

Run the local contract test and Frappe quotation integration test. Expected: all template/context tests pass, and generated PDF bytes are valid.

- [ ] **Step 5: Commit context and template**

```powershell
git add backend/apps/rayher_crm/rayher_crm/services/quotations.py backend/apps/rayher_crm/rayher_crm/templates/quotation/quotation.html backend/apps/rayher_crm/rayher_crm/tests
git commit -m "feat: reproduce retained quotation template"
```

### Task 3: Unify draft preview and formal publication on one PDF renderer

**Files:**
- Modify: `backend/apps/rayher_crm/rayher_crm/services/quotations.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/api/v1/quotations.py`
- Test: `backend/apps/rayher_crm/rayher_crm/tests/test_quotation_api.py`
- Test: `backend/apps/rayher_crm/rayher_crm/tests/test_quotation_backend_contract.py`

**Interfaces:**
- Produces: `render_quotation_pdf(master, version) -> bytes`.
- Produces API: `GET quotations.preview_pdf(id: str, versionId?: str)` returning `application/pdf`.
- Changes: `_release_pdf(master, version, pdf_content: bytes) -> str` saves pre-rendered bytes.

- [ ] **Step 1: Write failing renderer-sharing and atomicity tests**

Assert:

```python
with patch("rayher_crm.services.quotations.render_quotation_pdf", return_value=b"%PDF-preview") as render:
    filename, content = quotations.get_preview_pdf(master.name)
    self.assertEqual(content, b"%PDF-preview")
    render.assert_called_once()

with patch("rayher_crm.services.quotations.render_quotation_pdf", side_effect=RuntimeError("render failed")):
    with self.assertRaises(RuntimeError):
        quotations.publish_version(master.name, expected_modified)
    version.reload()
    self.assertEqual(version.status, "Draft")
    self.assertFalse(version.pdf_file)
```

- [ ] **Step 2: Implement one renderer and draft-preview service**

```python
def render_quotation_pdf(master, version) -> bytes:
    from frappe.utils.pdf import get_pdf
    return get_pdf(render_quotation_html(master, version))

def get_preview_pdf(name: str, version_id: str | None = None) -> tuple[str, bytes]:
    assert_capability("quotation:view")
    master, version = _quotation_version(name, version_id)
    return f"{master.ref_no}-V{int(version.version_no)}-preview.pdf", render_quotation_pdf(master, version)
```

Reuse one `_quotation_version` validator for JSON detail, preview, and download.

- [ ] **Step 3: Make publication render before status transition**

Order publication as:

```python
_apply_values(version, validated)
version.save(ignore_permissions=True)
pdf_content = render_quotation_pdf(master, version)
version.status = "Published"
version.published_at = now_datetime()
version.save(ignore_permissions=True)
version.pdf_file = _release_pdf(master, version, pdf_content)
version.save(ignore_permissions=True)
```

If rendering fails, no Published status or PDF URL is written.

- [ ] **Step 4: Add the whitelisted preview endpoint**

Return the binary through `frappe.local.response` exactly like download, with `Content-Type: application/pdf` and preview filename.

- [ ] **Step 5: Run backend tests and commit**

Run focused local and real Frappe tests, then commit:

```powershell
git add backend/apps/rayher_crm/rayher_crm/services/quotations.py backend/apps/rayher_crm/rayher_crm/api/v1/quotations.py backend/apps/rayher_crm/rayher_crm/tests
git commit -m "fix: unify quotation preview and publish PDF"
```

### Task 4: Display the actual preview PDF in Vue and manage Blob lifecycle

**Files:**
- Modify: `src/api/contracts.ts`
- Modify: `src/api/frappe-adapter.ts`
- Modify: `src/api/frappe-adapter.test.ts`
- Modify: `src/features/quotations/types.ts`
- Modify: `src/features/quotations/QuotationPreview.vue`
- Modify: `src/pages/QuotationDetailPage.vue`
- Modify: `src/pages/QuotationDetailPage.test.ts`

**Interfaces:**
- Adds: `CrmApi.getQuotationPreviewPdf(id: string, versionId?: string): Promise<BinaryDownload>`.
- Changes preview component to `defineProps<{ src: string }>()`.
- Removes `QuotationDetailDto.previewHtml`.
- Page owns `previewUrl: Ref<string>` and revokes replaced/unmounted object URLs.

- [ ] **Step 1: Write failing adapter and component tests**

Adapter test:

```ts
expect(FRAPPE_METHODS.getQuotationPreviewPdf).toBe('quotations.preview_pdf')
await api.getQuotationPreviewPdf('CRM-QTN-00001', 'CRM-QTV-00001')
expect(fetchMock).toHaveBeenCalledWith(
  expect.stringContaining('quotations.preview_pdf'),
  expect.objectContaining({ method: 'GET' }),
)
```

Page test:

```ts
expect(client.getQuotationPreviewPdf).toHaveBeenCalledWith('CRM-QTN-00001', 'CRM-QTV-00001')
expect(wrapper.get('[data-testid="quotation-preview"]').attributes('src')).toBe('blob:quotation-preview')
expect(wrapper.get('[data-testid="quotation-preview"]').attributes('srcdoc')).toBeUndefined()
```

Assert the old Blob URL is revoked after a successful save refresh and on unmount.

- [ ] **Step 2: Add the binary API contract and adapter method**

Map `getQuotationPreviewPdf` to `requestBinary(..., 'quotation-preview.pdf')`.

- [ ] **Step 3: Change the preview component to a PDF iframe**

```vue
<script setup lang="ts">
defineProps<{ src: string }>()
</script>
<template>
  <iframe
    class="quotation-preview"
    data-testid="quotation-preview"
    title="报价单 PDF 预览"
    :src="src"
  />
</template>
```

- [ ] **Step 4: Load and refresh preview only after successful detail loads/saves**

Add:

```ts
async function refreshPreview(versionId = detail.value?.version.id) {
  if (!versionId) return
  const file = await props.apiClient.getQuotationPreviewPdf(quotationId.value, versionId)
  const nextUrl = URL.createObjectURL(file.blob)
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = nextUrl
}
```

Call it after `applyDetail` for load/save/version selection. If it fails after a draft save, retain the previous URL and set a preview-specific error; do not replace the saved draft with stale data.

- [ ] **Step 5: Run focused frontend tests and commit**

```powershell
npm.cmd test -- --run src/pages/QuotationDetailPage.test.ts src/api/frappe-adapter.test.ts
git add src/api src/features/quotations src/pages/QuotationDetailPage.vue src/pages/QuotationDetailPage.test.ts
git commit -m "feat: preview exact quotation PDF"
```

### Task 5: Render-diff, full regression, deployment, and LAN QA

**Files:**
- Create QA intermediates only: `.codex-tmp/quotation-template-qa-<iteration>/`
- Modify only if a visual defect is found: template CSS/context/tests from Tasks 1-4.
- Do not commit QA PNG/PDF intermediates.

**Interfaces:**
- Consumes: real draft quotation, preview endpoint, retained `Format.pdf`.
- Produces: verified Docker deployment at `http://203.0.113.10:2224/crm`.

- [ ] **Step 1: Run complete automated tests**

```powershell
npm.cmd test -- --run
& 'C:\Users\PlanckSemicon\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest backend/apps/rayher_crm/rayher_crm/tests/test_quotation_backend_contract.py -v
```

Run the real Frappe quotation integration suite with `allow_tests=1`, explicitly fail if output contains `FAILED` or `ERROR`, and restore `allow_tests=0` in `finally`.

- [ ] **Step 2: Generate a representative multi-page preview PDF**

Use a disposable test quotation/version or a transaction rolled back after rendering. Do not publish or mutate `CRM-QTN-00115` or `CRM-QTN-00117`.

- [ ] **Step 3: Render every page and compare with the retained template**

Use bundled Poppler:

```powershell
pdftoppm -png -r 144 generated-preview.pdf .codex-tmp/quotation-template-qa-1/generated
pdftoppm -png -r 144 "C:\Users\PlanckSemicon\Desktop\Week 4\Format.pdf" .codex-tmp/quotation-template-qa-1/reference
```

Inspect every page at 100% zoom. Fail the gate for missing/repositioned header, wrong logo, wrong Ref. No., incorrect margins, table columns, typography, wrapping, pagination, totals, clauses, clipping, overlap, mojibake, or unexplained whitespace. Iterate template CSS and rerender into a new QA directory until clean.

- [ ] **Step 4: Build and deploy**

```powershell
npm.cmd run build:frappe
powershell -NoProfile -ExecutionPolicy Bypass -File backend\scripts\prepare-app-build-context.ps1
$env:DOCKER_CONFIG=(Resolve-Path '.codex-tmp\docker').Path
docker compose --env-file backend/.env.lan -f backend/compose.yaml build
docker compose --env-file backend/.env.lan -f backend/compose.yaml up -d
```

- [ ] **Step 5: Verify runtime boundaries**

Require all services healthy, LAN HTML HTTP 200, `allow_tests=0`, and preserved quotation names `CRM-QTN-00115` and `CRM-QTN-00117`.

- [ ] **Step 6: Browser QA in the signed-in LAN session**

Verify:

- contact and site selectors still work;
- saving refreshes the PDF preview;
- every visible PDF page has the complete logo/Ref. No./rule header;
- table is four columns;
- QTY is integer;
- percentage/fixed/no-discount edits persist but PDF shows only template totals;
- the three editable commercial values update the PDF;
- history opens its own stored PDF;
- browser console has no errors.

Restore all temporary values and do not publish a user record.

- [ ] **Step 7: Final verification commit**

Commit only source/test changes needed by the visual iterations:

```powershell
git add backend/apps/rayher_crm/rayher_crm src
git commit -m "fix: match quotation Word template exactly"
```
