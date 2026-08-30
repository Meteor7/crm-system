# CRM User Manual Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a complete, role-based Chinese user operation manual that matches the current CRM UI, permissions, workflows, and Demo limitations.

**Architecture:** Keep one authoritative module guide for each navigation entry, then provide concise role task maps that point users to the relevant modules. Separate verified Demo behavior from future Frappe production behavior.

**Tech Stack:** Markdown, Vue page copy, TypeScript permission definitions, current Mock adapter configuration.

## Global Constraints

- Do not describe Boss as the system administrator.
- Use the page labels currently visible in the navigation.
- Distinguish view scope from write or approval permissions.
- Mark `VITE_API_ADAPTER=mock` and the LAN preview boundary explicitly.
- Do not claim real Frappe login, shared database, backend audit, or controlled file delivery is verified.
- Do not add product features or modify application code.

---

### Task 1: Establish the verified role and module map

**Files:**
- Read: `src/domain/permissions.ts`
- Read: `src/demo/identities.ts`
- Read: `src/app/navigation.ts`
- Read: `.env.local`

**Interfaces:**
- Consumes: Current `RoleProfile`, capability lists, Demo identities, and navigation entries.
- Produces: The permission matrix and version statement used by the manual.

- [ ] **Step 1: Record the six user roles and their scope**

Expected roles: CRM Administrator, Management Viewer, Sales Manager, Sales User, FAE / Applied Engineer, Equipment Engineer.

- [ ] **Step 2: Record all ten visible navigation entries**

Expected entries: 信息中心、Calendar、客户档案、Opportunities & Booking、拜访与 Action、Demo 档案、Demo Request、Demo Test、Installed Tools、Document Center.

- [ ] **Step 3: Confirm the active adapter**

Run: `Get-Content .env.local`

Expected: `VITE_API_ADAPTER=mock`

### Task 2: Write the complete operation manual

**Files:**
- Create: `docs/crm-user-operation-manual.md`

**Interfaces:**
- Consumes: The verified role and module map from Task 1.
- Produces: A Chinese manual suitable for browser reading and later Word/PDF conversion.

- [ ] **Step 1: Write document control, scope, quick start, and common UI behavior**

Include the LAN URL, Demo identity switch, stale-data refresh behavior, global customer search, and version boundary.

- [ ] **Step 2: Write the role permission matrix and business flow**

Include Boss, Sales Manager, Sales, FAE, Equipment Engineer, and Demo-only CRM Administrator.

- [ ] **Step 3: Write all module guides**

For each module include purpose, roles, steps, result, and restrictions.

- [ ] **Step 4: Write role task checklists, glossary, FAQ, and limitations**

Ensure users can start from either their role or a module name.

### Task 3: Verify consistency

**Files:**
- Verify: `docs/crm-user-operation-manual.md`

**Interfaces:**
- Consumes: Completed manual.
- Produces: A terminology- and scope-consistent final document.

- [ ] **Step 1: Check required sections**

Run: `rg -n "^## " docs/crm-user-operation-manual.md`

Expected: System scope, roles, business flow, common operations, module guides, role guides, data definitions, FAQ, and limitations are present.

- [ ] **Step 2: Scan for inaccurate authority claims**

Run: `rg -n "Boss（所有权限）|正式系统已|真实数据库已|完整生命周期写入" docs/crm-user-operation-manual.md`

Expected: No matches.

- [ ] **Step 3: Confirm all navigation labels are documented**

Run: `rg -n "信息中心|Calendar|客户档案|Opportunities & Booking|拜访与 Action|Demo 档案|Demo Request|Demo Test|Installed Tools|Document Center" docs/crm-user-operation-manual.md`

Expected: Every navigation label has a dedicated section.

