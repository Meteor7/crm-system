"""One-time patch entry point for legacy CRM Customer ownership."""

from rayher_crm.setup.legacy_account_ownership import backfill_legacy_account_ownership


def execute() -> None:
    backfill_legacy_account_ownership()