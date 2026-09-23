import hmac
import hashlib
import logging
import os
import secrets
import threading
from collections.abc import Callable
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
    ) -> None:
        self.app_name = app_name
        self.state_store_factory = state_store_factory
        self.uptime = UpTime()
        self._page_message = "Empty!"
        self._message_lock = threading.RLock()
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

        @self.app.route("/login", methods=["GET", "POST"])
        def login() -> tuple[str, HTTPStatus] | flask.Response:
            token = _status_token()
            if len(token) < 32:
                return (
                    flask.render_template(
                        "status_login.html",
                        app_name=self.app_name,
                        error="Browser status is disabled until STATUS_TOKEN is configured.",
                    ),
                    HTTPStatus.SERVICE_UNAVAILABLE,
                )
            if flask.request.method == "POST":
                supplied_token = flask.request.form.get("token", "")
                if hmac.compare_digest(supplied_token, token):
                    flask.session.clear()
                    flask.session["status_authenticated"] = True
                    flask.session.permanent = True
                    return flask.redirect(flask.url_for("root"))
                return (
                    flask.render_template(
                        "status_login.html",
                        app_name=self.app_name,
                        error="The status token is incorrect.",
                    ),
                    HTTPStatus.UNAUTHORIZED,
                )
            return flask.render_template(
                "status_login.html", app_name=self.app_name, error=None
            )

        @self.app.post("/logout")
        def logout() -> flask.Response:
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
