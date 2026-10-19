import frappe

LOG_TITLE = "QIHENG Demo CRM reporting lines put right"


def _account_of(name: str) -> str | None:
    return frappe.db.get_value(
        "Dynamic Link", {"parent": name, "parenttype": "Contact", "parentfield": "links", "link_doctype": "Customer"}, "link_name",
    )


def _usable_line(survivor: str, duplicate: str, candidate) -> bool:
    """Whether the line kept on the merged Contact is one the survivor may be given: a Contact of the same Account,
    active and not merged away, and neither the survivor nor the merged Contact (the merged Contact may itself have
    been left reporting to themselves by an earlier merge)."""

    if not candidate or candidate in (survivor, duplicate):
        return False
    row = frappe.db.get_value("Contact", candidate, ["custom_crm_status", "custom_crm_merged_into"], as_dict=True)
    if not row or row.custom_crm_status != "Active" or row.custom_crm_merged_into:
        return False
    return _account_of(candidate) == _account_of(survivor)


def execute():
    """A merge used to make a Contact report to themselves, or close a longer loop, and left the merged Contact
    with a line of its own (F1-06); a line that comes back on itself is no line, and a merged Contact reports to
    nobody. A Contact who reports to themselves was a survivor who reported to the duplicate being merged into
    them: when one Contact alone was merged into them, its own line, kept on the archived record, is theirs (none
    if it had none); when more were, which of them they reported to cannot be told, and the line is cleared. The
    edge that closes each longer loop is cut. What was changed is logged, for whoever puts a line right by hand."""

    restored: list[str] = []
    cleared: list[str] = []
    self_reporting = frappe.db.sql_list("SELECT `name` FROM `tabContact` WHERE `custom_crm_reports_to` = `name`")
    # The lines kept on the merged Contacts are read before any line is changed: a merged Contact may be among
    # the self-reporting ones itself, and its line is judged as it was, whichever of the two comes first.
    merged_lines = {
        name: frappe.db.sql(
            "SELECT `name`, `custom_crm_reports_to` FROM `tabContact` WHERE `custom_crm_merged_into` = %s", (name,),
        )
        for name in self_reporting
    }
    for name in self_reporting:
        merged_in = merged_lines[name]
        candidate = merged_in[0][1] if len(merged_in) == 1 else None
        line = candidate if len(merged_in) == 1 and _usable_line(name, merged_in[0][0], candidate) else None
        frappe.db.set_value("Contact", name, "custom_crm_reports_to", line, update_modified=False)
        if line:
            restored.append(f"{name} -> {line} (the line of {merged_in[0][0]}, merged into them)")
        elif len(merged_in) == 1 and candidate and candidate != name:
            cleared.append(f"{name} ({merged_in[0][0]}, merged into them, had a line that cannot be restored: {candidate})")
        elif len(merged_in) == 1:
            cleared.append(f"{name} ({merged_in[0][0]}, merged into them, had no line)")
        else:
            cleared.append(f"{name} ({len(merged_in)} Contacts merged into them)")
    merged = frappe.db.sql_list(
        "SELECT `name` FROM `tabContact` WHERE IFNULL(`custom_crm_merged_into`, '') != '' "
        "AND IFNULL(`custom_crm_reports_to`, '') != ''",
    )
    if merged:
        frappe.db.set_value("Contact", {"name": ["in", merged]}, "custom_crm_reports_to", None, update_modified=False)
    lines = dict(frappe.db.sql(
        "SELECT `name`, `custom_crm_reports_to` FROM `tabContact` WHERE IFNULL(`custom_crm_reports_to`, '') != ''",
    ))
    cut: list[str] = []
    for start in list(lines):
        seen: list[str] = []
        current = start
        while current in lines and current not in seen:
            seen.append(current)
            current = lines[current]
        if current in seen:
            # `current` begins the loop; the Contact whose line leads back into it is cut off from it.
            loop = seen[seen.index(current):]
            last = loop[-1]
            frappe.db.set_value("Contact", last, "custom_crm_reports_to", None, update_modified=False)
            del lines[last]
            cut.append(" -> ".join(loop + [current]))
    if restored or cleared or merged or cut:
        # Which edge a loop lost depends on the order the rows came in: a record of it, where a migrate's logger
        # would drop it (Frappe logs at ERROR by default).
        sections = (
            ("Self-reporting Contacts given the line of the Contact merged into them", restored),
            ("Self-reporting Contacts whose line was cleared", cleared),
            ("Merged Contacts whose own line was cleared", merged),
            ("Loops cut at their last edge", cut),
        )
        message = chr(10).join(f"{title}:{chr(10)}{chr(10).join(rows)}" for title, rows in sections if rows)
        frappe.log_error(title=LOG_TITLE, message=message)
        print(
            f"rayher_crm: reporting lines put right ({len(restored)} restored, {len(cleared)} cleared, "
            f"{len(merged)} merged Contacts' lines cleared, {len(cut)} loop(s) cut), see Error Log '{LOG_TITLE}'"
        )
