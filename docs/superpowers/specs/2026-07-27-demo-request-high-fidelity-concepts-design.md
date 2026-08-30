# Demo Request High-Fidelity Concepts

## Goal

Generate three desktop high-fidelity reference images from the supplied hand-drawn prototype. The images are visual references only and do not modify the running CRM.

## Shared Structure

- 16:9 desktop CRM interface.
- Match the current QIHENG DEMO application shell, sidebar, top bar, page header, filter controls, cards, radii, shadows, typography, and spacing.
- Inside Demo Request, use four peer-level workspace tabs:
  `Demo Request`, `Sales Preparation`, `Engineer Review`, and `Manager Approval`.
- `Demo Request` is the overview of all requests. It is not a workflow stage and must never appear as step 1 in a progress indicator.
- Place a Sales owner filter and scrollable Demo request list in a narrow left rail.
- Place the selected request workspace in the large right panel.
- Keep the interface implementation-friendly, readable, and business-oriented.

## Visual System

- Primary accent: `#FE9900`.
- Supporting colors: charcoal `#24272D`, warm white `#F6F4F0`, white surfaces, muted grey borders.
- Use orange only for active states and primary actions.
- Use restrained green for approved states, amber for pending states, and red only for blocking issues.
- Use the current project typography, generous spacing, restrained shadows, and existing radius language.
- No gradients, glassmorphism, decorative blobs, mobile layouts, or generic KPI-card clutter.

## Concept 1: Demo Request Overview

- `Demo Request` tab is active.
- Show overview counts and all-request status distribution.
- The left rail contains every request and supports Sales owner filtering.
- The right workspace provides a useful selected-request overview without implying that Demo Request is a process step.

## Concept 2: Sales Preparation Form

- `Sales Preparation` tab is active.
- Right workspace is an editable Sales preparation form.
- Group fields into customer context, demo objective, equipment/sample requirements, schedule, and notes.
- Include completion guidance and a clear submit-for-engineering action.

## Concept 3: Review and Approval Desk

- `Engineer Review` or `Manager Approval` tab is active as appropriate.
- Right workspace emphasizes engineering feasibility, customer questions, risk checks, manager decision, and audit history.
- Show role ownership and approval status clearly.
- Present approve, return, and request-information actions with unambiguous hierarchy.

## Output

- Generate three separate horizontal images, one image per concept.
- Keep the same sample request, current-project visual system, navigation, and data across all three images so the layouts can be compared directly.

## Approved Typography Adjustment

- Scope is limited to the four Demo Request workspace views.
- Increase auxiliary copy from `9px` to `11px`.
- Increase table, list, field, and body copy from `10–11px` to `12–13px`.
- Increase card section headings from `13px` to `15px`.
- Keep the page title, application shell, layout, spacing, controls, workflow, and other modules unchanged.
- Verify the desktop layout at the running `4173` preview with no horizontal overflow or clipped controls.
