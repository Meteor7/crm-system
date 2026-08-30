# Controlled PPT, Shared Sales Accounts, and Site Editing Implementation Plan

> **For agentic workers:** Execute inline in this session. Do not commit, reset, stash, clean, or remove Docker volumes.

**Goal:** Replace the Mushi PDF with Aconca and Nansi source PPTX documents, add persistent Manager approval for watermarked PDF or original PPTX delivery, share customer archives across Sales users, and maintain customer sites from Modify Account.

**Architecture:** Store the original PPTX and a pre-rendered PDF derivative as separate private Frappe Files. A persistent access-request DocType records requester, reason, decision, delivery mode, approver, and timestamps; preview always uses the per-user watermarked PDF, while an Original approval downloads the verified PPTX. Customer visibility is shared for Sales at the Customer permission boundary, while Engineer assignment scope remains unchanged. Sites remain ERPNext Address records linked to Customer and gain explicit create/update API operations.

**Tech Stack:** Vue 3, TypeScript, Frappe/ERPNext v15, Python, MariaDB, Docker Compose, pypdf.

## Global Constraints

- Do not use TDD; debug first, then run focused and regression tests.
- Do not add HRMS, ERP business apps, or OCR services.
- Keep all source documents private in Frappe; never expose a public static URL.
- Do not log passwords, tokens, cookies, or document bytes.
- Keep Docker volumes and the existing local database intact.
- Package pre-rendered PDF derivatives so the same design works on Ubuntu without Microsoft Office.

---

### Task 1: Controlled document data model and seed migration

**Files:**
- Create: `backend/apps/rayher_crm/rayher_crm/rayher_crm/doctype/crm_document_access_request/*`
- Modify: `backend/apps/rayher_crm/rayher_crm/rayher_crm/doctype/crm_controlled_document/crm_controlled_document.json`
- Modify: `backend/apps/rayher_crm/rayher_crm/setup/controlled_documents.py`
- Add binaries: `backend/apps/rayher_crm/rayher_crm/assets/controlled_documents/*`

- [ ] Add fields for the private preview PDF and its integrity metadata.
- [ ] Add a persistent request record with Pending, Approved, Rejected, and More Info Required states and Watermarked/Original delivery modes.
- [ ] Seed Aconca and Nansi idempotently and remove only the exact legacy Mushi controlled document and attached private file.
- [ ] Verify PPTX/PDF hashes before saving private Frappe Files.

### Task 2: Approval and secure delivery services

**Files:**
- Modify: `backend/apps/rayher_crm/rayher_crm/services/read_only_views.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/services/controlled_documents.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/api/v1/read_only_views.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/api/v1/controlled_documents.py`

- [ ] List all released controlled documents and the current user's latest request state.
- [ ] Create one pending request per user/document/version and list the Manager queue.
- [ ] Restrict decisions to Manager and require Watermarked or Original on approval.
- [ ] Allow Manager or an approved requester to preview a per-user watermarked PDF.
- [ ] Download watermarked PDF for Watermarked approval or verified source PPTX for Original approval.
- [ ] Audit every allowed and denied preview/download with request and access identifiers.

### Task 3: Document Center real approval UI

**Files:**
- Modify: `src/types/workspaces.ts`
- Modify: `src/api/contracts.ts`
- Modify: `src/api/frappe-adapter.ts`
- Modify: `src/api/mock-adapter.ts`
- Modify: `src/pages/DocumentCenterPage.vue`

- [ ] Show the real Manager queue in Frappe mode.
- [ ] Add approval actions for Watermarked PDF, Original PPTX, rejection, and more information.
- [ ] Show requester status and unlock preview/download only after approval.
- [ ] Keep preview labeled as watermarked PDF even when original PPTX download is approved.

### Task 4: Shared Sales accounts and site maintenance

**Files:**
- Modify: `backend/apps/rayher_crm/rayher_crm/permissions/scope.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/services/sites.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/api/v1/accounts.py`
- Modify: `src/api/contracts.ts`
- Modify: `src/api/frappe-adapter.ts`
- Modify: `src/api/mock-adapter.ts`
- Modify: `src/pages/AccountDetailPage.vue`

- [ ] Make all Customer rows visible to every Sales user while retaining the owner field and Engineer assignment scope.
- [ ] Expose create/update Site operations backed by linked ERPNext Address records.
- [ ] Add an editable site section inside Modify Account and refresh Account 360 after saving.

### Task 5: Local migration and verification

**Files:**
- Modify mechanically: `backend/build/rayher_crm.zip`
- Modify mechanically: Docker images and the existing site schema/data.

- [ ] Validate PPTX signatures, PDF page counts (19 and 36), and all exported slide images.
- [ ] Run frontend type/build tests and focused backend tests.
- [ ] Rebuild the app image and run `bench migrate` without recreating volumes.
- [ ] Verify two Sales accounts can see the same Customer, create/update a Site, submit a document request, approve each delivery mode, preview a personalized watermark, and download the expected MIME type.
