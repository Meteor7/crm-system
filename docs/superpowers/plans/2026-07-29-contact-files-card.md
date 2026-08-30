# Contact Files Card Implementation Plan

> **For agentic workers:** Execute inline in the current workspace. Do not create subagents, worktrees, commits, branches, or pull requests.

**Goal:** Replace the Contact detail data-quality card with a persistent Salesforce-style Files card, move merge to the top actions, and restyle only the top delete button.

**Architecture:** Add a Contact-scoped file repository backed by IndexedDB in the browser and memory storage in tests. Expose file operations through `CrmApi`, keep Frappe methods explicitly unimplemented, and isolate the UI in a dedicated Contact Files card component.

**Tech Stack:** Vue 3, TypeScript, IndexedDB, Vitest, Vue Test Utils, Vite.

## Global Constraints

- Do not use TDD; add regression tests after implementation.
- Do not perform Git operations.
- Do not change the delete confirmation modal or shared `ModalShell`.
- Limit files to PDF, Office documents, TXT, CSV, PNG, and JPEG; maximum 20 MB each.
- Treat the persistent implementation as local Mock behavior only.

---

### Task 1: Contact file model and repository

**Files:**
- Create: `src/demo/contact-file-repository.ts`
- Modify: `src/types/crm.ts`

**Interfaces:**
- `ContactFileMetaDto`: file metadata without Blob.
- `ContactFileDto`: metadata plus Blob.
- `ContactFileUploadInput`: file name, MIME type, size, and Blob.
- `ContactFileRepository`: `list`, `get`, `save`, `remove`, `reassignContact`, and `removeForContact`.

- [ ] Implement clone-safe memory storage for tests.
- [ ] Implement IndexedDB storage in a dedicated `contact-files` object store.
- [ ] Export one shared browser repository.

### Task 2: API integration and lifecycle

**Files:**
- Modify: `src/api/contracts.ts`
- Modify: `src/api/index.ts`
- Modify: `src/api/mock-adapter.ts`
- Modify: `src/api/frappe-adapter.ts`

**Interfaces:**
- `listContactFiles(contactId)`
- `uploadContactFiles(contactId, files)`
- `getContactFile(fileId)`
- `deleteContactFile(fileId)`

- [ ] Inject the Contact file repository into the Mock API.
- [ ] Apply existing Contact read/write permissions and account scope checks.
- [ ] Validate type, size, and non-empty files in the Mock API.
- [ ] Reassign duplicate-contact files during merge.
- [ ] Remove Contact files during hard delete.
- [ ] Return `NOT_IMPLEMENTED` from the Frappe adapter methods.

### Task 3: Files card and top actions

**Files:**
- Create: `src/features/contacts/ContactFilesCard.vue`
- Modify: `src/pages/ContactDetailPage.vue`

- [ ] Build the Files card with count, click upload, drag-and-drop, file list, download, delete, loading, busy, empty, and error states.
- [ ] Replace the right-side Data Quality card with the Files card.
- [ ] Move the existing merge button to `PageHeader` without changing merge behavior.
- [ ] Restyle only the top delete button as a restrained danger outline with hover and focus-visible states.
- [ ] Preserve the existing responsive detail layout and delete confirmation modal.

### Task 4: Regression and visual verification

**Files:**
- Create: `src/demo/contact-file-repository.test.ts`
- Modify: `src/api/mock-adapter.test.ts`
- Modify: `src/pages/contacts.test.ts`

- [ ] Add post-implementation repository tests for persistence, reassignment, and deletion.
- [ ] Add API tests for permission, validation, upload/download/delete, merge migration, and hard-delete cleanup.
- [ ] Add page tests for the Files card, top merge action, and delete button class.
- [ ] Run focused Vitest suites.
- [ ] Run `pnpm.cmd run typecheck`.
- [ ] Run `pnpm.cmd run build`.
- [ ] Verify the completed workflow in the local browser, including refresh persistence.

