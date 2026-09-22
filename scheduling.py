from datetime import datetime


def days_until_check(next_renewal_days, fallback_days):
    if next_renewal_days:
        return max(1, int(next_renewal_days) - 6)
    return max(1, int(fallback_days))


def future_check(value, now):
    if not value:
        return None
    try:
        scheduled = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if scheduled.tzinfo is None:
        return None
    return scheduled if scheduled > now else None
