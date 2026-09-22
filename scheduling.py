from datetime import datetime, timedelta


def days_until_check(next_renewal_days, fallback_days, max_interval_days=5):
    max_interval = max(1, int(max_interval_days))
    if next_renewal_days:
        calculated = max(1, int(next_renewal_days) - 6)
    else:
        calculated = max(1, int(fallback_days))
    return min(max_interval, calculated)


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


def cap_future_check(scheduled, now, max_interval_days=5):
    if scheduled is None:
        return None
    maximum = now + timedelta(days=max(1, int(max_interval_days)))
    return min(scheduled, maximum)
