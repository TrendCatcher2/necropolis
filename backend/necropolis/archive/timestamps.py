"""Wayback timestamps (`YYYYMMDDhhmmss`, UTC) to and from `datetime`.

tech.md: they are converted here, at the archive boundary, and never leak further.
"""

from __future__ import annotations

from datetime import UTC, datetime


def parse_timestamp(value: object) -> datetime | None:
    """A 14-digit Wayback timestamp as an aware UTC datetime, or None if it is not one."""
    if not isinstance(value, str) or len(value) != 14 or not value.isascii() or not value.isdigit():
        return None
    try:
        return datetime(
            int(value[0:4]),
            int(value[4:6]),
            int(value[6:8]),
            int(value[8:10]),
            int(value[10:12]),
            int(value[12:14]),
            tzinfo=UTC,
        )
    except ValueError:  # month 13, day 32, year 0, ...
        return None


def format_timestamp(when: datetime) -> str:
    if when.tzinfo is None:
        raise ValueError("Wayback timestamps are UTC: pass an aware datetime")
    return when.astimezone(UTC).strftime("%Y%m%d%H%M%S")
