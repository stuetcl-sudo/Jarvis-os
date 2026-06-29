#!/usr/bin/env bash
set -euo pipefail

APP_URL="${APP_URL:-http://localhost:8088}"
READY_TIMEOUT_SECONDS="${READY_TIMEOUT_SECONDS:-90}"
ENDPOINTS=("/api/health" "/api/mission" "/api/worker/status" "/api/brain" "/api/observations" "/api/recommendations" "/api/events" "/api/events/latest" "/api/events/types" "/api/events/statistics")

show_logs() {
  echo ""
  echo "--- docker compose logs --tail=120 ---"
  docker compose logs --tail=120 || true
}

fail() {
  echo "ERROR: $1"
  show_logs
  exit 1
}

if command -v python3 >/dev/null 2>&1; then
  echo "Python sanity: $(python3 --version)"
elif command -v python >/dev/null 2>&1; then
  echo "Python sanity: $(python --version)"
else
  echo "WARNING: Neither python3 nor python was found on the host."
  echo "Continuing because validation runs against the Dockerized app."
fi

echo "[1/6] Checking Docker"
if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker was not found. Install Docker Engine and the Docker Compose plugin first."
  exit 1
fi

echo "Docker: $(docker --version)"

echo "[2/6] Checking Docker Compose plugin"
if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: docker compose was not found. Install the Docker Compose plugin first."
  exit 1
fi

docker compose version

echo "[3/6] Checking Docker Compose config"
docker compose config >/dev/null || {
  echo "ERROR: docker compose config failed."
  exit 1
}

echo "[4/6] Building and starting stack"
docker compose up -d --build || fail "docker compose up -d --build failed."

echo "[5/6] Waiting for Jarvis-os to become ready at ${APP_URL}"
start_time=$(date +%s)
ready=0
while true; do
  if curl -fsS --max-time 3 "${APP_URL}/api/health" >/dev/null 2>&1; then
    ready=1
    break
  fi

  now=$(date +%s)
  elapsed=$((now - start_time))
  if [ "$elapsed" -ge "$READY_TIMEOUT_SECONDS" ]; then
    fail "Jarvis-os did not become ready within ${READY_TIMEOUT_SECONDS} seconds."
  fi

  sleep 2
done

if [ "$ready" -ne 1 ]; then
  fail "Jarvis-os readiness check failed."
fi

echo "[6/6] Checking API endpoints"
for endpoint in "${ENDPOINTS[@]}"; do
  url="${APP_URL}${endpoint}"
  code=$(curl -sS -o /tmp/jarvis-validate-response.txt -w "%{http_code}" --max-time 10 "$url" || true)
  if [ "$code" != "200" ]; then
    echo "ERROR: ${url} returned HTTP ${code}."
    echo "--- response body ---"
    cat /tmp/jarvis-validate-response.txt || true
    fail "Endpoint validation failed for ${endpoint}."
  fi
  echo "OK: ${endpoint} returned HTTP 200"
done

echo "Validation OK: Dockerized Jarvis-os and Event Engine endpoints are healthy."
