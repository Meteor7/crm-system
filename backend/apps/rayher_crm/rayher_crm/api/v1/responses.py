"""Stable public response envelopes for QIHENG Demo CRM APIs."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def response_meta(**meta: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "requestId": f"req_{uuid4().hex[:24]}",
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    result.update(meta)
    return result


def success_response(
    data: Any,
    warnings: Iterable[str] = (),
    **meta: Any,
) -> dict[str, Any]:
    """Return the Stage 1 success envelope without exposing Frappe internals."""

    return {
        "data": data,
        "meta": response_meta(**meta),
        "warnings": list(warnings),
    }
