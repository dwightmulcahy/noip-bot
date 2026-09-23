from datetime import datetime, timedelta


RETRY_DELAYS_SECONDS = (15 * 60, 60 * 60, 6 * 60 * 60, 24 * 60 * 60)


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


def retry_delay_seconds(consecutive_failures, jitter_fraction=0.0):
    attempt = max(1, int(consecutive_failures))
    base_delay = RETRY_DELAYS_SECONDS[min(attempt, len(RETRY_DELAYS_SECONDS)) - 1]
    bounded_jitter = min(0.1, max(-0.1, float(jitter_fraction)))
    return max(60, round(base_delay * (1 + bounded_jitter)))


def should_notify_failure(consecutive_failures):
    attempt = max(1, int(consecutive_failures))
    return attempt in {1, 4} or (attempt > 4 and (attempt - 4) % 7 == 0)
