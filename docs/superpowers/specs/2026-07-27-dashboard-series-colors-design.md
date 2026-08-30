# Dashboard Series Colors Design

## Goal

Give the management Dashboard's three business data series a consistent, clearly distinguishable palette.

## Approved mapping

- Pipeline: orange `#FE9900`
- Weighted Pipeline: teal `#0D9488`
- Booking: indigo `#6366F1`

## Scope

- Apply the mapping consistently in Dashboard chart builders and legends.
- Use Booking indigo in booking-only charts.
- Use Pipeline orange and Booking indigo in two-series charts.
- Keep global positive/success colors unchanged so completion and health states retain their existing meaning.
- Do not change KPI data, chart structure, labels, tooltips, or business calculations.

## Acceptance criteria

- Owner performance uses all three approved colors in the approved order.
- Booking-only charts use `#6366F1`.
- Pipeline/Booking comparison charts use `#F97316` and `#6366F1`.
- Chart option tests, typecheck, build, and rendered Dashboard validation pass.
