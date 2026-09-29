# Review implementation contract

Baseline: PR #36, 5c5f27d17202fa4c066528b769df58341061622a (on PR #35, 9035e78). Isolated branch codex/review-cockpit.

This contract follows the latest product decisions; older workshop documents are historical references.

Visual standard approved on 2026-09-17: [standalone Review preview](../../previews/review/README.md). See [approved UI and backend integration gaps](approved-ui-backend-contract.md). The approved layout now renders in src/pages/ReviewPage.vue inside the existing AppShell. Region labels remain the API storage text; Claude will integrate localized labels from the server-only region release 119b9fc.

- Deliver Manager-only Review, using existing brand colours and Philippe's Review layout. No Plan, full Warnings, Business Pulse, equipment filtering, conversion rates, loss-review workflow or team targets.
- Custom business endpoints only: cockpit.get_review, cockpit.get_details, cockpit.save_target. No generic resource/client calls. Backend owns aggregation and authorization. Notification permissions remain separate.
- Sales, market and customer-master region filters. Region readiness requires verified migration; options come from the shared Customer Select, including custom values. Preset storage uses English names; Chinese UI translates five presets. Opportunity.sub_region never determines filtering.
- Shanghai periods; default last complete Monday–Sunday week. Historical S1–S6 reflect period-end state, one bucket per opportunity. Complete periods compare complete preceding periods; an ongoing period compares equal elapsed progress.
- Four activities: completed visits (Visited / Minutes Submitted / Manager Reviewed), converted leads (converted_at, otherwise linked lead_converted event), completed Test Runs (run_date, Demo Request.sales_owner), first published quotation version (published_at, regardless of current version status). No new qualified_at field.
- S1 count only. S2–S6 sum unweighted, sales-entered Opportunity.amount_cny across original currencies. Blank/zero/invalid CNY amounts make affected totals insufficient; never fall back to the original amount. Historical CNY amounts replay amount_cny changes within verified field-history coverage; pre-backfill values remain missing. Detail, stalled and loss rows also use CNY estimates. See [CNY integration](cny-amount-integration.md). S7 YTD counts current Opportunity-source Bookings in Confirmed / Completed status whose actual_po_date falls from Jan 1 through the selected Shanghai cutoff date. Attribute to the current opportunity owner. Backfill, correction, rollback and cancellation change this current-state total; do not replay po_confirmed events. Missing dates are a separate non-year-scoped count and drilldown. See [actual PO integration](actual-po-date-integration.md). Booking actual CNY amount remains unavailable: actual order amount, gap and attainment stay unavailable.
- Warnings only lost / overdue Action / downgrade. Event warnings follow selected period and count unique opportunities; Action overdue reflects reference-date state, including carryover. Downgrade warnings now use current responsibility and resolution: recording an actual action clears that event; editing a plan does not. Handled events remain in the period's downgrade history. Lost/overdue clearing and snoozing remain outside this change. See [probability recovery](probability-recovery.md).
- Stalled means no substantive Action title/owner/due/status change for 21/35 days. Ignore no-op actionUpdated and deletion. Reuse JSON actionCreated/actionUpdated and soft-archive actionDeleted in Opportunity History.
- Probability ranks low_probability < pipeline < upside < committed. Read optional reason; legacy absence displays unrecorded. PR #36 supplies mandatory downgrade reasons and is included locally; region normalization remains a separate pending module. See [PR #36 integration](pr36-integration.md).
- Loss list covers trailing 12 calendar months; show original reason, no reason classification.
- Only individual targets: annual order amount, default weekly activity targets effective prospectively, and explicit week/month/quarter/year activity overrides. Never sum individual goals into a team goal. Region/market-filtered targets are not applicable.
- Historical coverage must be evidenced by rollout, migration and audited write paths, never the earliest history row. Configuration `crm_cockpit_history_complete_from` maps stage / fields / actions / probability to verified Shanghai timestamps; absent coverage renders affected historical totals insufficient. Administrator/SQL corrections require audit reconciliation before asserting coverage. S7 uses current Bookings and no longer depends on history coverage; the legacy po coverage key is ignored. Missing actual_po_date schema returns insufficient, never zero.
- `crm_cockpit_region_migration_verified` is only set after the region module migration dry-run, mapping approval, execution and verification. Select schema and actual stored values are also checked before enabling region filtering.

## Release validation (not performed automatically by development)

Rehearse #35 migration on a copy, merge source module PRs, migrate schemas, verify region values, document coverage evidence and set only proven coverage boundaries, then exercise manager/sales/engineer HTTP sessions. Do not infer the staging deployment date from a commit timestamp. This branch does not deploy itself.


## 统一应用外壳（用户补充确认）

保留左侧功能导航及右上角姓名、角色、语言、通知和账户入口，正式页直接复用 `src/app/AppShell.vue`。角色来自现有 bootstrap，菜单沿用 capability 权限过滤；不在 Review 内复制身份或权限逻辑，不新增后端接口。Philippe 的设计用于 Review 内容区，按侧栏展开后实际剩余宽度重排，空卡不塌缩。独立预览中的演示身份和禁用导航仅用于展示，正式接入继续使用已有真实路由与账户功能。
