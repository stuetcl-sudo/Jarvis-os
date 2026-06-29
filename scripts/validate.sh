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
  echo "WARNING: no host Python found; endpoint checks continue."
fi

echo "[1/7] Checking Docker"
command -v docker >/dev/null 2>&1 || fail "docker was not found."
docker compose version >/dev/null 2>&1 || fail "docker compose was not found."
docker --version
docker compose version

echo "[2/7] Checking Docker Compose config"
docker compose config >/dev/null || fail "docker compose config failed."

echo "[3/7] Building and starting stack"
docker compose up -d --build || fail "docker compose up -d --build failed."

echo "[4/7] Waiting for Jarvis-os at ${APP_URL}"
start_time=$(date +%s)
while true; do
  if curl -fsS --max-time 3 "${APP_URL}/api/health" >/dev/null 2>&1; then
    break
  fi
  elapsed=$(($(date +%s) - start_time))
  [ "$elapsed" -lt "$READY_TIMEOUT_SECONDS" ] || fail "Jarvis-os did not become ready within ${READY_TIMEOUT_SECONDS} seconds."
  sleep 2
done

echo "[5/7] Checking API endpoints"
for endpoint in "${ENDPOINTS[@]}"; do
  url="${APP_URL}${endpoint}"
  code=$(curl -sS -o /tmp/jarvis-validate-response.txt -w "%{http_code}" --max-time 10 "$url" || true)
  if [ "$code" != "200" ]; then
    echo "ERROR: ${url} returned HTTP ${code}."
    cat /tmp/jarvis-validate-response.txt || true
    fail "Endpoint validation failed for ${endpoint}."
  fi
  echo "OK: ${endpoint} returned HTTP 200"
done

echo "[6/7] Reading live Docker API snapshots"
curl -fsS --max-time 10 "${APP_URL}/api/containers" -o /tmp/jarvis-containers.json || fail "Could not read /api/containers"
curl -fsS --max-time 10 "${APP_URL}/api/mission" -o /tmp/jarvis-mission.json || fail "Could not read /api/mission"

echo "[7/7] Checking live Docker count consistency"
if [ -n "$PYTHON_BIN" ]; then
  "$PYTHON_BIN" - <<'PY'
import json
from pathlib import Path
containers = json.loads(Path('/tmp/jarvis-containers.json').read_text())['containers']
mission = json.loads(Path('/tmp/jarvis-mission.json').read_text())
def state(c): return c.get('docker_state') or c.get('status')
if len(containers) != mission['docker']['total'] or len(containers) != len(mission.get('containers', [])):
    raise SystemExit('Docker totals disagree')
if sum(1 for c in containers if state(c) == 'running') != mission['docker']['running']:
    raise SystemExit('Docker running count disagrees')
if sum(1 for c in containers if state(c) == 'exited') != mission['docker']['stopped']:
    raise SystemExit('Docker stopped count disagrees')
class_total = sum(len(mission.get(k, [])) for k in ['critical_services','optional_services','stopped_by_design','unknown_containers'])
if class_total != len(containers):
    raise SystemExit('Classified sections do not include all containers')
if len([c for c in containers if c.get('classification') == 'unknown']) != len(mission.get('unknown_containers', [])):
    raise SystemExit('Unknown containers are hidden or mismatched')
for c in containers:
    for field in ['docker_state','docker_status','health_status']:
        if field not in c:
            raise SystemExit(f'Missing {field} on {c.get("name")}')
print('Live Docker regression OK')
PY
else
  echo "WARNING: skipped JSON consistency check because host Python is unavailable."
fi

echo "Validation OK."
