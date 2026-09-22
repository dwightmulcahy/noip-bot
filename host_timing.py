import math
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


DISPLAY_FORMATS = (
    "%b %d, %Y %H:%M:%S",
    "%b %d, %Y, %H:%M:%S",
)


def parse_data_update(value, timezone_name=None):
    if not value:
        return None
    timezone = ZoneInfo(timezone_name or os.environ.get("TZ", "UTC"))
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        parsed = None
    if parsed is None:
        for date_format in DISPLAY_FORMATS:
            try:
                parsed = datetime.strptime(value, date_format)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    return parsed.replace(tzinfo=timezone) if parsed.tzinfo is None else parsed


def derive_cycle_timing(value, now=None, timezone_name=None, cycle_days=30):
    updated_at = parse_data_update(value, timezone_name)
    if updated_at is None:
        return {
            "estimated_expiration": None,
            "estimated_days_until_expiry": None,
        }
    now = now or datetime.now(updated_at.tzinfo)
    expiration = updated_at + timedelta(days=cycle_days)
    remaining = max(0, math.ceil((expiration - now).total_seconds() / 86400))
    return {
        "estimated_expiration": expiration.isoformat(),
        "estimated_days_until_expiry": remaining,
    }
