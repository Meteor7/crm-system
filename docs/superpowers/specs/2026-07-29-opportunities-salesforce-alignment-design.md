# Opportunities Salesforce Alignment Design

## Goal

Adapt the approved Salesforce Opportunities list and Path detail structure to the Planck semiconductor CRM Demo without copying Salesforce branding or removing the existing opportunity strategy capabilities.

## Scope

- Keep `Leads&Opportunities` as the left-navigation module name.
- Keep Leads and Opportunities as the vertical switch inside that module.
- Show Opportunities as a dedicated list view by default.
- Open an Opportunity in a dedicated detail route.
- Keep Booking as an independent left-navigation module.
- Apply the approved search style A to Leads, Opportunities, and Booking searches.
- Preserve Mock persistence and permissions. Frappe mutations remain explicitly unsupported.

## Opportunity List

The Opportunities view uses the Salesforce list hierarchy while retaining Planck styling:

- Header: `Opportunities`, record count, and `新增 Opportunity`.
- Toolbar: one shared styled search field plus Stage, Forecast, and Owner filters.
- Table columns: Opportunity, Account / Site, Stage, Close Date, Amount / Probability, Forecast, Owner, Updated.
- Clicking an Opportunity name navigates to `/opportunities/:opportunityId`.
- Creating an Opportunity reuses `OpportunityEditorModal` and navigates to the created record.
- Empty, loading, permission-denied, and error states reuse the current design-system components.

## Opportunity Detail

The detail page follows the reference image hierarchy:

1. Record header with back navigation, Opportunity identity, account, edit action, and new Action action.
2. Horizontal Path showing the ordered sales stages. Completed stages are marked, the current stage uses the Planck orange emphasis, and `推进到下一阶段` updates the current record through the existing API.
3. Responsive three-column workspace:
   - Left: About and Status fields.
   - Center: Action Plan, Change History, and Commercial Forecast.
   - Right: Buying Influence, Strength, Red Flag, and Information Needed.
4. Existing stakeholder, action, contact, and opportunity edit flows stay available.

The stage order is:

1. 需求发现
2. 技术确认
3. Demo 验证
4. 商务谈判
5. 采购流程
6. Won

`Lost` is treated as a closed terminal state and is not advanced by the Path action.

## Shared Search Style A

The compact search field matches the top navigation search language:

- 38px control height.
- Warm white surface.
- 1px neutral border and 10px radius.
- Muted search icon and placeholder.
- Stronger neutral border on hover.
- Planck orange border and soft three-pixel focus ring on `:focus-within`.
- Minimum width on desktop and full-width behavior on narrow layouts.

Only search inputs adopt this shared utility. Select filters retain their existing behavior and are height-aligned.

## Responsive Behavior

- The list toolbar wraps without page-level horizontal overflow.
- The table remains horizontally scrollable inside its card.
- The Path scrolls horizontally when needed rather than compressing stage labels.
- The detail workspace changes from three columns to one column at narrow widths.
- Primary actions stay visible and keyboard focus remains apparent.

## Acceptance Criteria

- Leads, Opportunities, and Booking searches share the same rendered style and focus treatment.
- Opportunities initially render as a searchable list, not as the previous inline strategy dashboard.
- Clicking a listed Opportunity opens its dedicated detail URL.
- The detail includes Path, About, Status, Action Plan, Change History, Commercial Forecast, Buying Influence, Strength, Red Flag, and Information Needed.
- Stage advancement persists through the existing Mock API.
- Creating and editing Opportunities and Actions still work.
- Booking remains independent and does not regress.
- Focused tests, typecheck, production build, desktop browser QA, and one narrow viewport QA are completed.

## Delivery Boundary

This remains a Mock-backed browser Demo. Salesforce is a structural reference only. No Salesforce connector, Frappe Opportunity mutation, database migration, or production audit trail is introduced.
