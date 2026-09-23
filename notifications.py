import os
import queue
import threading


class NotificationDeliveryError(RuntimeError):
    """Raised internally when a provider reports an unsuccessful delivery."""


DEFAULT_TIMEOUT_SECONDS = 30.0


def _delivery_timeout_seconds():
    raw_value = os.environ.get("NOTIFICATION_TIMEOUT_SECONDS", "30")
    try:
        return max(0.1, float(raw_value))
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS


def _deliver_with_timeout(server, send_to, subject, body, timeout_seconds):
    result_queue: queue.Queue[tuple[bool, object]] = queue.Queue(maxsize=1)

    def deliver():
        try:
            result_queue.put((True, server.sendEmail(send_to, subject, str(body))))
        except Exception as exc:
            result_queue.put((False, exc))

    threading.Thread(
        target=deliver,
        name="notification-delivery",
        daemon=True,
    ).start()
    try:
        succeeded, result = result_queue.get(timeout=timeout_seconds)
    except queue.Empty as exc:
        raise TimeoutError(
            f"Notification delivery exceeded {timeout_seconds:g} seconds"
        ) from exc
    if not succeeded:
        if isinstance(result, BaseException):
            raise result
        raise RuntimeError("Notification worker returned an invalid error result")
    return result


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


def send_notification(
    server, send_to, subject, body, state_store, logger, timeout_seconds=None
):
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
        timeout_seconds = (
            _delivery_timeout_seconds()
            if timeout_seconds is None
            else max(0.1, float(timeout_seconds))
        )
        delivered = _deliver_with_timeout(
            server, send_to, subject, body, timeout_seconds
        )
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
