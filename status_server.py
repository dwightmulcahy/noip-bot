import flask
import hmac
import os

from http import HTTPStatus

import waitress

from health_status import evaluate_health
from state_store import StateStore
from utils import UpTime

# formatting for log messages
import logging

log = logging.getLogger(__name__)

# start flask using the appname
app = flask.Flask(__name__)

# set the app name to use
APP_NAME = "Piku Template Flask App"
app_Name = APP_NAME
uptime = UpTime()

BIND_ADDRESS = "0.0.0.0"  # nosec
PORT = 9090


# msg to display for webpage
pageMsg = "Empty!"


def _status_token():
    return os.environ.get("STATUS_TOKEN", "").strip()


def _is_authorized():
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


def _authentication_error():
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


def _redact_error(error):
    if not isinstance(error, dict):
        return None
    return {key: value for key, value in error.items() if key in {"timestamp", "type"}}


def _detailed_status(state):
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
    payload["uptime"] = str(uptime)
    return payload


@app.after_request
def disable_status_caching(response):
    response.headers["Cache-Control"] = "no-store"
    return response


def setPageMsg(msg):
    global pageMsg
    pageMsg = msg.replace("\n", "<br>")


def getPageMsg():
    return pageMsg


# health check endpoint
@app.route("/health")
def health():
    log.debug(f"{app_Name} /health endpoint executing")
    grace = int(os.environ.get("HEALTH_OVERDUE_GRACE_SECONDS", "3600"))
    payload = evaluate_health(StateStore().state, overdue_grace_seconds=grace)
    public_payload = {"status": payload["status"], "healthy": payload["healthy"]}
    status_code = (
        HTTPStatus.OK if payload["healthy"] else HTTPStatus.SERVICE_UNAVAILABLE
    )
    return flask.jsonify(public_payload), status_code


@app.route("/status.json")
def status_json():
    if not _is_authorized():
        return _authentication_error()
    state = StateStore().state
    return flask.jsonify(_detailed_status(state)), HTTPStatus.OK


@app.route("/")
def hello():
    log.debug(f"{app_Name} / endpoint executing")
    if not _is_authorized():
        return _authentication_error()
    return getPageMsg(), HTTPStatus.OK


def startWebServer(appName=APP_NAME, bind=BIND_ADDRESS, port=PORT, debug=False):
    global app_Name
    app_Name = appName
    if debug:
        log.info(f"Starting flask server on {bind}:{port}")
        # run the built-in flask server
        # FOR DEVELOPMENT/DEBUGGING ONLY
        app.run(threaded=True, host=bind, port=port, debug=False)
    else:
        logging.getLogger("waitress").setLevel(logging.ERROR)
        log.info(f"Starting waitress server on {bind}:{port}")
        # Run the production server
        waitress.serve(app, host=bind, port=port, threads=4)


if __name__ == "__main__":
    log.info(f"Started {app_Name}")

    log.info(f"Running {app_Name} press Ctrl+C to exit.")
    try:
        startWebServer(debug=False)
    except (KeyboardInterrupt, SystemExit):
        log.info("Shutting down...")
    except RuntimeError as err:
        log.error(f"RuntimeError.\n{err}")
