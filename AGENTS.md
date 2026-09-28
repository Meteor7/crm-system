# Agent guidelines

## Runtime

Frappe is the only runtime, in development and in production. `vite.config.ts`
resolves `@/api/runtime-adapter`, `@/api/identity-switch` and `@/demo/personnel`
to their Frappe versions in every mode except `test` (see
`src/app/runtime-mode.ts`).

## Test doubles

These files exist only for unit tests; nothing a user runs loads them:

- `src/api/mock-adapter.ts`, `src/api/mock-data.ts`, `src/api/runtime-adapter.ts`
  and `src/api/mock-identity-switch.ts`
- `src/features/**/mock-*.ts`
- everything in `src/demo/`, except `personnel.frappe.ts` and the helpers and
  types that production code imports from `identities.ts` and
  `operations-data.ts`. "Demo" in names such as Demo Request means the
  product-demo workflow, not mock data.

Do not extend `mock-adapter.ts` for new features. A test for new behaviour
should stub the `CrmApi` methods it needs (`vi.fn`, `vi.spyOn`) or fake the HTTP
responses through `createFrappeApi({ fetchImpl })`, as
`src/api/frappe-adapter.test.ts` does.

The one exception is the type contract: `createMockApi` returns `CrmApi`, so a
method added to `CrmApi` needs a stub in `mock-adapter.ts` before the project
type-checks. Keep that stub minimal — throw a `CrmApiError` and implement no
behaviour — and cover the feature through the stubs or fakes described above.

## Review guidelines

- Do not report persistence across reloads, concurrency, or parity with backend
  rules in the test doubles above as defects. Raise them only when a test
  depends on the behaviour in question.
- Business rules, permissions and data integrity are enforced by the Frappe app
  in `backend/apps/rayher_crm`; review them against Frappe 15 and MariaDB 10.6
  behaviour.
