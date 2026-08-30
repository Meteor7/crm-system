from __future__ import annotations

import importlib.abc
import sys
from typing import Any


TRUE_MARKERS = {True, 1, "1", "true"}


def assert_dedicated_test_site(marker: Any, site: str | None) -> None:
    normalized_marker = marker.strip().lower() if isinstance(marker, str) else marker
    normalized_site = str(site or "").strip().lower()
    if normalized_marker not in TRUE_MARKERS or not normalized_site.endswith(".test"):
        raise RuntimeError(
            "CRM tests require a dedicated CRM test site ending in '.test'; "
            "refusing to run against operational data."
        )


def before_tests() -> None:
    import frappe
    from erpnext.regional.address_template.setup import set_up_address_templates

    assert_dedicated_test_site(frappe.conf.get("crm_test_site"), frappe.local.site)
    if not frappe.db.exists("Address Template", {"is_default": 1}):
        set_up_address_templates(default_country="United States")
        frappe.db.commit()


def guard_test_module_import() -> None:
    try:
        import frappe
    except ModuleNotFoundError:
        return

    site = getattr(frappe.local, "site", None)
    if site:
        assert_dedicated_test_site(frappe.conf.get("crm_test_site"), site)


class _DedicatedTestSiteFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname: str, path=None, target=None):
        if fullname.startswith("rayher_crm.tests.test_"):
            guard_test_module_import()
        return None


def install_test_module_guard() -> None:
    if not any(isinstance(finder, _DedicatedTestSiteFinder) for finder in sys.meta_path):
        sys.meta_path.insert(0, _DedicatedTestSiteFinder())
