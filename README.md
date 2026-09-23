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
- Escalates failed-run retries from 15 minutes to 1 hour, 6 hours, then 24 hours
- Sends deduplicated failure alerts and a notification after recovery
- Prevents overlapping browser renewals with an inter-process whole-run lock
- Validates live No-IP markup against tested login, MFA, host, and renewal contracts
- Uses injected, instance-owned status services instead of mutable module globals
- Stores diagnostic screenshots in a configurable persistent directory
- Persists verified renewal state atomically across restarts
- Restores a still-future scheduled check instead of rerunning immediately
- Records every discovered hostname, including hosts not yet renewable
- Verifies both confirmation-control removal and changed `data-update`
- Re-reads authoritative host data after renewal instead of fabricating a
  30-day expiration value
- Emits one JSON object per log line for ingestion by Docker logging systems
- Supports a true dry-run mode that never clicks a renewal control
- Provides a minimal unauthenticated `/health` endpoint for container checks
- Protects detailed `/` and `/status.json` responses with bearer authentication
- Redacts host IDs and exception messages from detailed status output
- Runs as a non-root container user
- Runs with a read-only root filesystem, no Linux capabilities, bounded
  memory/PIDs, and `no-new-privileges`

## Quick start with Docker Compose

1. Copy the example configuration:

   ```sh
   cp .env.example .env
   ```

2. Set at minimum `NOIP_ID`, `NOIP_PASSWORD`, and a random `STATUS_TOKEN` in
   `.env`. Generate the status token with `openssl rand -hex 32`. If No-IP
   requires an emailed code, also configure the verification email fields.

3. Build and run:

   ```sh
   docker compose up -d --build
   ```

4. Check public container health and authenticated detailed status:

   ```sh
   curl http://localhost:8080/health
   curl -H "Authorization: Bearer ${STATUS_TOKEN}" \
     http://localhost:8080/status.json
   ```

5. Open `http://localhost:8080/` in a browser and request a six-digit login
   code. The code is emailed to `STATUS_LOGIN_EMAIL` (or `NOIP_ID` when the
   login address is omitted), expires after 10 minutes, and can be used once.
   Browser sessions expire after 12 hours. Set `STATUS_COOKIE_SECURE=true` when
   access is exclusively through an HTTPS reverse proxy.

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
| `STATUS_TOKEN` | Bearer token protecting `/status.json` and signing browser sessions; minimum 32 characters | detailed status disabled |
| `STATUS_LOGIN_EMAIL` | Recipient for six-digit browser-login codes | `NOIP_ID` |
| `STATUS_COOKIE_SECURE` | Require HTTPS for the browser status-session cookie | `false` |
| `TZ` | Scheduler timezone | `America/Costa_Rica` |
| `SCREENSHOT_DIR` | Diagnostic screenshot directory | `/app/data/screenshots` |
| `STATE_FILE` | Persistent renewal-state JSON file | `/app/data/state.json` |
| `RUN_LOCK_FILE` | Inter-process renewal lock and owner metadata | `/app/data/renewal.run.lock` |
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

To validate renewal discovery without changing any hostname:

```sh
DRY_RUN=true docker compose up --build
```

Dry-run results are written to `state.json` as `dry_run` and
`would_renew`, and are exposed by authenticated `/status.json`. Enabling
dry-run bypasses a restored future schedule once so the validation runs
immediately.

`SKIP_INITIAL_RUN=true` is intended for container smoke tests and maintenance.
It starts the scheduler and status server without contacting No-IP. Until a
real renewal check succeeds, `/health` correctly returns HTTP 503 with only
the `status` and `healthy` fields.

## Operational notes

- The supported runtime is Docker or Python 3.12+.
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
- The exact timezone-aware scheduler date is persisted for normal checks and
  failure retries. Retry state survives process and container restarts.
- Failed runs retry after 15 minutes, 1 hour, 6 hours, and then every 24 hours,
  with bounded 10% jitter. The counter resets only after a successful run.
- Failure email is sent on the first failure, on entry into the 24-hour retry
  tier, and weekly thereafter while the outage continues. This prevents alert
  spam while preserving long-running outage reminders. Recovery after one or
  more failures also sends an email.
- Notification delivery failures are isolated from renewal and scheduling. They
  are recorded under `notifications` in `state.json` and exposed as
  `notification_status` by authenticated `/status.json`; they do not make the
  renewal health check fail. An unconfigured sender reports `disabled`.
