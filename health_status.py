from datetime import datetime, timedelta, timezone


def _parse_timestamp(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else None


def evaluate_health(state, now=None, overdue_grace_seconds=3600):
    now = now or datetime.now(timezone.utc)
    last_success = _parse_timestamp(state.get("last_success"))
    next_check = _parse_timestamp(state.get("next_check"))
    last_error = state.get("last_error")
    reasons = []

    if last_success is None:
        reasons.append("no successful renewal check has completed")
    elif next_check is None:
        reasons.append("no next renewal check is scheduled")

    if last_error:
        error_time = _parse_timestamp(last_error.get("timestamp"))
        if last_success is None or error_time is None or error_time > last_success:
            reasons.append(last_error.get("message") or "the last renewal check failed")

    if next_check and now > next_check + timedelta(seconds=overdue_grace_seconds):
        reasons.append("the scheduled renewal check is overdue")

    hosts = state.get("hosts", {})
    notifications = state.get("notifications", {})
    if not notifications.get("enabled", False):
        notification_status = "disabled"
    else:
        notification_success = _parse_timestamp(notifications.get("last_success"))
        notification_error = notifications.get("last_error")
        notification_error_time = _parse_timestamp(
            notification_error.get("timestamp") if notification_error else None
        )
        notification_status = (
            "degraded"
            if notification_error
            and (
                notification_success is None
                or notification_error_time is None
                or notification_error_time > notification_success
            )
            else "healthy"
        )
    active_hosts = sum(1 for host in hosts.values() if host.get("active", True))
    return {
        "status": "unhealthy" if reasons else "healthy",
        "healthy": not reasons,
        "reasons": reasons,
        "last_run": state.get("last_run"),
        "last_success": state.get("last_success"),
        "last_error": last_error,
        "next_check": state.get("next_check"),
        "next_renewal_days": state.get("next_renewal_days"),
        "dry_run": bool(state.get("dry_run", False)),
        "would_renew": state.get("would_renew", []),
        "notification_status": notification_status,
        "notifications": notifications,
        "host_count": active_hosts,
        "total_host_count": len(hosts),
    }
