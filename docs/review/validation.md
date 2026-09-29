# Review development handoff — 2026-09-17

## Location and scope

- Branch: `codex/review-cockpit`, updated to PR #36 `5c5f27d` (on #35 `9035e78`).
- Worktree: `C:/Users/PlanckSemicon/Desktop/testpr3/.codex-tmp/review-cockpit`.
- Review implementation prepared for the shared GitHub branch and PR; no staging deployment by Codex. Deployment steps: [staging-handoff.md](staging-handoff.md).
- Scope and metric definitions: [implementation-contract.md](implementation-contract.md).
- Review replaces the `/dashboard` page. Manager capability `cockpit:view` gates navigation; backend independently resolves the Manager role for every endpoint. Calendar and notification capabilities remain available to their existing roles.

## Custom API

| Endpoint under `rayher_crm.api.v1.cockpit` | Method | Purpose |
| --- | --- | --- |
| `get_review` | GET | Server aggregates all Review sections and returns filter readiness and individual targets. |
| `get_details` | GET | Paginated recorded details using the same filters and period. |
| `save_target` | POST | Save one individual target, with `expectedModified` for updates. |

Queries: `period=week|month|quarter|year`, `anchor=YYYY-MM-DD`, optional `sales`, `market`, `region`. Details add `metric`, `page`, `pageSize` (maximum 200). Target input is `{sales, metric, period, anchor, value}`; default weekly targets use `period=weekly_default` and a future Monday. Monetary targets are decimal strings in CNY. Values distinguish zero / not set / not applicable / insufficient data.

The new `CRM Cockpit Target` DocType must be synchronized through the normal bench migration. Review itself changes no source workflow tables; the included PR #36 adds the probability-history reason field and must also be migrated. The optional probability-history reason column is detected dynamically.

## Checks performed

- `vue-tsc --noEmit`: passed on final frontend source.
- `vite build --mode frappe`: passed; production bundles checked to exclude the local fixture.
- After PR #36 sync: focused Review page and API transport suites passed (33 tests), including reason rendering. Ten additional impacted suites passed (203 tests). Full frontend regression at the earlier #36 baseline passed: 125 suites, 918 tests. Final #36 baseline `5c5f27d` including PR #16 report/visit fixes: 126 suites, 924 tests passed (151 seconds); typecheck, production build and all 14 plain Python metrics tests also passed.
- Plain Python `test_cockpit_metrics.py`: 14 passed, including backdated migration uncertainty, owner/amount replay, currency isolation, PO system-confirmation date and annual deduplication, lead conversion, first publication, stable Test Run sales attribution, and Action history replay/no-op exclusion.
- New Python service/API syntax and target DocType JSON parsed successfully.
- Changed source files were recovered through a trusted writer and checked for exact bytes. Git can review them as text; existing line endings were preserved where applicable.

## Not yet verified

- Live Frappe database, HTTP role sessions, target persistence/concurrent writes and schema migration. `test_cockpit_api.py` provides site integration tests; these require a migrated rehearsal site and were not run here.
- Live-site visual acceptance is still pending. Local Chrome fixture layout acceptance is now complete as recorded below; this does not verify real server data or deployment.
- Region readiness and historical coverage. Follow the configuration/evidence requirements in the scope contract after migration; do not set readiness based only on a commit date or the earliest history row.
- Region normalization/shared options remain pending. Mandatory downgrade reasons from #36 are included locally; rehearse #35 migration, migrate #36 and Review schemas, then run site integration tests before deployment. See [PR #36 compatibility](pr36-integration.md).

## Card layout correction — 2026-09-17

- Matched the PPT panel proportions: wider pipeline column, two stacked cards in each other column, aligned top/bottom edges and 16px gutters. Empty content retains the same card space.
- Pipeline rows place stage label, bar and count on one horizontal row. Lists and sales tables scroll within their card; chart and empty messages fill the remaining card area.
- Browser inspected using explicitly labelled local synthetic fixtures: English empty state, Chinese populated state with target chart, and 20-row overflow state. At 1440px, pipeline is 680px tall; upper cards are 320px, lower cards 344px. At 1930px the full card area is 760px tall. At 1100px the layout uses two columns; at 390px one column, with no page or pipeline-row horizontal overflow.
- Related Vitest suites: 21 passed. Frappe-mode production build passed. This correction changes Review CSS only; no API or metric behavior changes.
- Claude should fetch the latest `codex/review-cockpit` head and rebuild frontend assets for the test server. No additional schema migration is introduced by this layout-only correction.


## Approved preview integrated into production Review — 2026-09-17

- Replaced ReviewPage.vue content with the accepted 63c7c34 layout. Uses the existing AppShell, not the static preview shell. Production has no synthetic records or preview toggles.
- Uses the existing getReview/getReviewDetails/saveReviewTarget transport methods. Added independent individual-chart loading with stale-response protection, versioned target saves, and preserved filter scope; regional/market goals stay not applicable. Region labels use the API text for Claude to localize during integration with server-only release 119b9fc (version reported by the user, not inspected on the server here).
- Loss rows return amount/currency reconstructed at marked_lost time. Tests cover changes after reopening, USD preservation, and absent historical coverage. Sales table uses PO count rather than unavailable actual order amount.
- Full frontend: 126 suites, 930 tests passed (205.78 seconds). Final test type annotation correction passes vue-tsc --noEmit; it does not change runtime behavior. Frappe production build passed.
- Plain Python metrics: 15 tests passed. No live database or HTTP acceptance was run.
- Actual ReviewPage + AppShell were rendered in an ignored local fixture harness, with explicit synthetic-data labeling. Browser checked Chinese and English, populated/insufficient/20-row dense states, independent chart selection, goal dialog and scoped targets. No browser console errors observed.
- At 1958 × 1102 the five main cards measure 744 / 320 / 408 / 357 / 371 px, identical in populated, empty and dense states. At 1440px and 390px there is no page horizontal overflow. Temporary browser viewport settings were restored.
- Claude owns merge and test-server deployment. This verification does not assert server region migration or historical coverage; use staging-handoff.md for the 119b9fc integration constraint.