- Docker Compose publishes the status service only on `127.0.0.1` by default.
  To expose it to a LAN, deliberately change the port mapping and use a strong
  `STATUS_TOKEN`. `/health` remains unauthenticated but contains no timestamps,
  hostnames, errors, or scheduling details. Detailed endpoints return HTTP 503
  when no token of at least 32 characters is configured. The dashboard at `/`
  sends a single-use, six-digit code through the configured Gmail sender and
  establishes a 12-hour, HTTP-only, same-site browser session after verification.
- State updates use an inter-process file lock and reload the latest state
  before mutation so scheduler, web, and notification writers do not overwrite
  one another.
- A separate non-blocking lock covers the complete Selenium renewal operation.
  Concurrent processes sharing the data volume cannot both log in or click
  Renew. Lock contention emits `run_skipped_locked` and does not increment the
  failure counter, schedule a retry, or send a failure notification. The lock
  file contains diagnostic PID, hostname, and acquisition time metadata; the
  operating system releases ownership automatically when a process exits.
- APScheduler also coalesces missed executions and permits only one instance of
  the renewal job inside a process.
- Selenium selectors depend on No-IP's website and may need maintenance when
  the site changes. Sanitized HTML fixtures exercise the expected login, six-box
  MFA, host inventory, renewable-host, verified-renewal, and interstitial page
  contracts without contacting No-IP during tests. Runtime contract violations
  are fatal and enter the normal retry and notification path.
- Docker runs Chromium in headless mode with a persistent verbose ChromeDriver
  log at `data/chromedriver.log`.
- The Python base image is pinned by exact patch version and multi-architecture
  digest. Dependabot should be allowed to update this digest so security fixes
  are deliberate and reviewable rather than silently changing builds.
- The image explicitly upgrades `libpcre2-8-0` from Debian security metadata
  and fails the build if it is older than `10.42-1+deb12u1`, preventing the
  pinned base layer from reintroducing the fixed PCRE2 memory-corruption CVEs.
- The Compose service runs as UID/GID `10001`, drops every Linux capability,
  enables `no-new-privileges`, uses a read-only root filesystem, limits the
  process count to 256 and memory to 1 GiB, and uses an init process for signal
  forwarding and child reaping. Only `/app/data`, `/tmp`, and the ephemeral
  browser home are writable. The temporary filesystems are mounted with
  `nodev`, `nosuid`, and `noexec`.
- Container shutdown uses `SIGINT` with a 30-second grace period so the Python
  cleanup path can stop the scheduler and browser before Docker kills it.
- Automating a third-party site can be affected by its terms and anti-bot
  controls. You are responsible for using this project appropriately.

## Continuous integration and releases

Every push and pull request runs the Python test suite, compiles all Python
sources, verifies the application imports, builds and boots the Docker image,
checks authenticated `/status.json`, rejects unauthorized status access,
checks minimal `/health`, and scans the image with Trivy. Fixable high or
critical vulnerabilities fail verification.

CI also enforces Ruff linting and formatting plus Mypy checks across 14
operational modules: the CLI, typed configuration and orchestration, Selenium
renewal engine, HTML contracts, persistent state, run locking, status server,
scheduling, health, logging, timing, notifications, and version resolution.

CI separately verifies installed versions of security-sensitive Python
packages before Trivy runs. Trivy ignores pip's embedded
`pip/_vendor/bom.cdx.json` because it describes pip's build environment—not
packages installed in this image—and otherwise produces false positives.

Pushing a semantic-version tag whose commit belongs to the `release` branch
builds and pushes a multi-architecture `linux/amd64` and `linux/arm64` image to:

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

The same successful workflow creates the GitHub Release automatically. Its
notes group conventional commits into sections for features, fixes, security,
performance, documentation, tests, CI, and maintenance. Re-running a workflow
updates the existing release instead of creating a duplicate.

Create a release by tagging a commit already on the `release` branch:

```sh
git tag -a v0.4.0 -m "No-IP Bot v0.4.0"
git push origin v0.4.0
```

## License and attribution

Licensed under Apache License 2.0. This project was originally derived from
[loblab/noip-renew](https://github.com/loblab/noip-renew) and has been
substantially modified. See `LICENSE` and `NOTICE`.
