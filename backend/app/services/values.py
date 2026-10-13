"""Defensive conversions for ClassAd values, which may be missing or malformed."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any


def as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if math.isfinite(value) else None
    if isinstance(value, str):
        try:
            return int(float(value.strip()))
        except (ValueError, OverflowError):
            return None
    return None


def as_str(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "1"):
            return True
        if lowered in ("false", "0"):
            return False
    return None


def as_datetime(value: Any) -> datetime | None:
    epoch = as_int(value)
    if epoch is None or epoch <= 0:
        return None
    try:
        return datetime.fromtimestamp(epoch, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def seconds_between(start: datetime | None, end: datetime | None) -> int | None:
    if start is None or end is None:
        return None
    return max(0, int((end - start).total_seconds()))


def split_slot(value: Any) -> tuple[str | None, str | None]:
    """Split 'slot1@host' into (slot name, machine)."""
    name = as_str(value)
    if name is None:
        return None, None
    if "@" in name:
        return name, name.split("@", 1)[1] or None
    return None, name
