"""Equipment type names without a site: the presets, the comparison key and the catalog spelling.

Kept apart from ``services.equipment`` so the board rules, which run without Frappe, can use it.
Two spellings that differ only in case, width, accents, spacing, punctuation or invisible
characters ("NANSI", "nan-si", "ＮＡＮＳＩ", "Nánsi", "Nansi") are the same type; the catalog
spelling is the preset, else the custom type registered first.
"""

from __future__ import annotations

import unicodedata
from typing import Any, Iterable

EQUIPMENT_PRESETS = ("Aconca", "Drakens", "Kibo", "Nansi", "Veymont")


def normalized_text(value: str) -> str:
    """NFKC text (full-width letters become ASCII) without invisible format characters such as
    zero-width spaces or a BOM."""

    return "".join(char for char in unicodedata.normalize("NFKC", value) if unicodedata.category(char) != "Cf")


def equipment_key(value: Any) -> str:
    """Compare equipment types by their letters and digits only.

    Case, width, accents, spacing, punctuation and invisible characters do not count, so the key
    folds at least what the catalog's unique index (utf8mb4_unicode_ci) folds for Latin letters:
    "Probe" and "Próbe" are one type, not a failed insert. Text without a letter or digit has no key.
    """

    folded = unicodedata.normalize("NFKD", normalized_text(str(value or "")).casefold())
    return "".join(char for char in folded if char.isalnum())


def equipment_spellings(options: Iterable[str]) -> dict[str, str]:
    """Comparison key -> catalog spelling; presets win, then the option listed first."""

    spellings: dict[str, str] = {}
    for option in (*EQUIPMENT_PRESETS, *options):
        spellings.setdefault(equipment_key(option), option)
    return spellings


def canonical_equipment(value: str | None, spellings: dict[str, str]) -> str | None:
    """The catalog spelling of a stored value; one with no catalog match keeps its own."""

    if not value:
        return None
    return spellings.get(equipment_key(value), value)
