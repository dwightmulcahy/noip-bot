FROM python:3.12-slim-bookworm

# chromium-driver installs to /usr/bin/chromedriver, which the app already
# tries first (see noip_renew/noip_renew.py). Debian keeps chromium and
# chromium-driver version-matched, so no separate driver-download step
# is needed here.
RUN apt-get update && apt-get install -y --no-install-recommends \
        chromium \
        chromium-driver \
        fonts-liberation \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

# Selenium looks for a binary named "chrome"/"google-chrome" by default;
# Debian's package is named "chromium", so point it there explicitly.
ENV CHROME_BIN=/usr/bin/chromium \
    PYTHONUNBUFFERED=1 \
    BIND_ADDR=0.0.0.0 \
    PORT=8080 \
    TZ=America/Costa_Rica \
    SCREENSHOT_DIR=/app/data/screenshots \
    STATE_FILE=/app/data/state.json \
    LOG_LEVEL=INFO \
    HEADLESS=true \
    CHROMEDRIVER_BIN=/usr/bin/chromedriver \
    CHROMEDRIVER_LOG=/app/data/chromedriver.log \
    DRY_RUN=false

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data/screenshots \
    && useradd --system --uid 10001 --create-home noipbot \
    && chown -R noipbot:noipbot /app

USER noipbot

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)" || exit 1

CMD ["python3", "noip_bot.py"]
