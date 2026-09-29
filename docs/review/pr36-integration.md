# PR #36 integration — 2026-09-17

> 历史集成记录：本文的 PO 日期缺失及按系统时间计数已被 2026-09-18 的 [实际 PO 日期口径](actual-po-date-integration.md) 替代；不再作为当前开发要求。


## Local baseline

Review branch `codex/review-cockpit` now builds on PR #36 commit `5c5f27d17202fa4c066528b769df58341061622a` (parent baseline `9035e78`, PR #35). Fast-forwarded with Git autostash; all local Review changes were reapplied without conflicts. The main checkout was not modified. The Review changes are prepared for the shared branch and PR; deployment is handed off to Claude. See [staging handoff](staging-handoff.md).

PR: https://github.com/kizzhang/PlanckSemicon_CRM/pull/36

## Compatible now in source

PR #36 extends existing custom business methods; it adds no new `api/v1` endpoint. Review keeps its own aggregation endpoints, and the browser never calls generic Frappe resource/client APIs.

| Contract | PR #36 behavior | Review integration |
| --- | --- | --- |
| `opportunities.create_strategy_opportunity` | Requires `probabilityLevel`; shared creation writes initial probability history. | Source editor and mock changes included; initial assignment is excluded from downgrade warnings. |
| `leads.convert_lead` | Requires `opportunityProbabilityLevel`; writes the initial opportunity probability. | Conversion UI and types included. Qualified-lead activity still uses conversion time, not a new qualification field. |
| `opportunities.update_strategy_opportunity` | Downgrade requires `probabilityReason`; existing level cannot be cleared. | Source editor and mock changes included. Review does not duplicate this write workflow. |
| Opportunity detail `probabilityHistory[].reason` | Adds reason to returned history and the Small Text schema field. | Cockpit bulk loader reads the same history field; `cockpit.get_details` returns it and Review renders it. Earlier rows without a reason remain unrecorded. |
| Probability ranking | `low_probability < pipeline < upside < committed`. | Same shared vocabulary; earlier downgrade remains visible after a later upgrade. |

## Remaining prerequisites

| Area | What is missing | Current behavior |
| --- | --- | --- |
| Region | Customer Select/shared custom options, normalization and verified migration are not implemented by #36. | Region is retained in scope but disabled until ready; no mixed-language aggregation. Reads Customer master, never opportunity `sub_region`. |
| Reliable historical totals | Evidence of rollout, migration and audited write paths for each source. | Recorded detail can be shown; affected totals show insufficient data until coverage is proven. |
| Actual order CNY amount, amount gap and attainment | Booking still lacks the agreed actual CNY amount and PO business date. | Actual financial metrics remain unavailable. S7 YTD uses system `po_confirmed` time, which needs no PO business date. |
| Live integration | #35 rehearsal, #36 reason schema migration, Review target DocType migration, deployed site sessions. | Local source compatibility only; no claim of site verification. |
| Cockpit API ownership | #36 supplies no cockpit aggregation or target endpoints. | Our `get_review`, `get_details`, `save_target` implementation remains responsible; targets are individual only. |

Existing visits, converted leads, completed Test Runs, first-published quotations and Action history sources remain usable under the agreed definitions. #36 does not remove historical-coverage prerequisites.

## Verification

See [validation.md](validation.md) for commands, results and remaining site/browser acceptance work. Focused checks cover initial assignment exclusion, retaining a downgrade after an upgrade, and rendering the returned reason through the cockpit business API.
