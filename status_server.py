import hmac
import hashlib
import logging
import os
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from typing import Any, Protocol
from zoneinfo import ZoneInfo

import flask
import waitress

from health_status import evaluate_health
from state_store import StateStore
from utils import UpTime


log = logging.getLogger(__name__)


class StateReader(Protocol):
    state: dict[str, Any]


StateStoreFactory = Callable[[], StateReader]
OtpSender = Callable[[str, str, str], bool]

OTP_TTL_SECONDS = 10 * 60
OTP_RESEND_SECONDS = 60
OTP_MAX_ATTEMPTS = 5


@dataclass(slots=True)
class OtpChallenge:
    digest: bytes
    expires_at: float
    attempts_remaining: int


def _status_token() -> str:
    return os.environ.get("STATUS_TOKEN", "").strip()


def _is_bearer_authorized() -> bool:
    token = _status_token()
    if len(token) < 32:
        return False
    authorization = flask.request.headers.get("Authorization", "")
    scheme, separator, supplied_token = authorization.partition(" ")
    return (
        bool(separator)
        and scheme.lower() == "bearer"
        and hmac.compare_digest(supplied_token, token)
    )


def _is_session_authorized() -> bool:
    return bool(flask.session.get("status_authenticated"))


def _is_authorized() -> bool:
    return _is_bearer_authorized() or _is_session_authorized()


def _csrf_token() -> str:
    token = flask.session.get("csrf_token")
    if not isinstance(token, str) or not token:
        token = secrets.token_urlsafe(32)
        flask.session["csrf_token"] = token
    return token


def _csrf_is_valid() -> bool:
    expected = flask.session.get("csrf_token", "")
    supplied = flask.request.form.get("csrf_token", "")
    return bool(
        isinstance(expected, str)
        and expected
        and hmac.compare_digest(supplied, expected)
    )


def _environment_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _display_timestamp(value: object) -> str:
    if not isinstance(value, str) or not value:
        return "Not available"
    try:
        parsed = datetime.fromisoformat(value)
        timezone = ZoneInfo(os.environ.get("TZ", "America/Costa_Rica"))
        return parsed.astimezone(timezone).strftime("%b %d, %Y at %H:%M %Z")
    except (TypeError, ValueError, KeyError):
        return value


def _masked_email(value: str) -> str:
    local, separator, domain = value.partition("@")
    if not separator:
        return "configured address"
    visible = local[:2] if len(local) > 2 else local[:1]
    return f"{visible}{'*' * max(3, len(local) - len(visible))}@{domain}"


def _authentication_error() -> tuple[flask.Response, HTTPStatus]:
    if len(_status_token()) < 32:
        return (
            flask.jsonify(
                {
                    "error": "detailed status is disabled",
                    "status": "unavailable",
                }
            ),
            HTTPStatus.SERVICE_UNAVAILABLE,
        )
    response = flask.jsonify({"error": "unauthorized", "status": "unauthorized"})
    response.headers["WWW-Authenticate"] = "Bearer"
    return response, HTTPStatus.UNAUTHORIZED


def _redact_error(error: object) -> dict[str, Any] | None:
    if not isinstance(error, dict):
        return None
    return {key: value for key, value in error.items() if key in {"timestamp", "type"}}


