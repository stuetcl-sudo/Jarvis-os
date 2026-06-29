#!/usr/bin/env bash
set -euo pipefail

APP_URL="${APP_URL:-http://localhost:8088}"
READY_TIMEOUT_SECONDS="${READY_TIMEOUT_SECONDS:-90}"
ENDPOINTS=("/api/health" "/api/mission" "/api/worker/status" "/api/brain" "/api/observations" "/api/recommendations" "/api/events" "/api/events/latest" "/api/events/types" "/api/events/statistics" "/api/service-classifications")

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
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  PYTHON_BIN=""
  echo "WARNING: Neither python3 nor python was found on the host."
  echo "Continuing because endpoint validation runs against the Dockerized app."
fi

if [ -n "$PYTHON_BIN" ]; then
  echo "Python sanity: $($PYTHON_BIN --version)"
fi

echo "[1/7] Checking Docker"
if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker was not found. Install Docker Engine and the Docker Compose plugin first."
  exit 1
fi

echo "Docker: $(docker --version)"

echo "[2/7] Checking Docker Compose plugin"
if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: docker compose was not found. Install the Docker Compose plugin first."
  exit 1
fi

docker compose version

echo "[3/7] Checking Docker Compose config"
docker compose config >/dev/null || {
  echo "ERROR: docker compose config failed."
  exit 1
}

echo "[4/7] Building and starting stack"
docker compose up -d --build || fail "docker compose up -d --build failed."

echo "[5/7] Waiting for Jarvis-os to become ready at ${APP_URL}"
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

echo "[6/7] Checking API endpoints"
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

echo "[7/7] Regression: /api/containers and /api/mission live Docker counts agree"
if [ -z "$PYTHON_BIN" ]; then
  echo "WARNING: detailed JSON regression skipped because no host Python is available."
  echo "Endpoint checks still passed. Install python3 for full regression validation."
else
  "$PYTHON_BIN" - <<'PY' || fail "Live Docker state regression failed."
import json
import os
import urllib.request

base = os.environ.get("APP_URL", "http://localhost:8088")

def fetch(path):
    with urllib.request.urlopen(base + path, timeout=10) as response:
        if response.status != 200:
            raise SystemExit(f"{path} returned HTTP {response.status}")
        return json.loads(response.read().decode("utf-8"))

containers_payload = fetch("/api/containers")
mission = fetch("/api/mission")
containers = containers_payload.get("containers", [])
mission_containers = mission.get("containers", [])

def state(item):
    return item.get("docker_state") or item.get("status")

expected = {
    "total": len(containers),
    "running": len([c for c in containers if state(c) == "running"]),
    "stopped": len([c for c in containers if state(c) == "exited"]),
}
actual = mission.get("docker", {})
for key, value in expected.items():
    if actual.get(key) != value:
        raise SystemExit(f"Count mismatch for {key}: containers={value}, mission={actual.get(key)}")

if len(mission_containers) != len(containers):
    raise SystemExit("Mission does not include all containers")

required_fields = ["docker_state", "docker_status", "health_status", "classification"]
for item in mission_containers:
    for field in required_fields:
        if field not in item:
            raise SystemExit(f"Container {item.get('name')} missing {field}")
    if item["classification"] == "unknown" and item.get("auto_start_allowed"):
        raise SystemExit(f"Unknown container {item.get('name')} has auto_start_allowed=true")

unknown_count = len([c for c in mission_containers if c.get("classification") == "unknown"])
if len(mission.get("unknown_containers", [])) != unknown_count:
    raise SystemExit("Unknown containers are hidden or count mismatch")

print("Live Docker state regression OK")
PY
fi

echo "Validation OK: Dockerized Jarvis-os, Event Engine endpoints, and live Docker state are healthy."
