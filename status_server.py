import flask

from utils import UpTime
from http import HTTPStatus
import waitress
import os
from health_status import evaluate_health
from state_store import StateStore

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
    payload["uptime"] = str(uptime)
    return flask.jsonify(payload), HTTPStatus.OK if payload[
        "healthy"
    ] else HTTPStatus.SERVICE_UNAVAILABLE


@app.route("/status.json")
def status_json():
    state = StateStore().state
    payload = evaluate_health(state)
    payload["uptime"] = str(uptime)
    payload["hosts"] = state.get("hosts", {})
    return flask.jsonify(payload), HTTPStatus.OK


@app.route("/")
def hello():
    log.debug(f"{app_Name} / endpoint executing")
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
