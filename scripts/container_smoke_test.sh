#!/usr/bin/env bash
set -euo pipefail

image="${1:-noip-bot:verify}"
container="noip-bot-smoke-${RANDOM}"

cleanup() {
  docker logs "$container" 2>/dev/null || true
  docker rm -f "$container" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker run --detach --name "$container" \
  --no-healthcheck \
  --publish 127.0.0.1::8080 \
  --env SKIP_INITIAL_RUN=true \
  --env STATE_FILE=/app/data/smoke-state.json \
  "$image" >/dev/null

port="$(docker port "$container" 8080/tcp | sed 's/.*://')"
for attempt in {1..30}; do
  if curl --fail --silent "http://127.0.0.1:${port}/status.json" >/tmp/noip-status.json; then
    break
  fi
  if [[ "$attempt" == 30 ]]; then
    echo "status endpoint did not become ready" >&2
    exit 1
  fi
  sleep 1
done

python3 - /tmp/noip-status.json <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as status_file:
    payload = json.load(status_file)
assert payload["status"] == "unhealthy", payload
assert payload["healthy"] is False, payload
assert "hosts" in payload, payload
PY

http_code="$(curl --silent --output /tmp/noip-health.json --write-out '%{http_code}' \
  "http://127.0.0.1:${port}/health")"
test "$http_code" = "503"
python3 - /tmp/noip-health.json <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as health_file:
    payload = json.load(health_file)
assert payload["status"] == "unhealthy", payload
assert "no successful renewal check has completed" in payload["reasons"], payload
PY
