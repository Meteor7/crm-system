# CRM Clean Runtime and Account Center Design

## Scope

- Frappe mode must never render Mock approval requests, requirement notifications, identities, or timestamps.
- Document Center Manager view reads only backend data; when no approval source exists, it shows an explicit empty state.
- Message Center loads recipient-scoped `CRM Notification Event` rows from Frappe and writes read state back to Frappe.
- The top-right identity switcher becomes an Account Center opened by a classic gear icon.
- Account Center shows current account information and a Setting form for changing the current Frappe user's password.

## Password boundary

- Require current password, new password, and confirmation.
- Server verifies the current password and enforces at least 12 characters with upper-case, lower-case, digit, and special character.
- Password values never enter logs, audit documents, notifications, or frontend persistence.

## Empty-state boundary

- Current backend business counts are zero for Customer, Lead, CRM Opportunity, Booking, Visit, Demo Request, Evaluation, Installed Tool, and Notification Event.
- Existing Contact and File Access Audit rows are not deleted in this UI fix; destructive database cleanup requires a separately reviewed target list.

## Verification

- Run focused existing tests after implementation, then typecheck/build.
- Rebuild only the new `rayher-crm-stage1-local` Docker stack image and verify `/crm`, Manager Document Center, Message Center, and Account Center in the browser.

