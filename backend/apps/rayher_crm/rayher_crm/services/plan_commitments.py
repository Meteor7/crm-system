"""Manager-recorded period activity promises, separate from current scheduling."""
from datetime import date

import frappe

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import CRM_ROLE_TO_PROFILE
from rayher_crm.services.common import as_payload, ensure_server_generated_id, normalize_expected_modified, to_iso_timestamp
from rayher_crm.services.cockpit_metrics import metric, number, supported_bounds
from rayher_crm.services import cockpit_target_rules as targets

DOCTYPE = "CRM Plan Commitment"
METRICS = ("visits", "leads", "tests", "quotes", "followups", "actions", "events")


def dto(row):
    return {"id": row.name, "sales": row.sales_owner, "metric": row.metric, "period": row.period,
            "anchor": str(row.anchor), "value": str(row.commitment_value), "note": row.note or "",
            "modified": to_iso_timestamp(row.modified), "modifiedBy": row.modified_by}


def save(payload, expected=None):
    from rayher_crm.services.cockpit import require_manager
    require_manager()
    payload = as_payload(payload)
    ensure_server_generated_id(payload)
    owner, key, period = (payload.get(field) for field in ("sales", "metric", "period"))
    if not isinstance(owner, str) or not owner or not isinstance(key, str) or key not in METRICS or not isinstance(period, str) or period not in {"week", "month", "quarter", "year"}:
        raise CrmApiException("VALIDATION_ERROR", "Choose a sales rep, activity and period.")
    try:
        day = date.fromisoformat(payload.get("anchor", ""))
        start, _ = supported_bounds(period, day)
        if day != start:
            raise ValueError()
    except (TypeError, ValueError, OverflowError) as exc:
        raise CrmApiException("VALIDATION_ERROR", "Commitment date must be the first day of its period.") from exc
    value = number(payload.get("value"))
    if value is None or value != value.to_integral_value() or value > 999999999:
        raise CrmApiException("VALIDATION_ERROR", "Commitment must be a non-negative whole count up to 999999999.")
    note = payload.get("note", "")
    if not isinstance(note, str) or len(note.strip()) > 1000:
        raise CrmApiException("VALIDATION_ERROR", "Commitment note must be at most 1000 characters.")
    # The transaction mutex must not be a row with audit-owner columns:
    # User.after_rename scans those tables while already holding User locks.
    # Upsert takes an exclusive lock even on first use, until commit/rollback.
    frappe.db.sql("""INSERT INTO `tabSeries` (`name`, `current`) VALUES (%s, 0)
        ON DUPLICATE KEY UPDATE `current`=`current`""", ("rayher_crm.plan_commitment_write_lock",))
    user = frappe.db.get_value("User", owner, ["name", "enabled"], as_dict=True, for_update=True)
    if not user or not user.enabled:
        raise CrmApiException("VERSION_CONFLICT", "The selected sales rep is no longer available; reload the plan before editing.")
    # MariaDB's case-insensitive Link lookup must resolve before deriving the
    # business identity; Frappe canonicalizes Links only later during insert.
    owner = user.name
    roles = frappe.db.sql("SELECT role FROM `tabHas Role` WHERE parent=%s AND parenttype='User' FOR UPDATE", (owner,), pluck=True)
    if {role for role in roles if role in CRM_ROLE_TO_PROFILE} != {"CRM Sales"}:
        raise CrmApiException("VERSION_CONFLICT", "The selected sales rep's role changed; reload the plan before editing.")
    # A User rename updates the Link but deliberately keeps this record's name.
    # Resolve by the business key under the transaction mutex, retaining its audit.
    records = frappe.db.sql("""SELECT name, modified FROM `tabCRM Plan Commitment`
        WHERE sales_owner=%s AND metric=%s AND period=%s AND anchor=%s
        ORDER BY name FOR UPDATE""", (owner, key, period, day), as_dict=True)
    if len(records) > 1:
        raise CrmApiException("VERSION_CONFLICT", "Multiple commitments exist after a user merge. Resolve the duplicate records before saving.")
    record = records[0] if records else None
    # A renamed user's old email may later belong to a different user. Keep
    # existing IDs, but never derive a new ID from a mutable/reusable Link.
    name = record.name if record else frappe.generate_hash(length=32)
    existing = record.modified if record else None
    if (to_iso_timestamp(existing) if existing else None) != (normalize_expected_modified(expected) if expected else None):
        raise CrmApiException("VERSION_CONFLICT", "Commitment changed; reload before saving.")
    doc = frappe.get_doc(DOCTYPE, name, for_update=True) if existing else frappe.get_doc({"doctype": DOCTYPE, "name": name,
        "sales_owner": owner, "metric": key, "period": period, "anchor": day})
    doc.update({"commitment_value": str(int(value)), "note": note.strip()})
    doc.save(ignore_permissions=True, ignore_version=False) if existing else doc.insert(ignore_permissions=True)
    return dto(doc)


