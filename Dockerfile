FROM python:3.12-slim-bookworm

# Only the chromium browser binary is installed from apt — the driver is
# intentionally NOT installed here. undetected-chromedriver downloads and
# stealth-patches its own chromedriver matching the installed Chromium
# version at runtime; reusing a plain apt-installed driver would undermine
# that patching (the whole point of using undetected-chromedriver).
RUN apt-get update && apt-get install -y --no-install-recommends \
        chromium \
        fonts-liberation \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

ENV CHROME_BIN=/usr/bin/chromium \
    PYTHONUNBUFFERED=1 \
    BIND_ADDR=0.0.0.0 \
    PORT=8080 \
    HEADLESS=true

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["python3", "noip_bot.py"]
