"""Project the shared activity contract onto already-authorized opportunities."""
from rayher_crm.services.activities import activity_facts, last_activity_at
from rayher_crm.services.cockpit_history import grouped
import frappe


def visible_linked(doctype, fields, field, names):
    if not names or not frappe.has_permission(doctype, "read"):
        return []
    return [dict(row) for row in frappe.get_list(doctype, fields=fields.split(),
            filters={field: ["in", list(names)]}, limit_page_length=0)]


def attach(opportunities, now):
    # No account-wide expansion: a moved source still follows its opportunity,
    # and data from another opportunity never enters this projection.
    from rayher_crm.services.cockpit import linked as child_rows
    linked = visible_linked
    ids = {row["name"] for row in opportunities}
    stages = linked("CRM Opportunity Stage History", "name creation opportunity event recorded_at reached_at reference_doctype reference_name", "opportunity", ids)
    leads = linked("Lead", "name creation custom_crm_status custom_crm_converted_at custom_crm_converted_account custom_crm_converted_opportunity", "custom_crm_converted_opportunity", ids)
    historical_leads = {row["reference_name"] for row in stages if row["event"] == "lead_converted" and row.get("reference_doctype") == "Lead"} - {row["name"] for row in leads}
    leads += linked("Lead", "name creation custom_crm_status custom_crm_converted_at custom_crm_converted_account custom_crm_converted_opportunity", "name", historical_leads)
    requests = linked("CRM Demo Request", "name creation account sales_owner opportunity", "opportunity", ids)
    evaluations = linked("CRM Evaluation", "name creation account demo_request", "demo_request", {row["name"] for row in requests})
    quotes = linked("CRM Quotation", "name creation account quotation_owner ref_no status opportunity", "opportunity", ids)
    quote_ids = {row["name"] for row in quotes}
    data = {
        "opportunities": opportunities, "leads": leads, "stages": stages, "requests": requests, "evaluations": evaluations, "quotes": quotes,
        "history": linked("CRM Opportunity History", "name creation opportunity at field from_value to_value from_owner to_owner", "opportunity", ids),
        "visits": linked("CRM Visit", "name creation account opportunity visit_owner subject visit_date status completed_at customer_kind", "opportunity", ids),
        "actions": linked("CRM Opportunity Action", "name creation opportunity title action_owner due status archived completed_at", "opportunity", ids),
        "tests": linked("CRM Test Run", "name creation evaluation run_date test_round status", "evaluation", {row["name"] for row in evaluations}),
        "versions": linked("CRM Quotation Version", "name quotation version_no published_at account quotation_owner currency total", "quotation", quote_ids),
        # The child inherits its already-visible Quotation parent's permissions.
        "followups": child_rows("CRM Quotation Follow Up", "name parent creation title due status completed_at completed_owner completed_version", "parent", quote_ids),
        "events": linked("CRM Event", "name creation title opportunity account event_owner status start_date end_date completed_at completed_owner", "opportunity", ids),
    }
    histories = grouped(data["history"], "opportunity")
    facts = grouped(activity_facts(data, {}, now), "opportunityId")
    for row in opportunities:
        own = facts.get(row["name"], [])
        row["last_activity_at"] = last_activity_at(own, row["name"], now, histories.get(row["name"], []))
        # An undated completion could be more recent than the evidenced date.
        # Keep the date visible but exclude it from date comparisons and sorting.
        row["last_activity_incomplete"] = any(fact["done"] and not fact["occurredAt"] for fact in own)
