"""Guest-safe health endpoint."""

from __future__ import annotations

import frappe

from rayher_crm import __version__
from rayher_crm.api.v1.responses import success_response


@frappe.whitelist(allow_guest=True, methods=["GET"])
def get_health() -> dict:
    return success_response(
        {
            "status": "ok",
            "app": "rayher_crm",
            "version": __version__,
        }
    )
