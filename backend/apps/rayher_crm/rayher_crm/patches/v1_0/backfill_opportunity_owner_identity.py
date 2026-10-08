"""Preserve owner identities across User renames without changing audit text."""
from rayher_crm.services.cockpit_identity import backfill_owner_identities


def execute():
    backfill_owner_identities()