class StatusServer:
    def __init__(
        self,
        app_name: str,
        state_store_factory: StateStoreFactory = StateStore,
        otp_sender: OtpSender | None = None,
        otp_recipient: str = "",
    ) -> None:
        self.app_name = app_name
        self.state_store_factory = state_store_factory
        self.uptime = UpTime()
        self._page_message = "Empty!"
        self._message_lock = threading.RLock()
        self._otp_lock = threading.RLock()
        self._otp_challenge: OtpChallenge | None = None
        self._otp_last_sent_at = 0.0
        self._otp_sender = otp_sender
        self._otp_recipient = otp_recipient.strip()
        self.app = flask.Flask(__name__)
        token = _status_token()
        self.app.secret_key = (
            hashlib.sha256(f"{app_name}:{token}:status-session".encode()).digest()
            if len(token) >= 32
            else secrets.token_bytes(32)
        )
        self.app.config.update(
            SESSION_COOKIE_HTTPONLY=True,
            SESSION_COOKIE_SAMESITE="Strict",
            SESSION_COOKIE_SECURE=_environment_flag("STATUS_COOKIE_SECURE"),
            PERMANENT_SESSION_LIFETIME=12 * 60 * 60,
        )
        self.app.jinja_env.filters["status_time"] = _display_timestamp
        self._register_routes()

    def _otp_digest(self, code: str) -> bytes:
        secret_key = self.app.secret_key
        if isinstance(secret_key, str):
            secret_key = secret_key.encode()
        return hmac.new(secret_key, code.encode(), hashlib.sha256).digest()

    def _login_available(self) -> bool:
        return bool(
            len(_status_token()) >= 32
            and self._otp_sender is not None
            and self._otp_recipient
        )

    def _login_page(
        self,
        error: str | None = None,
        code_sent: bool = False,
        status: HTTPStatus = HTTPStatus.OK,
    ) -> tuple[str, HTTPStatus]:
        return (
            flask.render_template(
                "status_login.html",
                app_name=self.app_name,
                error=error,
                code_sent=code_sent,
                login_available=self._login_available(),
                masked_email=_masked_email(self._otp_recipient),
                otp_ttl_minutes=OTP_TTL_SECONDS // 60,
                csrf_token=_csrf_token(),
            ),
            status,
        )

    def set_page_message(self, message: str) -> None:
        with self._message_lock:
            self._page_message = message.replace("\n", "<br>")

    def get_page_message(self) -> str:
        with self._message_lock:
            return self._page_message

    def _detailed_status(self, state: dict[str, Any]) -> dict[str, Any]:
        payload = evaluate_health(state)
        error_message = (payload.get("last_error") or {}).get("message")
        if error_message:
            payload["reasons"] = [
                "the last renewal check failed" if reason == error_message else reason
                for reason in payload["reasons"]
            ]
        payload["last_error"] = _redact_error(payload.get("last_error"))
        notifications = dict(payload.get("notifications") or {})
        notifications["last_error"] = _redact_error(notifications.get("last_error"))
        payload["notifications"] = notifications
        payload["hosts"] = {
            hostname: {key: value for key, value in details.items() if key != "host_id"}
            for hostname, details in state.get("hosts", {}).items()
        }
        payload["configured_dry_run"] = _environment_flag("DRY_RUN")
        payload["uptime"] = str(self.uptime)
        return payload

    def _register_routes(self) -> None:
        @self.app.after_request
        def disable_status_caching(response: flask.Response) -> flask.Response:
            response.headers["Cache-Control"] = "no-store"
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; style-src 'self'; img-src 'self'; "
                "form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
            )
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            return response

        @self.app.get("/login")
        def login() -> tuple[str, HTTPStatus] | flask.Response:
            if _is_session_authorized():
                return flask.redirect(flask.url_for("root"))
            if not self._login_available():
                return self._login_page(
                    "Email login is unavailable. Configure Gmail, "
                    "STATUS_LOGIN_EMAIL, and STATUS_TOKEN.",
                    status=HTTPStatus.SERVICE_UNAVAILABLE,
                )
            return self._login_page()

        @self.app.post("/login/send")
        def send_login_code() -> tuple[str, HTTPStatus]:
            if not _csrf_is_valid():
                return self._login_page(
                    "The login form expired. Please try again.",
                    status=HTTPStatus.BAD_REQUEST,
                )
            if not self._login_available():
                return self._login_page(
                    "Email login is unavailable.",
                    status=HTTPStatus.SERVICE_UNAVAILABLE,
                )
            now = time.monotonic()
            with self._otp_lock:
                wait_seconds = OTP_RESEND_SECONDS - (now - self._otp_last_sent_at)
                if wait_seconds > 0:
                    return self._login_page(
                        f"Please wait {int(wait_seconds) + 1} seconds before sending another code.",
                        code_sent=self._otp_challenge is not None,
                        status=HTTPStatus.TOO_MANY_REQUESTS,
                    )
                code = f"{secrets.randbelow(1_000_000):06d}"
                challenge = OtpChallenge(
                    digest=self._otp_digest(code),
                    expires_at=now + OTP_TTL_SECONDS,
                    attempts_remaining=OTP_MAX_ATTEMPTS,
                )
                self._otp_last_sent_at = now

            subject = f"{self.app_name} status login code"
            body = (
                f"Your {self.app_name} status login code is **{code}**.\n\n"
                f"It expires in {OTP_TTL_SECONDS // 60} minutes and can be used once. "
                "If you did not request it, no action is required."
            )
            sender = self._otp_sender
            delivered = bool(sender and sender(self._otp_recipient, subject, body))
            if not delivered:
                with self._otp_lock:
                    self._otp_challenge = None
                log.error(
                    "Unable to deliver status login code",
                    extra={"event": "status_login_delivery_failed"},
                )
                return self._login_page(
                    "The login code could not be delivered. Check the Gmail configuration.",
                    status=HTTPStatus.BAD_GATEWAY,
                )
            with self._otp_lock:
                self._otp_challenge = challenge
            log.info(
                "Status login code delivered",
                extra={"event": "status_login_code_sent"},
            )
            return self._login_page(code_sent=True)

        @self.app.post("/login/verify")
        def verify_login_code() -> tuple[str, HTTPStatus] | flask.Response:
            if not _csrf_is_valid():
                return self._login_page(
                    "The login form expired. Please try again.",
                    status=HTTPStatus.BAD_REQUEST,
                )
            supplied_code = flask.request.form.get("code", "").strip()
            now = time.monotonic()
            with self._otp_lock:
                challenge = self._otp_challenge
                if challenge is None or now >= challenge.expires_at:
                    self._otp_challenge = None
                    return self._login_page(
                        "The login code has expired. Request a new code.",
                        status=HTTPStatus.UNAUTHORIZED,
                    )
                valid = bool(
                    len(supplied_code) == 6
                    and supplied_code.isdigit()
                    and hmac.compare_digest(
                        self._otp_digest(supplied_code), challenge.digest
                    )
                )
                if not valid:
                    challenge.attempts_remaining -= 1
                    if challenge.attempts_remaining <= 0:
                        self._otp_challenge = None
                        error = "Too many incorrect attempts. Request a new code."
                    else:
                        error = (
                            "The login code is incorrect. "
                            f"{challenge.attempts_remaining} attempts remain."
                        )
                    return self._login_page(
                        error,
                        code_sent=self._otp_challenge is not None,
                        status=HTTPStatus.UNAUTHORIZED,
                    )
                self._otp_challenge = None

            flask.session.clear()
            flask.session["status_authenticated"] = True
            flask.session.permanent = True
            _csrf_token()
            log.info(
                "Status login succeeded", extra={"event": "status_login_succeeded"}
            )
            return flask.redirect(flask.url_for("root"))

        @self.app.post("/logout")
        def logout() -> flask.Response:
            if not _csrf_is_valid():
                flask.abort(HTTPStatus.BAD_REQUEST)
            flask.session.clear()
            return flask.redirect(flask.url_for("login"))

        @self.app.route("/health")
        def health() -> tuple[flask.Response, HTTPStatus]:
            log.debug("%s /health endpoint executing", self.app_name)
            grace = int(os.environ.get("HEALTH_OVERDUE_GRACE_SECONDS", "3600"))
            payload = evaluate_health(
                self.state_store_factory().state,
                overdue_grace_seconds=grace,
            )
            public_payload = {
                "status": payload["status"],
                "healthy": payload["healthy"],
            }
            status_code = (
                HTTPStatus.OK if payload["healthy"] else HTTPStatus.SERVICE_UNAVAILABLE
            )
            return flask.jsonify(public_payload), status_code

        @self.app.route("/status.json")
        def status_json() -> tuple[flask.Response, HTTPStatus]:
            if not _is_authorized():
                return _authentication_error()
            state = self.state_store_factory().state
            return flask.jsonify(self._detailed_status(state)), HTTPStatus.OK

        @self.app.route("/")
        def root() -> tuple[str, HTTPStatus] | flask.Response:
            log.debug("%s / endpoint executing", self.app_name)
            if not _is_authorized():
                return flask.redirect(flask.url_for("login"))
            state = self.state_store_factory().state
            return (
                flask.render_template(
                    "status_dashboard.html",
                    app_name=self.app_name,
                    status=self._detailed_status(state),
                    csrf_token=_csrf_token(),
                ),
                HTTPStatus.OK,
            )

    def serve(self, bind: str, port: int, debug: bool = False) -> None:
        if debug:
            log.info("Starting flask server on %s:%s", bind, port)
            self.app.run(threaded=True, host=bind, port=port, debug=False)
            return
        logging.getLogger("waitress").setLevel(logging.ERROR)
        log.info("Starting waitress server on %s:%s", bind, port)
        waitress.serve(self.app, host=bind, port=port, threads=4)
