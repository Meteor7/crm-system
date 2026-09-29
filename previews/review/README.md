# Review standalone UI preview

Open `previews/review/index.html` directly in a browser, or serve it with the existing local Vite server. It uses plain HTML/CSS/JavaScript and the existing PLANCK logo. No backend or installation is needed.

All records are synthetic. There are no CRM requests, authentication, persistence or production route changes. The annual orders chart is an explicitly selected individual's illustrative plan, not a team target. Four activities, sales/region/market filters and original loss records retain the agreed scope.

Interactions: region/market/sales filters, individual chart owner, week/month/quarter/year display, prior/next period, quantity/value bars, local record dialog, English/Chinese, and an empty-state toggle. Period changes use illustrative counts; they are not business calculations and should not be reused as backend logic.

Source files: `index.html`, `style.css`, `layout.css`, `data.js`, `chart.js`, `render.js`, `app.js`. The generated offline deliverable is `artifacts/Review-UI-preview.html` in the local worktree; it inlines all assets and can be copied anywhere.

Visual QA: inspected at the reference 1958 × 1102 canvas, 1440px laptop width and 390px mobile width. No page horizontal overflow. Filled and empty states preserve identical panel sizes. Language, filter, individual target, period and detail interactions were checked. No browser console errors observed. The user approved this visual standard on 2026-09-17. This standalone mock remains a visual reference. The production Review page now adopts its layout inside the existing AppShell and uses the cockpit business APIs. See [backend integration gaps](../../docs/review/approved-ui-backend-contract.md) for the agreed integration work.


## Shared application shell

The approved visual standard retains the existing left navigation and top-right account/role display. Production must reuse `src/app/AppShell.vue` and its bootstrap identity, capability-filtered navigation, locale, notifications and account controls. Only the Review content changes. The standalone preview uses a static Manager identity and disabled links to other modules; it does not log in or call backend APIs. Sidebar collapse, mobile navigation and language switching are interactive. Content breakpoints use the available width after the sidebar.

Shell preview files: `shell.css` and `shell.js`, with existing design tokens. Checked at desktop and mobile sizes; populated and empty panel heights match.
