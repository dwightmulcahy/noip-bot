class NotificationDeliveryError(RuntimeError):
    """Raised internally when a provider reports an unsuccessful delivery."""


def _record_safely(logger, action, *args):
    if action is None:
        return
    try:
        action(*args)
    except Exception:
        logger.exception(
            "Unable to persist notification status",
            extra={"event": "notification_state_failed"},
        )


def send_notification(server, send_to, subject, body, state_store, logger):
    """Attempt a notification without allowing it to interrupt core work."""
    if server is None:
        action = state_store.set_notifications_enabled if state_store else None
        _record_safely(logger, action, False)
        logger.warning(
            "Notification skipped because Gmail is not configured",
            extra={"event": "notification_disabled", "subject": subject},
        )
        return False

    try:
        delivered = server.sendEmail(send_to, subject, str(body))
        if not delivered:
            raise NotificationDeliveryError(
                "The email provider did not confirm delivery"
            )
    except Exception as exc:
        action = state_store.record_notification_failure if state_store else None
        _record_safely(logger, action, exc)
        logger.exception(
            "Notification delivery failed",
            extra={
                "event": "notification_failed",
                "recipient": send_to,
                "subject": subject,
            },
        )
        return False

    action = state_store.record_notification_success if state_store else None
    _record_safely(logger, action)
    logger.info(
        "Notification delivered",
        extra={
            "event": "notification_succeeded",
            "recipient": send_to,
            "subject": subject,
        },
    )
    return True
