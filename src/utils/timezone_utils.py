"""Timezone helpers — default IST (Asia/Kolkata)."""

from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = "Asia/Kolkata"


def get_timezone_name() -> str:
    return os.getenv("TIMEZONE", DEFAULT_TIMEZONE)


def get_timezone() -> ZoneInfo:
    return ZoneInfo(get_timezone_name())


def configure_timezone() -> ZoneInfo:
    """Set process timezone and return the configured ZoneInfo."""
    tz = get_timezone()
    os.environ["TZ"] = str(tz)
    return tz


def now_local() -> datetime:
    return datetime.now(get_timezone())


def local_date_str(fmt: str = "%Y-%m-%d") -> str:
    return now_local().strftime(fmt)


def local_datetime_str(fmt: str = "%B %d, %Y") -> str:
    return now_local().strftime(fmt)
