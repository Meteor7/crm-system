"""Durable owner identities alongside unchanged Opportunity audit text."""
import frappe

from rayher_crm.api.v1.errors import CrmApiException


def _identity_pair(source, target, *, current=False):
    rows = frappe.db.sql("""SELECT name, creation, enabled,
        name=%s AS is_source, name=%s AS is_target FROM `tabUser`
        WHERE name IN (%s, %s) ORDER BY name""" + (" LOCK IN SHARE MODE" if current else ""),
        (source, target, source, target), as_dict=True)
    return {side: next((row for row in rows if row[f"is_{side}"]), None) for side in ("source", "target")}


def lock_users_before_rename(doc, method, old, new, merge):
    # Native merge otherwise does not lock the source User before traversing
    # its Links. Both rename and merge must precede Opportunity locks.
    from rayher_crm.services.user_identity import lock_user_pair
    users = lock_user_pair(old, new)
    if merge and len(users) == 2:
        reject_target_merge_collisions(old, new.strip())
        reject_commitment_merge_collisions(old, new.strip())


def reject_target_merge_collisions(source, destination):
    if not frappe.db.table_exists("CRM Cockpit Target"):
        return
    # The two User locks block target saves before they can insert or update.
    # Use a current read even when native rename started with an older snapshot.
    # Never acquire the target Series mutex here: saves take Series before User.
    collisions = frappe.db.sql("""SELECT a.name, b.name
        FROM `tabCRM Cockpit Target` a JOIN `tabCRM Cockpit Target` b
          ON a.metric=b.metric AND a.period=b.period AND a.anchor=b.anchor
        WHERE a.sales_owner=%s AND b.sales_owner=%s
          AND COALESCE(NULLIF(a.target_scope, ''), 'Sales')='Sales'
          AND COALESCE(NULLIF(b.target_scope, ''), 'Sales')='Sales'
        LIMIT 1 FOR UPDATE""", (source, destination))
    if collisions:
        frappe.throw("These users have conflicting cockpit targets for the same metric and period. "
                     "Reconcile their targets before merging users.")


def reject_commitment_merge_collisions(source, destination):
    if not frappe.db.table_exists("CRM Plan Commitment"):
        return
    # The ordered User locks also precede commitment writes. Keep a current
    # read here and never take their Series mutex (writes take Series first).
    collisions = frappe.db.sql("""SELECT a.name, b.name
        FROM `tabCRM Plan Commitment` a JOIN `tabCRM Plan Commitment` b
          ON a.metric=b.metric AND a.period=b.period AND a.anchor=b.anchor
        WHERE a.sales_owner=%s AND b.sales_owner=%s
        LIMIT 1 FOR UPDATE""", (source, destination))
    if collisions:
        frappe.throw("These users have conflicting plan commitments for the same metric and period. "
                     "Reconcile their commitments before merging users.")


def lock_opportunity_owners(name, payload):
    from rayher_crm.services.common import resolve_write_owner
    from rayher_crm.permissions.roles import CRM_ROLE_TO_PROFILE

    source = frappe.db.get_value("CRM Opportunity", name, "opportunity_owner")
    requested = resolve_write_owner(payload.get("owner", source))
    snapshot = _identity_pair(source, requested)
    current = _identity_pair(source, requested, current=True)
    for side in ("source", "target"):
        old, actual = snapshot[side], current[side]
        if ((old.name, old.creation) if old else None) != ((actual.name, actual.creation) if actual else None):
            raise CrmApiException("VERSION_CONFLICT", "An owner identity changed. Reload before saving.")
    target = current["target"]
    if not target or not target.enabled:
        raise CrmApiException("INVALID_OWNER", "Owner must be an active CRM Manager or Sales user.")
    if target.name != "Administrator":
        roles = frappe.db.sql("SELECT role FROM `tabHas Role` WHERE parent=%s AND parenttype='User' LOCK IN SHARE MODE",
                              (target.name,), pluck=True)
        assigned = {role for role in roles if role in CRM_ROLE_TO_PROFILE}
        if assigned not in ({"CRM Manager"}, {"CRM Sales"}):
            raise CrmApiException("INVALID_OWNER", "Owner must be an active CRM Manager or Sales user.")
    return {"source": current["source"].name if current["source"] else source, "target": target.name}


def check_current_opportunity_owner(name, locked):
    # Native Link renames don't change Opportunity.modified. Also check the
    # identity under the parent lock, using the database's Link collation.
    matches = frappe.db.sql("""SELECT COALESCE(opportunity_owner, '')=%s
        FROM `tabCRM Opportunity` WHERE name=%s FOR UPDATE""", (locked["source"] or "", name), pluck=True)
    if matches != [1]:
        raise CrmApiException("VERSION_CONFLICT", "The owner identity changed. Reload before saving.")


def capture_owner_identity(doc):
    doc.from_owner = doc.to_owner = None
    doc.owner_identity_resolved = 0
    if doc.field != "opportunity_owner":
        return
    identities = _identity_pair(doc.from_value, doc.to_value, current=True)
    at = frappe.utils.get_datetime(doc.at)
    for side, key in (("from", "source"), ("to", "target")):
        user = identities[key]
        # A later-created email cannot prove the identity of a historical event.
        doc.set(f"{side}_owner", user.name if user and user.creation and user.creation <= at else None)
    doc.owner_identity_resolved = 1


def backfill_owner_identities():
    # One pass marks unresolved identities too. Do not revisit them after email
    # reuse, or re-infer proven identities after a native merge to a newer User.
    frappe.db.sql("""UPDATE `tabCRM Opportunity History` h
        LEFT JOIN `tabUser` before_user ON before_user.name=h.from_value AND before_user.creation<=h.at
        LEFT JOIN `tabUser` after_user ON after_user.name=h.to_value AND after_user.creation<=h.at
        SET h.from_owner=before_user.name, h.to_owner=after_user.name, h.owner_identity_resolved=1
        WHERE h.field='opportunity_owner' AND COALESCE(h.owner_identity_resolved, 0)=0""")
