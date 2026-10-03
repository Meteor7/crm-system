"""Give an existing site the default sales territory tree: World > Asia > China > the five regions."""

from __future__ import annotations

from rayher_crm.services.territories import ensure_default_territories


def execute() -> None:
    ensure_default_territories()
