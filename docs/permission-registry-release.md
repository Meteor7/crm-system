# Native permission registration gate

`permissions/registry.py` records each shipped CRM DocType plus Customer, Address,
Contact, Lead and File. Entries identify the parent/current read scope, business
write services, native scope hooks and deliberate native exceptions. The registry
is an inventory and release gate; services and Frappe hooks still authorize each
request. The writer list is documentation, not a runtime service allowlist.

The existing backend test/release gate now checks missing registrations, child-table
classification, replaced/missing hooks, duplicate dictionary keys, both DocShare
guards, the managed File override, unsafe JSON grants and installed effective
DocPerm/Custom DocPerm drift. On an installed site it also checks that every table
field of a DocType with a CRM list hook names a registered child table: Frappe lists
a child table on the parent's DocType-level read alone, so an unregistered one lists
every row (User's `Has Role` and `DefaultValue` did, #219), whoever owns the parent.
Replaced/missing hooks include the write guards in
`doc_events` (Customer, Contact, Lead, Address and User `before_save`, Customer,
Contact, Lead, Address and Customer Group `before_rename`, User `after_rename`,
and File `before_insert`/`before_validate`) and the private file content deletion hook. The
app must keep its single `Rayher CRM` module, which both inventories and the
module-keyed DocShare guards cover.

On an installed site the gate also checks the hooks Frappe actually uses after
merging every installed app: the CRM `has_permission` hook must be the one asked
first (a later app's hook or any `*` hook fails the gate), and the whitelisted
search, File class and file content deletion overrides must be the CRM ones.
For guarded list queries the exact effective sequence must match the reviewed
Frappe Contact, Address or File hook, where applicable, followed by the CRM hook.
Extra, reordered or wildcard handlers and enabled Permission Query Server Scripts
fail the gate. Frappe 15 concatenates SQL fragments without parentheses, so an
additional hook is not necessarily a restriction. Core File's public/unattached
OR branches remain; their safety depends on F2's migrations and write guards
keeping managed files private, attached and free of ordinary aliases. Installed
apps remain trusted code. This checks deployment drift during install/migrate;
it does not monitor later site changes or prove another app's implementation safe.

The same validation runs as the final step of install and migration, after all
setup work, and a drift failure names the differing rows. Run migration with
traffic stopped or in maintenance mode. If validation fails, keep traffic
blocked, correct the drift, and rerun the full migration before reopening it.
Do not add an explicit commit just to retain permission repairs. Frappe's DDL
helpers can commit while indexes or money columns are updated, so a gate failure
may leave permission repairs, share cleanup and earlier schema or patch work
committed. Rollback covers only the transaction still open at the point of failure.
Keep traffic blocked while correcting and retrying the migration, or restore the
verified pre-upgrade backup. The check deliberately does not delete unregistered
custom grants on shared ERP objects. No release gate can protect a deployment
that skips the gate and migration.

CRM Account Engineer Assignment is a Manager-maintained Desk exception. Its CRM
DocPerm rows are now reconciled on migration, including removal of share permission;
Engineer reads still use the current-assignment hook. Address installation keeps
non-CRM roles and All unchanged. CRM Manager is not Frappe Administrator.

Every CRM user holds Frappe's implicit roles (All, Guest and, for Desk users, Desk
User). On Customer, Contact and Lead those roles may hold no unrestricted level-0
read or native write, create, delete, submit, cancel, amend or import grant.
Installation strips All's write,
create and delete again; any other such grant aborts migration until an operator
removes it. On Address they may hold nothing beyond Frappe's shipped owner-only All
create/write row, which the Address hooks refuse for CRM sites. Rows of other ERP
roles on these four shared objects, duplicates included, stay ERP decisions. No
Address `before_delete` hook is registered: Frappe does not fire that event
(deletion runs `on_trash` and `after_delete`). `has_address_permission` refuses
native deletes of CRM sites (#68).

For the types whose CRM rows installation reconciles (the scoped types, Address and
the Assignment), schema grants may be narrower than installed convenience
permissions (such as export), but may not grant a broader operation or role. For
the catalogue, Manager-read, upload-request and service-only types, installation
reconciles nothing, so their schema grants are the installed grants and must equal
the registered rows. Old schema-only Demo/RFQ writes, Engineer Visit/Meeting Record/
stakeholder reads, and Assignment sharing are aligned with the existing runtime policy. No new
business write endpoint is introduced.

This is the first release slice of #68, not closure of its entire authorization
program. The existing Controlled Document metadata catalogue and Manager-native
Document Upload Request administration are recorded as explicit legacy exceptions;
this PR does not claim to solve their delivery/field projection design. General
API endpoint/action/field registration, exhaustive generated HTTP matrices, export
audits and future organization roles remain in #68/#62. B1–B3's actual native and
HTTP regression evidence remains required; matching registry strings cannot prove
the contents of a scope function are correct.
