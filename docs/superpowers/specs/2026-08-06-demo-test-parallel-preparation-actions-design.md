# Demo Test Parallel Preparation and Action Buttons Design

## Goal

Replace the Demo Test status dropdown with explicit workflow actions, persist Wafer Preparation and Test Preparation as independent parallel branches, and make concurrent Manager/Sales writes use optimistic locking without replacing loaded pages with generic load errors.

## Current problem

- `CRM Evaluation` has one linear `status` and no persisted preparation-branch state.
- Project timelines draw two branches, but the Mock adapter hard-codes one seed record and Frappe cannot report either branch independently.
- Demo Test exposes a status dropdown even though the backend permits only the next state or rejection.
- Demo Request edit omits `expectedModified`; transitions have no version argument.
- Non-permission write errors are stored as page-load errors, hiding already loaded data.

## Data model

Add these fields to `CRM Evaluation` and `EvaluationDto`:

- `waferPreparationStatus`: `Pending | Completed`
- `waferPreparationCompletedBy`
- `waferPreparationCompletedAt`
- `testPreparationStatus`: `Pending | Completed`
- `testPreparationCompletedBy`
- `testPreparationCompletedAt`

New Evaluations start with both branches Pending. Legacy records are migrated conservatively:

- `Requested` and `Scope Confirmed`: both Pending.
- `Sample Received`: Wafer Completed, Test Pending.
- `Scheduled` and later statuses: both Completed.

Completing the first branch does not change the Evaluation status. Completing the second branch moves the record to `Scheduled`. `Testing` is allowed only after both branches are Completed.

## API and concurrency

Add `completeEvaluationPreparation(id, branch, expectedModified)` where branch is `wafer` or `test`. The service locks `CRM Evaluation`, records actor/time, and returns the new `modified` value.

Require `expectedModified` for Demo Request edit and transition. Frontend calls always use the selected row's current `modified` value. A stale version returns `VERSION_CONFLICT`; the page reloads the latest rows and shows an inline conflict notice. Permission revocation continues to clear sensitive records.

## Demo Test actions

Remove the status dropdown. The action panel renders only actions valid for the selected record:

- Wafer Preparation: `完成 Wafer Preparation` while Pending.
- Test Preparation: `设置 Test Run DDL` and `完成 Test Preparation` while Pending.
- When both branches are complete: `进入 Test Execution`.
- Testing: `新增 Test Run`; once report readiness permits progression, `完成 Test Execution` moves to Internal Review.
- Internal Review: `提交 Customer Review`.
- Customer Review: `Accept Demo` and `External Report`.
- Every non-terminal stage: `Reject Demo`.

Existing backend transition validation remains authoritative. Buttons do not permit arbitrary skipping.

## Navigation and synchronization

Demo Test navigation becomes:

`Demo Test | Wafer Preparation -> Test Preparation -> Test Execution -> Internal Review -> Customer Review`

Preparation records appear in both preparation views, but each view displays its own persisted branch state. The project-cycle board, lifecycle board, and unified detail timeline use the same two branch fields, including completion actor and date. The combined timeline gate is Done only when both branches are Completed.

Sales can view Demo Test. Manager and the scoped Engineer retain write access under existing capability rules.

## Error handling

- List failures keep the existing full-page DataState.
- Non-permission action failures use an inline alert and preserve loaded rows.
- `VERSION_CONFLICT` reloads current data and tells the user that another user updated the record.
- Permission or scope revocation clears rows and closes write modals.

## Verification

- Domain tests cover branch gate rules, action availability, and legacy mapping.
- Component tests prove there is no status dropdown and every stage shows only valid buttons.
- Page tests cover current `modified`, stale Manager/Sales writes, inline errors, and permission revocation.
- Frappe tests cover branch persistence, double-completion, gate enforcement, version conflicts, workflow projections, and Demo Request transition locking.
- Run full frontend tests, typecheck, Frappe backend tests, production build, deployment, and deployed asset/health checks.

