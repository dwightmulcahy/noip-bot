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
- Restores a still-future scheduled check instead of rerunning immediately
- Records every discovered hostname, including hosts not yet renewable
- Verifies both confirmation-control removal and changed `data-update`
- Re-reads authoritative host data after renewal instead of fabricating a
  30-day expiration value
- Emits one JSON object per log line for ingestion by Docker logging systems
- Supports a true dry-run mode that never clicks a renewal control
- Provides a web status page and Docker health check
- Provides machine-readable `/health` and `/status.json` endpoints
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
| `NOTIFICATION_TIMEOUT_SECONDS` | Maximum notification blocking time | `30` |
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
| `DRY_RUN` | Discover renewable hosts without clicking Renew | `false` |
| `SKIP_INITIAL_RUN` | Start services without an immediate No-IP check | `false` |
| `MAX_CHECK_INTERVAL_DAYS` | Hard cap between No-IP checks | `5` |

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

Development installs include Ruff, Mypy, and pre-commit:

```sh
pip install -r requirements-dev.txt
pre-commit install
ruff check .
ruff format --check .
mypy
```

Run the unit tests with:

```sh
python3 -m unittest discover -s tests -v
```

The project archive includes all internal modules. If PyCharm reports a missing
`utils.iputils` or `utils.uptime` module, replace the project from the
current archive rather than reusing an older extracted copy.

To validate renewal discovery without changing any hostname:

```sh
DRY_RUN=true docker compose up --build
```

Dry-run results are written to `state.json` as `dry_run` and
`would_renew`, and are exposed by `/health` and `/status.json`. Enabling
dry-run bypasses a restored future schedule once so the validation runs
immediately.

`SKIP_INITIAL_RUN=true` is intended for container smoke tests and maintenance.
It starts the scheduler and status server without contacting No-IP. Until a
real renewal check succeeds, `/health` correctly remains unhealthy.

## Operational notes

- The supported runtime is Docker or Python 3.12+; obsolete Heroku and Python
  3.6 compatibility scaffolding has been removed.
- A navigation or renewal failure now fails the run instead of being treated as
  “nothing to renew.”
- A hostname is only recorded as renewed after its confirmation control
  disappears and its `data-update` attribute changes.
- `expires_in_days` is stored only when No-IP actually displays it. When it
  is absent, scheduling uses clearly labeled `estimated_expiration` and
  `estimated_days_until_expiry` fields derived from `data-update`.
- Derived timing can never postpone a real No-IP check beyond
  `MAX_CHECK_INTERVAL_DAYS`; the default safety cap is five days.
- State is written atomically after each verified hostname and after every run.
- The exact timezone-aware scheduler date is persisted for both normal checks
  and next-day failure retries.
- The process schedules a next-day retry after a failed No-IP run.
- Notification delivery failures are isolated from renewal and scheduling. They
  are recorded under `notifications` in `state.json` and exposed as
  `notification_status` by `/health` and `/status.json`; they do not make the
  renewal health check fail. An unconfigured sender reports `disabled`.
- State updates use an inter-process file lock and reload the latest state
  before mutation so scheduler, web, and notification writers do not overwrite
  one another.
- Selenium selectors depend on No-IP's website and may need maintenance when
  the site changes.
- Docker runs Chromium in headless mode with a persistent verbose ChromeDriver
  log at `data/chromedriver.log`.
- Automating a third-party site can be affected by its terms and anti-bot
  controls. You are responsible for using this project appropriately.

## Continuous integration and releases

Every push and pull request runs the Python test suite, compiles all Python
sources, verifies the application imports, builds and boots the Docker image,
checks `/status.json` and `/health`, and scans the image with Trivy. Fixable
high or critical vulnerabilities fail verification.

CI also enforces Ruff linting and formatting plus Mypy checks for the typed
configuration, orchestration, state, scheduling, health, and notification core.

CI separately verifies installed versions of security-sensitive Python
packages before Trivy runs. Trivy ignores pip's embedded
`pip/_vendor/bom.cdx.json` because it describes pip's build environment—not
packages installed in this image—and otherwise produces false positives.

Publishing a GitHub Release builds and pushes a multi-architecture
`linux/amd64` and `linux/arm64` image to:

```text
dwightmulcahy/noip-bot
```

Release images include BuildKit provenance and SPDX SBOM attestations.
Dependabot maintains Python, Docker, and SHA-pinned GitHub Actions dependencies.

The application version is injected from the GitHub Release tag during the
Docker build. Tags such as `0.2.3` and `v0.2.3` both make the application
report version `0.2.3`. Local source runs fall back to
`git describe --tags --always --dirty`; local Docker builds can set
`APP_VERSION`.

Configure these GitHub repository secrets before publishing a release:

| Secret | Value |
| --- | --- |
| `DOCKERHUB_USERNAME` | Docker Hub username, normally `dwightmulcahy` |
| `DOCKERHUB_TOKEN` | Docker Hub access token with Read & Write permission |

For a release tagged `v0.4.0`, the workflow publishes:

```text
dwightmulcahy/noip-bot:0.4.0
dwightmulcahy/noip-bot:0.4
dwightmulcahy/noip-bot:0
dwightmulcahy/noip-bot:latest
```

Create releases from semantic-version tags:

```sh
git tag -a v0.4.0 -m "No-IP Bot v0.4.0"
git push origin v0.4.0
gh release create v0.4.0 --generate-notes
```

## License and attribution

Licensed under Apache License 2.0. This project was originally derived from
[loblab/noip-renew](https://github.com/loblab/noip-renew) and has been
substantially modified. See `LICENSE` and `NOTICE`.
