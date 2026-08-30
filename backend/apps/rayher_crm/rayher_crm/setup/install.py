"""Idempotent installation and migration hooks."""

import frappe

from rayher_crm.permissions.roles import install_roles
from rayher_crm.permissions.scope import install_crm_doc_permissions
from rayher_crm.setup.custom_fields import install_crm_schema
from rayher_crm.setup.controlled_documents import install_approved_controlled_documents
from rayher_crm.setup.demo_report_cleanup import cleanup_external_demo_reports
from rayher_crm.setup.enum_normalization import normalize_crm_enums
from rayher_crm.setup.indexes import install_stage5f_indexes
from rayher_crm.setup.money_schema import enforce_money_column_contract


from erpnext.regional.address_template.setup import set_up_address_templates

SYSTEM_TIME_ZONE = "Asia/Shanghai"


def configure_system_timezone() -> None:
    frappe.db.set_single_value("System Settings", "time_zone", SYSTEM_TIME_ZONE)


def ensure_default_address_template() -> None:
    if frappe.db.exists("Address Template", {"is_default": 1}):
        return
    existing = frappe.get_all("Address Template", pluck="name", limit=1)
    if existing:
        frappe.db.set_value("Address Template", existing[0], "is_default", 1)
        return
    country = frappe.defaults.get_global_default("country") or "China"
    set_up_address_templates(default_country=country)


def after_install() -> None:
    configure_system_timezone()
    ensure_default_address_template()
    install_roles()
    install_crm_schema()
    install_crm_doc_permissions()
    install_stage5f_indexes()
    enforce_money_column_contract()
    normalize_crm_enums()
    install_approved_controlled_documents()


def after_migrate() -> None:
    configure_system_timezone()
    ensure_default_address_template()
    install_roles()
    install_crm_schema()
    install_crm_doc_permissions()
    install_stage5f_indexes()
    enforce_money_column_contract()
    normalize_crm_enums()
    install_approved_controlled_documents()
    cleanup_external_demo_reports()
