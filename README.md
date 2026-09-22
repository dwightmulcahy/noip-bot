# No-IP Renewal Bot

A Docker-friendly Python service that logs in to No-IP, confirms eligible free
hostnames, handles emailed verification codes, schedules the next check, sends
optional Gmail notifications, and exposes a small status page.

## Features

- Discovers No-IP hostnames from the current DNS records interface
- Confirms hostnames that No-IP marks as eligible for renewal
- Supports No-IP email verification codes through Gmail
- Recovers from HTMX stale-element updates
- Schedules the next run from the displayed expiration information
- Retries a failed run the following day
- Stores diagnostic screenshots in a configurable persistent directory
- Persists verified renewal state atomically across restarts
- Verifies both confirmation-control removal and changed `data-update`
- Emits one JSON object per log line for ingestion by Docker logging systems
- Provides a web status page and Docker health check
- Runs as a non-root container user

## Quick start with Docker Compose

1. Copy the example configuration:

   ```sh
   cp .env.example .env
   ```

2. Set at minimum `NOIP_ID` and `NOIP_PASSWORD` in `.env`. If No-IP
   requires an emailed code, also configure the verification email fields.

3. Build and run:

   ```sh
   docker compose up -d --build
   ```

4. Open `http://localhost:8080`.

Diagnostic screenshots are written beneath `./data/screenshots`.

## Configuration

| Variable | Purpose | Default |
| --- | --- | --- |
| `NOIP_ID` | No-IP username/email | required |
| `NOIP_PASSWORD` | No-IP password | required |
| `NOIP_VERIFICATION_EMAIL` | Inbox receiving No-IP verification codes | empty |
| `NOIP_VERIFICATION_EMAIL_TOKEN` | Gmail app password/token for that inbox | empty |
| `GMAIL_ID` | Gmail sender for notifications | empty |
| `GMAIL_TOKEN` | Gmail app password/token for notifications | empty |
| `BIND_ADDR` | Status server bind address | `0.0.0.0` in Docker |
| `PORT` | Status server port | `8080` in Docker |
| `TZ` | Scheduler timezone | `America/Costa_Rica` |
| `SCREENSHOT_DIR` | Diagnostic screenshot directory | `/app/data/screenshots` |
| `STATE_FILE` | Persistent renewal-state JSON file | `/app/data/state.json` |
| `LOG_LEVEL` | Structured JSON logging level | `INFO` |
| `HEADLESS` | Run Chromium without a display | `true` in Docker |
| `CHROMEDRIVER_BIN` | ChromeDriver executable | `/usr/bin/chromedriver` |
| `CHROMEDRIVER_LOG` | Persistent verbose driver log | `/app/data/chromedriver.log` |
| `DEBUG` | Enable debug behavior | `False` |

Never commit `.env`, Gmail tokens, No-IP credentials, or captured screenshots.

## Local development

Python 3.12 or newer and Chrome/Chromium are recommended.

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python3 noip_bot.py
```

Run the unit tests with:

```sh
python3 -m unittest discover -s tests -v
```

The project archive includes all internal modules. If PyCharm reports a missing
`utils.iputils` or `utils.uptime` module, replace the project from the
current archive rather than reusing an older extracted copy.

## Operational notes

- A navigation or renewal failure now fails the run instead of being treated as
  “nothing to renew.”
- A hostname is only recorded as renewed after its confirmation control
  disappears and its `data-update` attribute changes.
- State is written atomically after each verified hostname and after every run.
- The exact timezone-aware scheduler date is persisted for both normal checks
  and next-day failure retries.
- The process schedules a next-day retry after a failed No-IP run.
- Selenium selectors depend on No-IP's website and may need maintenance when
  the site changes.
- Docker runs Chromium in headless mode with a persistent verbose ChromeDriver
  log at `data/chromedriver.log`.
- Automating a third-party site can be affected by its terms and anti-bot
  controls. You are responsible for using this project appropriately.

## License and attribution

Licensed under Apache License 2.0. This project was originally derived from
[loblab/noip-renew](https://github.com/loblab/noip-renew) and has been
substantially modified. See `LICENSE` and `NOTICE`.
