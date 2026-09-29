"""Store Customer and Opportunity regions in the shared region options.

The mapping, the overrides and the CSV reports live in rayher_crm.setup.region_migration;
run its dry_run on a restored copy first.
"""

from __future__ import annotations

from rayher_crm.setup.region_migration import apply_migration


def execute() -> None:
    apply_migration()
