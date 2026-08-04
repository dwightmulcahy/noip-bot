import http
import flask

from utils import UpTime
from http import HTTPStatus
from emailServer.markdownEmailServer import MarkdownEmailServer
import waitress
import sys
if not sys.version_info > (3, 6):
    print('Python3.6 is required to run this')
    sys.exit(-1)

# formatting for log messages
import logging
log = logging.getLogger(__name__)

# start flask using the appname
app = flask.Flask(__name__)

# set the app name to use
APP_NAME = 'Piku Template Flask App'
app_Name = APP_NAME
uptime = UpTime()

BIND_ADDRESS = '0.0.0.0'  # nosec
PORT = 9090

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{
    --accent: #2b7a78;
    --bg: #f4f6f7;
    --card: #ffffff;
    --border: #dde3e4;
    --text: #1f2933;
    --muted: #6b7280;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    padding: 2.5rem 1rem;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    line-height: 1.55;
  }}
  .card {{
    max-width: 720px;
    margin: 0 auto;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 2rem 2.25rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  }}
  .card h1 {{
    margin-top: 0;
    font-size: 1.4rem;
    color: var(--accent);
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    margin: 1rem 0 1.5rem;
    font-size: 0.95rem;
  }}
  th, td {{
    text-align: left;
    padding: 0.55rem 0.75rem;
    border-bottom: 1px solid var(--border);
  }}
  th {{
    background: #eef5f4;
    color: var(--accent);
    font-weight: 600;
  }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: #fafcfc; }}
  em, i {{ color: var(--muted); }}
  hr {{ border: none; border-top: 1px solid var(--border); margin: 1.5rem 0; }}
  .meta {{ color: var(--muted); font-size: 0.85rem; margin-top: 1.5rem; }}
</style>
</head>
<body>
  <div class="card">
    <h1>{app_name}</h1>
    {content}
  </div>
</body>
</html>"""

# msg to display for webpage
pageMsg = 'Empty!'

def setPageMsg(msg):
    global pageMsg
    pageMsg = msg

def getPageMsg():
    return PAGE_TEMPLATE.format(
        title=app_Name,
        app_name=app_Name,
        content=MarkdownEmailServer.githubMarkdown(pageMsg),
    )


# health check endpoint
@app.route('/health')
def health():
    log.info(f'{app_Name} /health endpoint executing')

    # build the response to send back
    res = HTTPStatus.OK

    return f'Current Health Status: {res.phrase}<br><br>{app_Name} uptime: {str(uptime)}', res.value


@app.route('/')
def hello():
    log.info(f'{app_Name} / endpoint executing')
    return getPageMsg(), http.HTTPStatus.OK.numerator


def startWebServer(appName=APP_NAME, bind=BIND_ADDRESS, port=PORT, debug=False):
    global app_Name
    app_Name = appName
    if debug:
        log.info(f'Starting flask server on {bind}:{port}')
        # run the built-in flask server
        # FOR DEVELOPMENT/DEBUGGING ONLY
        app.run(threaded=True, host=bind, port=port, debug=False)
    else:
        logging.getLogger("waitress").setLevel(logging.ERROR)
        log.info(f'Starting waitress server on {bind}:{port}')
        # Run the production server
        waitress.serve(app, host=bind, port=port, threads=4)


if __name__ == '__main__':
    log.info(f'Started {app_Name}')

    log.info(f'Running {app_Name} press Ctrl+C to exit.')
    try:
        startWebServer(debug=False)
    except (KeyboardInterrupt, SystemExit):
        log.info('Shutting down...')
    except RuntimeError as err:
        log.error(f'RuntimeError.\n{err}')