def attach(result, query):
    from rayher_crm.services.cockpit import period_target_rows, targetable_sales
    query = {key: str(query.get(key) or "").strip() for key in ("sales", "market", "region", "equipment")}
    kind, anchor = result["period"]["kind"], result["period"]["start"]
    # Resolve legacy Link casing with the same User collation used on save.
    # Reads preserve stored identity/audit and keep every duplicate inspectable.
    records = [dto(row) for row in frappe.db.sql("""SELECT c.name,
        COALESCE(u.name, c.sales_owner) AS sales_owner, c.metric, c.period,
        c.anchor, c.commitment_value, c.note, c.modified, c.modified_by
        FROM `tabCRM Plan Commitment` c LEFT JOIN `tabUser` u ON u.name=c.sales_owner
        WHERE c.period=%s AND c.anchor=%s""", (kind, anchor), as_dict=True)]
    target_rows = period_target_rows(kind, anchor)
    active = targetable_sales()
    owners = active | {row["sales"] for row in records} | {row["id"] for row in result["sales"] if row["id"]}
    if query.get("sales"):
        owners = {query["sales"]}
    allocated = not any(query.get(key) for key in ("market", "region", "equipment"))
    unavailable = {**metric(None, "not_applicable", "not_allocated_to_scope"), "record": None}
    names = {row["id"]: row["name"] for row in result["filters"]["sales"]}
    plans = {row["id"]: row for row in result["sales"]}
    output = []
    for owner in sorted(owners):
        mine = [row for row in records if row["sales"] == owner]
        my_targets = [row for row in target_rows if row["sales"] == owner]
        entries = []
        for key in METRICS:
            commitment = targets.target(mine, key, kind, anchor) if allocated else dict(unavailable)
            matches = [row for row in mine if row["metric"] == key] if allocated else []
            if len(matches) > 1:
                # Keep every preserved record inspectable without choosing a
                # winner or allowing the ambiguous business key to be edited.
                commitment["conflicts"] = sorted(matches, key=lambda row: row["id"])
            entries.append({"key": key,
                "scheduled": plans.get(owner, {}).get(key, metric(0)) if key != "leads" else metric(None, "not_applicable", "no_lead_schedule"),
                "commitment": commitment,
                "target": (targets.target(my_targets, key, kind, anchor) if key not in {"actions", "events"} else {**metric(None, "not_applicable", "no_activity_target"), "record": None}) if allocated else dict(unavailable)})
        output.append({"id": owner, "name": names.get(owner, owner), "canEdit": owner in active and allocated, "activities": entries})
    team = []
    for key in METRICS:
        contributors = {row.get("id") for row in result["sales"] if row.get(key, {}).get("state") == "insufficient" or row.get(key, {}).get("value")}
        members = ({query["sales"]} if query.get("sales") else active | {row["sales"] for row in records if row["metric"] == key} | contributors)
        members = {member or "__unknown_sales_owner__" for member in members}
        team.append({"key": key,
            "scheduled": result["summary"].get(key, metric(None, "not_applicable", "no_lead_schedule")),
            "commitment": targets.aggregate(records, members, key, kind, anchor, "sales", non_targetable=members - active) if allocated else dict(unavailable),
            "target": (targets.aggregate(target_rows, members, key, kind, anchor, "sales", non_targetable=members - active) if key not in {"actions", "events"} else {**metric(None, "not_applicable", "no_activity_target"), "record": None}) if allocated else dict(unavailable)})
    # Version is the existing immutable audit trail. Include only this period's
    # current records, with a per-record cap shown by the UI.
    visible = {row["id"] for row in records if row["sales"] in owners} if allocated else set()
    histories = {name: [] for name in sorted(visible)}
    # MariaDB 10.6 ranks each visible record independently. Chunk IDs to bound
    # SQL parameters, rather than issuing one Version query per commitment.
    visible_ids = sorted(visible)
    for offset in range(0, len(visible_ids), 500):
        batch = visible_ids[offset:offset + 500]
        placeholders = ", ".join(["%s"] * len(batch))
        versions = frappe.db.sql(f"""SELECT name, docname, creation, owner, data FROM (
            SELECT name, docname, creation, owner, data,
                   ROW_NUMBER() OVER (PARTITION BY docname ORDER BY creation DESC, name) AS history_rank
            FROM `tabVersion` WHERE ref_doctype=%s AND docname IN ({placeholders})
        ) ranked WHERE history_rank <= 20 ORDER BY docname, history_rank""", (DOCTYPE, *batch), as_dict=True)
        for row in versions:
            histories[row.docname].append({"id": row.name, "at": to_iso_timestamp(row.creation), "actor": row.owner,
                                          "changes": (frappe.parse_json(row.data) or {}).get("changed", [])})
    result["commitments"] = {"people": output, "team": team, "allocated": allocated, "history": histories}
