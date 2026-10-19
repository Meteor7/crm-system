# PLANCK Desktop Brand Design

## Goal

Replace the desktop sidebar's temporary QIHENG Demo brand cluster with the approved QIHENG DEMO logo while preserving the current CRM layout and behavior.

## Approved visual direction

- Use `planck-logo-standard.png` from the desktop Logo folder.
- Render the horizontal logo directly on the charcoal sidebar without a card, border, glow, or extra label.
- Target a width of about `176px`, preserve the source aspect ratio, and align it with the navigation content.
- Remove the generated three-bar mark, `QIHENG Demo`, and `客户经营系统` text.
- Keep the existing sidebar close control available for the current responsive navigation.

## Scope boundaries

- Desktop sidebar only.
- No mobile header redesign.
- No favicon change.
- No repeated company logo in KPI, customer, opportunity, or Demo cards.
- No navigation, data, color-token, or business-flow changes.

## Acceptance criteria

- The sidebar exposes one accessible image with alt text `QIHENG DEMO`.
- The old QIHENG Demo mark and product subtitle no longer render.
- The logo is copied into the project and does not depend on the desktop source folder at runtime.
- The focused AppShell test, typecheck, production build, and browser visual check pass.
