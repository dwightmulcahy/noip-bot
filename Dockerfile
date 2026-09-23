FROM python:3.12.13-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2

ARG APP_VERSION=0.0.0-dev

# chromium-driver installs to /usr/bin/chromedriver, which the app already
# tries first (see noip_renew/noip_renew.py). Debian keeps chromium and
# chromium-driver version-matched, so no separate driver-download step
# is needed here.
RUN apt-get update && apt-get install -y --no-install-recommends \
        chromium \
        chromium-driver \
        fonts-liberation \
        libpcre2-8-0 \
        tzdata \
    && installed_pcre2="$(dpkg-query -W -f='${Version}' libpcre2-8-0)" \
    && dpkg --compare-versions "$installed_pcre2" ge "10.42-1+deb12u1" \
    && rm -rf /var/lib/apt/lists/*

# Selenium looks for a binary named "chrome"/"google-chrome" by default;
# Debian's package is named "chromium", so point it there explicitly.
ENV CHROME_BIN=/usr/bin/chromium \
    APP_VERSION=${APP_VERSION} \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/home/noipbot \
    XDG_CACHE_HOME=/tmp/noipbot-cache \
    XDG_CONFIG_HOME=/tmp/noipbot-config \
    BIND_ADDR=0.0.0.0 \
    PORT=8080 \
    TZ=America/Costa_Rica \
    SCREENSHOT_DIR=/app/data/screenshots \
    STATE_FILE=/app/data/state.json \
    RUN_LOCK_FILE=/app/data/renewal.run.lock \
    LOG_LEVEL=INFO \
    HEADLESS=true \
    CHROMEDRIVER_BIN=/usr/bin/chromedriver \
    CHROMEDRIVER_LOG=/app/data/chromedriver.log \
    DRY_RUN=false \
    SKIP_INITIAL_RUN=false \
    MAX_CHECK_INTERVAL_DAYS=5 \
    NOTIFICATION_TIMEOUT_SECONDS=30 \
    STATUS_TOKEN=""

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

RUN mkdir -p /app/data/screenshots \
    && useradd --system --uid 10001 --create-home noipbot \
    && chown -R noipbot:noipbot /app

COPY --chown=noipbot:noipbot . .

USER 10001:10001

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)" || exit 1

STOPSIGNAL SIGINT

CMD ["python3", "noip_bot.py"]
