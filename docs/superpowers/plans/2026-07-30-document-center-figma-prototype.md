# Document Center Figma Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create an editable high-fidelity Figma prototype for the redesigned Document Center with Direct Access, Access Required, and Admin Review states.

**Architecture:** Create one Figma Design page containing three 1440 × 1024 top-level frames. Reuse one consistent CRM shell and three-column document workspace, then vary the preview and action areas to demonstrate each permission state.

**Tech Stack:** Figma Design, Figma Plugin API, Auto Layout, editable vector and text layers.

## Global Constraints

- Preserve the current CRM left navigation and top bar.
- Use a 1440 × 1024 desktop canvas.
- Use the existing deep navy, warm white, orange, green, amber, and red visual language.
- The left document library contains only All Documents, Technical Documents, and Commercial Documents.
- Version history and download audit remain inside the selected-document detail area.
- Restricted content must not reveal document body text.
- Management Viewer is explicitly read-only.
- Create editable components or reusable structures for repeated navigation, filters, list items, badges, buttons, and permission notices.
- Do not modify CRM source code.

---

### Task 1: Prepare the Figma file and design foundations

**Artifacts:**
- Create: Figma file `PLANCK CRM · Document Center Redesign`
- Create: Figma page `Document Center Redesign`

**Interfaces:**
- Consumes: the approved design specification and the current CRM visual reference.
- Produces: a Figma page, color/type foundations, and three empty top-level frames.

- [ ] Create or select a Figma Design file through the connected Figma app.
- [ ] Inspect existing pages, components, variables, and local styles before adding nodes.
- [ ] Create the `Document Center Redesign` page when it does not already exist.
- [ ] Create `01 · Direct Access`, `02 · Access Required`, and `03 · Admin Review` as 1440 × 1024 frames positioned side by side.
- [ ] Add reusable color and spacing foundations or bind to matching existing variables when available.
- [ ] Validate frame names, dimensions, page placement, and absence of overlap.

### Task 2: Build the shared CRM shell

**Artifacts:**
- Modify: the three top-level frames created in Task 1.

**Interfaces:**
- Consumes: the three frame IDs and design foundations.
- Produces: matching sidebar, top bar, and page-heading regions in all states.

- [ ] Build the deep-navy CRM sidebar with QIHENG DEMO branding and grouped navigation.
- [ ] Highlight `Document Center` with the orange active state.
- [ ] Build the top bar with global search, data timestamp, notification, and current identity.
- [ ] Build the Document Center heading, permission identity chip, search, and filter controls.
- [ ] Validate text hierarchy, spacing, navigation state, and consistent shell geometry across all three frames.

### Task 3: Build the shared three-column workspace

**Artifacts:**
- Modify: the three top-level frames from Task 1.

**Interfaces:**
- Consumes: the shared CRM shell.
- Produces: library navigation, document results, selected-document metadata, and preview container.

- [ ] Build the left library with All Documents, Technical Documents, and Commercial Documents only.
- [ ] Build the center document list with realistic titles, IDs, products, versions, statuses, and classifications.
- [ ] Create a selected-row state and a compact selected-document information section.
- [ ] Build the right preview container with toolbar, page canvas, version metadata, and detail tabs.
- [ ] Place Version History and Download Audit in the right-side detail area.
- [ ] Validate no clipping, overlap, hidden text, or accidental recent-view entry.

### Task 4: Apply the three permission states

**Artifacts:**
- Modify: `01 · Direct Access`, `02 · Access Required`, and `03 · Admin Review`.

**Interfaces:**
- Consumes: the shared workspace.
- Produces: visibly different and internally consistent permission-state screens.

- [ ] In `01 · Direct Access`, show full PDF preview, personalized watermark notice, and a primary controlled-download action.
- [ ] In `02 · Access Required`, select a Restricted document, replace the body preview with a lock overlay, and show an access-reason field plus submission action.
- [ ] Show the submitted request as `Manager Review` without revealing document contents.
- [ ] In `03 · Admin Review`, show request review, version history, download audit, classification, approve, and reject controls.
- [ ] Add a clear read-only badge and disabled mutation controls for the Management Viewer presentation.
- [ ] Validate that Direct, Request, and Admin states can be distinguished without reading annotations.

### Task 5: Final visual verification and delivery

**Artifacts:**
- Inspect: all three top-level frames.
- Deliver: Figma file link and screenshots.

**Interfaces:**
- Consumes: the completed Figma frames.
- Produces: verified screenshots and a user-facing Figma handoff.

- [ ] Capture a screenshot of each top-level frame.
- [ ] Check sidebar and top-bar consistency, column alignment, contrast, text rendering, locked-content privacy, and role-specific controls.
- [ ] Fix any clipping, overlap, inconsistent spacing, placeholder shimmer, or wrong font.
- [ ] Confirm all repeated structures remain editable and Auto Layout is used for structural relationships.
- [ ] Return the Figma file link and summarize the three permission states.

No git commit is included because the Figma artifact is external and the shared repository already contains unrelated staged and unstaged user changes.
