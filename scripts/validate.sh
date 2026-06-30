#!/usr/bin/env bash
set -euo pipefail

APP_URL="${APP_URL:-http://localhost:8088}"
READY_TIMEOUT_SECONDS="${READY_TIMEOUT_SECONDS:-90}"
ENDPOINTS=("/api/health" "/api/mission" "/api/worker/status" "/api/brain" "/api/observations" "/api/recommendations" "/api/events" "/api/events/latest" "/api/events/types" "/api/events/statistics" "/api/service-classifications" "/api/assets" "/api/assets/search" "/api/assets/relationships" "/api/policies" "/api/policy-decisions" "/api/policy-decisions/latest" "/api/actions" "/api/action-log")

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

check_live_route() {
  local path="$1"
  local label="$2"
  local marker="${3:-}"
  local url="${APP_URL}${path}"
  local response_file="/tmp/jarvis-validate-ui-response.txt"
  local code

  code=$(curl -sS -o "$response_file" -w "%{http_code}" --max-time 10 "$url" || true)
  if [ "$code" != "200" ]; then
    echo "ERROR: ${url} returned HTTP ${code}."
    cat "$response_file" || true
    fail "Live ${label} check failed for ${path}."
  fi
  if [ -n "$marker" ] && ! grep -Fq -- "$marker" "$response_file"; then
    echo "ERROR: ${url} did not contain the expected marker: ${marker}"
    cat "$response_file" || true
    fail "Live ${label} is stale or incorrect after rebuild."
  fi
  echo "OK: ${label} at ${path} returned HTTP 200${marker:+ with expected marker}"
}

check_live_redirect() {
  local path="$1"
  local expected_location="$2"
  local headers_file="/tmp/jarvis-validate-redirect-headers.txt"
  local code
  local location

  code=$(curl -sS -D "$headers_file" -o /dev/null -w "%{http_code}" --max-time 10 "${APP_URL}${path}" || true)
  if [ "$code" != "303" ]; then
    fail "Live redirect check for ${path} returned HTTP ${code}, expected 303."
  fi
  location=$(awk 'BEGIN {IGNORECASE=1} /^Location:/ {sub(/\r$/, "", $2); print $2}' "$headers_file" | tail -n 1)
  if [ "$location" != "$expected_location" ]; then
    fail "Live redirect check for ${path} returned Location ${location:-missing}, expected ${expected_location}."
  fi
  echo "OK: ${path} redirects to ${expected_location}"
}

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  PYTHON_BIN=""
  echo "WARNING: no host Python found; endpoint checks continue."
fi

echo "[1/10] Running privacy check"
bash scripts/privacy_check.sh || {
  echo "ERROR: privacy check failed."
  exit 1
}

echo "[2/10] Running focused authentication, dashboard, Action Engine, verification, atomic queue, dependency safety, Docker transition, worker queue, policy seed, and privacy tests"
if [ -z "$PYTHON_BIN" ]; then
  echo "ERROR: Python is required for focused tests."
  exit 1
fi
PYTHONPATH=. "$PYTHON_BIN" tests/test_auth_roles.py
PYTHONPATH=. "$PYTHON_BIN" tests/test_dashboard_routes.py
PYTHONPATH=. "$PYTHON_BIN" tests/test_action_state_machine.py
PYTHONPATH=. "$PYTHON_BIN" tests/test_action_verification.py
PYTHONPATH=. "$PYTHON_BIN" tests/test_action_queue_atomic.py
PYTHONPATH=. "$PYTHON_BIN" tests/test_dependency_safety.py
PYTHONPATH=. "$PYTHON_BIN" tests/test_docker_transition_events.py
PYTHONPATH=. "$PYTHON_BIN" tests/test_worker_action_queue.py
PYTHONPATH=. "$PYTHON_BIN" tests/test_policy_seed_migration.py
PYTHONPATH=. "$PYTHON_BIN" tests/test_privacy_check.py

echo "[3/10] Checking Docker"
command -v docker >/dev/null 2>&1 || fail "docker was not found."
docker compose version >/dev/null 2>&1 || fail "docker compose was not found."
docker --version
docker compose version

echo "[4/10] Checking Docker Compose config"
docker compose config >/dev/null || fail "docker compose config failed."

echo "[5/10] Building and force-recreating Jarvis-os service"
docker compose up -d --build --force-recreate jarvis-os || fail "docker compose up -d --build --force-recreate jarvis-os failed."

echo "[6/10] Waiting for Jarvis-os at ${APP_URL}"
start_time=$(date +%s)
while true; do
  if curl -fsS --max-time 3 "${APP_URL}/api/health" >/dev/null 2>&1; then
    break
  fi
  elapsed=$(($(date +%s) - start_time))
  [ "$elapsed" -lt "$READY_TIMEOUT_SECONDS" ] || fail "Jarvis-os did not become ready within ${READY_TIMEOUT_SECONDS} seconds."
  sleep 2
done

echo "[7/10] Checking live authenticated v0.8 routes and assets"
check_live_route "/" "family dashboard" "Her er et roligt overblik over hjemmet"
check_live_route "/login" "login page" "Log ind på Jarvis"
check_live_redirect "/admin" "/login?next=/admin"
check_live_route "/static/admin.html" "Mission Control static page" "Mission Control"
check_live_route "/static/js/login.js" "login JavaScript"
check_live_route "/static/js/family.js" "family dashboard JavaScript"
check_live_route "/static/js/admin.js" "Mission Control JavaScript"
check_live_route "/static/css/login.css" "login stylesheet"
check_live_route "/static/css/family.css" "family dashboard stylesheet"
check_live_route "/static/css/admin.css" "Mission Control stylesheet"

echo "[8/10] Checking API endpoints"
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

echo "[9/10] Reading live Docker, asset, event, policy, and action snapshots"
curl -fsS --max-time 10 "${APP_URL}/api/containers" -o /tmp/jarvis-containers.json || fail "Could not read /api/containers"
curl -fsS --max-time 10 "${APP_URL}/api/mission" -o /tmp/jarvis-mission.json || fail "Could not read /api/mission"
curl -fsS --max-time 10 "${APP_URL}/api/assets" -o /tmp/jarvis-assets.json || fail "Could not read /api/assets"
curl -fsS --max-time 10 "${APP_URL}/api/events/latest" -o /tmp/jarvis-events.json || fail "Could not read /api/events/latest"
curl -fsS --max-time 10 "${APP_URL}/api/policies" -o /tmp/jarvis-policies.json || fail "Could not read /api/policies"
curl -fsS --max-time 10 "${APP_URL}/api/policy-decisions/latest" -o /tmp/jarvis-policy-decisions.json || fail "Could not read /api/policy-decisions/latest"
curl -fsS --max-time 10 "${APP_URL}/api/actions" -o /tmp/jarvis-actions.json || fail "Could not read /api/actions"

echo "[10/10] Checking live Docker, Asset Registry, Event Engine, Policy Engine, and Action Engine consistency"
PYTHONPATH=. "$PYTHON_BIN" tests/test_live_validation.py

echo "Validation OK."
