"""Move Opportunities from the legacy stages to the seven milestones.

The mapping, the evidence rules and the CSV reports live in
rayher_crm.setup.opportunity_stage_migration; run its dry_run on a restored copy first.
"""

from __future__ import annotations

from rayher_crm.setup.opportunity_stage_migration import apply_migration


def execute() -> None:
    apply_migration()
