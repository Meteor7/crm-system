# Native File and User lists

The native lists include REST resource lists, `frappe.client` list/value/count,
report views and link search. Their CRM filters are registered and checked on
fresh installation and every migration.

## File policy

`services.managed_file_access.file_query` is the single CRM File list hook.
It combines the existing managed-file rules with the ordinary parent rule:

| File category | Native list for non-Administrator users |
| --- | --- |
| Service-backed Contact file | Current Contact/Account scope, stakeholder capability, live metadata and valid upload provenance |
| Service-backed Visit file | Current Visit scope and valid upload provenance |
| Controlled document, other service or CRM-module attachment | Hidden; existing delivery services decide access |
| Ordinary private attachment directly on Customer, Contact or Lead | Hidden, including for the CRM owner or Manager |
| Ordinary private attachment on a CRM site or an Address with a missing Customer link | Hidden |
| Ordinary attachment on another ERP Address or unrelated DocType; own unattached upload | Existing Frappe policy |

Administrator retains the core list. Contact/Visit scope revocation still
removes native list, detail and private-byte access even for the original uploader.
The ordinary parent restriction adds no native download grant and does not
change the existing managed-file upload, alias, detail or download guards.
Private ordinary CRM-parent files cannot be shared directly: Frappe otherwise
ORs DocShare grants outside the list predicate. Installation/migration removes
old grants, and File reparenting and Address/Customer promotion revoke grants
before entering the restricted boundary. Making a file private also revokes
restricted shares on its same-path siblings. Ordinary ERP and public-file sharing
retain their existing policy.
Editing an existing File or User share while its permission boundary is being
changed fails with a retry message instead of waiting in the opposite lock order.

Frappe 15's core File predicate has ungrouped public/unattached/attached OR
branches. The additional ordinary-parent rule limits private attached rows;
it does not privatize or hide already-public ordinary files. Managed service
uploads remain private and attached through the existing migration and write
guards. This change is not a new delivery service for ordinary Desk attachments.

## User policy

Sales and Engineer identities can list only their own User row, including when
they also hold an ERP role. Their CRM personnel directory still comes from
`bootstrap`. Administrator, System Manager, CRM Manager and identities without
a CRM role keep Frappe's existing User list. Manager must be the user's sole CRM
role; ambiguous combinations with Sales or Engineer are restricted too. Adding
an ERP role does not invalidate the Manager exception. The exception preserves
Engineer selection in the Account Engineer Assignment Desk form; it also keeps
the existing access to native User columns such as last login and IP address.
This is a row restriction, not a field-redaction change.
Foreign User shares to restricted identities and everyone shares are refused;
old shares are removed on installation/migration and role changes. Core User
self-shares and shares to exempt identities remain available.

The User query hook is separately inventoried with Frappe's core User hook.
It has no CRM detail hook or CRM-owned schema/DocPerm reconciliation. Removing
the restriction, duplicating a File key or changing either effective hook order
must fail the permission registry gate.

## Regression coverage

Run `test_native_lists`, `test_permission_registry`, `test_contact_file_api`,
`test_visit_api`, `test_private_file_lifecycle` and
`test_controlled_document_delivery` together. The Stage 5F HTTP acceptance
also checks authorized Contact reads, ordinary-parent and Demo metadata denial,
User row restrictions, and list/private-byte revocation after an Account transfer.
The release gate still requires the full native and HTTP suites.
