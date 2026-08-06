#!/usr/bin/env bash
set -euo pipefail

APP_URL="${APP_URL:-http://localhost:8088}"
READY_TIMEOUT_SECONDS="${READY_TIMEOUT_SECONDS:-90}"
VALIDATE_OWNER_USERNAME="${VALIDATE_OWNER_USERNAME:-}"
VALIDATE_OWNER_PASSWORD="${VALIDATE_OWNER_PASSWORD:-}"
COOKIE_JAR="/tmp/jarvis-validate-cookies.txt"
PROTECTED_ENDPOINTS=("/api/containers" "/api/incidents" "/api/worker/status" "/api/brain" "/api/observations" "/api/recommendations" "/api/events" "/api/events/latest" "/api/events/types" "/api/events/statistics" "/api/service-classifications" "/api/assets" "/api/assets/search" "/api/assets/relationships" "/api/policies" "/api/policy-decisions" "/api/policy-decisions/latest" "/api/actions" "/api/action-log")
AUTHENTICATED_OWNER=false
AUTH_COOKIE_ARGS=()

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

check_live_status_code() {
  local path="$1"
  local expected="$2"
  local label="$3"
  shift 3
  local code
  code=$(curl -sS "$@" -o /tmp/jarvis-validate-status-response.txt -w "%{http_code}" --max-time 10 "${APP_URL}${path}" || true)
  if [ "$code" != "$expected" ]; then
    echo "ERROR: ${APP_URL}${path} returned HTTP ${code}, expected ${expected}."
    cat /tmp/jarvis-validate-status-response.txt || true
    fail "Live ${label} check failed for ${path}."
  fi
  echo "OK: ${label} at ${path} returned HTTP ${expected}"
}

check_live_json_status() {
  local path="$1"
  local label="$2"
  local kind="$3"
  local url="${APP_URL}${path}"
  local response_file="/tmp/jarvis-validate-${kind}-response.json"
  local code

  code=$(curl -sS -o "$response_file" -w "%{http_code}" --max-time 10 "$url" || true)
  if [ "$code" != "200" ]; then
    echo "ERROR: ${url} returned HTTP ${code}."
    fail "Live ${label} check failed for ${path}."
  fi
  if ! "$PYTHON_BIN" scripts/validate_family_status.py "$kind" "$response_file"; then
    fail "Live ${label} returned malformed JSON or an unsupported status."
  fi
  echo "OK: ${label} at ${path} returned HTTP 200 with a supported status"
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

check_live_login() {
  local response_file="/tmp/jarvis-validate-login-page.txt"
  local headers_file="/tmp/jarvis-validate-login-headers.txt"
  local code
  local location

  code=$(curl -sS -D "$headers_file" -o "$response_file" -w "%{http_code}" --max-time 10 "${APP_URL}/login" || true)
  if [ "$code" = "200" ]; then
    if ! grep -Fq -- "Log ind på Jarvis" "$response_file"; then
      echo "ERROR: ${APP_URL}/login returned HTTP 200 without the expected login-page content."
      return 1
    fi
    echo "OK: login page returned HTTP 200 with expected marker"
    return 0
  fi
  if [ "$code" = "303" ]; then
    location=$(awk 'BEGIN {IGNORECASE=1} /^Location:/ {sub(/\r$/, "", $2); print $2}' "$headers_file" | tail -n 1)
    if [ "$location" = "/bootstrap" ]; then
      echo "OK: login redirects to /bootstrap for initial setup"
      return 0
    fi
    echo "ERROR: ${APP_URL}/login returned unapproved Location ${location:-missing}."
    return 1
  fi
  echo "ERROR: ${APP_URL}/login returned HTTP ${code}; expected 200 or approved 303."
  return 1
}

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  PYTHON_BIN=""
  echo "WARNING: no host Python found; endpoint checks continue."
fi

if [ "${VALIDATE_LOGIN_ONLY:-false}" = "true" ]; then
  check_live_login
  exit $?
fi

echo "[1/10] Running privacy check"
bash scripts/privacy_check.sh || {
  echo "ERROR: privacy check failed."
  exit 1
}

echo "[2/10] Running focused security, family, setup, wall dashboard, Action Engine, policy, queue, and privacy tests"
if [ -z "$PYTHON_BIN" ]; then
  echo "ERROR: Python is required for focused tests."
  exit 1
fi
PYTHONPATH=. "$PYTHON_BIN" tests/test_admin_ui.py
PYTHONPATH=. "$PYTHON_BIN" tests/test_frontend_foundation.py
PYTHONPATH=. "$PYTHON_BIN" tests/test_screen_module_layout.py
PYTHONPATH=. "$PYTHON_BIN" tests/test_wall_dashboard.py
PYTHONPATH=. "$PYTHON_BIN" tests/test_login_payload.py
PYTHONPATH=. "$PYTHON_BIN" tests/test_frontend_safety.py
PYTHONPATH=. "$PYTHON_BIN" tests/test_family_routines.py
PYTHONPATH=. "$PYTHON_BIN" tests/test_routine_editor.py
PYTHONPATH=. "$PYTHON_BIN" tests/test_family_visibility.py
PYTHONPATH=. "$PYTHON_BIN" tests/test_family_api_visibility.py
PYTHONPATH=. "$PYTHON_BIN" tests/test_safety_status.py
PYTHONPATH=. "$PYTHON_BIN" tests/test_api_read_access.py
PYTHONPATH=. "$PYTHON_BIN" tests/test_session_touch.py
PYTHONPATH=. "$PYTHON_BIN" tests/test_docker_socket_proxy.py
PYTHONPATH=. "$PYTHON_BIN" tests/test_live_family_status_validation.py
PYTHONPATH=. "$PYTHON_BIN" tests/test_calendar_integration.py
PYTHONPATH=. "$PYTHON_BIN" tests/test_weather_integration.py
PYTHONPATH=. "$PYTHON_BIN" tests/test_family_role_views.py
PYTHONPATH=. "$PYTHON_BIN" tests/test_auth_roles.py
PYTHONPATH=. "$PYTHON_BIN" tests/test_setup_state.py
PYTHONPATH=. "$PYTHON_BIN" tests/test_setup_access.py
PYTHONPATH=. "$PYTHON_BIN" tests/test_home_setup.py
PYTHONPATH=. "$PYTHON_BIN" tests/test_home_entity_settings.py
PYTHONPATH=. "$PYTHON_BIN" tests/test_home_assistant_setup.py
PYTHONPATH=. "$PYTHON_BIN" tests/test_settings_store.py
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

echo "[5/10] Building and force-recreating Jarvis-os and its restricted Docker proxy"
docker compose up -d --build --force-recreate jarvis-os docker-socket-proxy || fail "docker compose up -d --build --force-recreate jarvis-os docker-socket-proxy failed."

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

echo "[7/10] Checking live family routes, authentication boundaries, and assets"
check_live_route "/" "family dashboard" "Her er et roligt overblik over hjemmet"
check_live_redirect "/wall" "/login?next=/wall"
check_live_json_status "/api/family/weather" "family weather API" "weather"
check_live_json_status "/api/family/calendar" "family calendar API" "calendar"
check_live_route "/api/family/routines" "family routines API" '"status":"authentication_required"'
check_live_status_code "/api/family/safety-status" "401" "protected family safety API"
check_live_login || fail "Live login route check failed."
check_live_redirect "/admin" "/login?next=/admin"
check_live_redirect "/setup" "/login?next=/setup"
check_live_route "/static/admin.html" "home administration static page" "Hjemmets administration"
check_live_route "/static/setup.html" "first-run setup static page" "Gør Jarvis klar til hjemmet"
check_live_route "/static/js/login.js" "login JavaScript"
check_live_route "/static/js/family.js" "family dashboard JavaScript"
check_live_route "/static/js/routines.js" "routine JavaScript"
check_live_route "/static/js/routine-editor.js" "routine editor JavaScript"
check_live_route "/static/js/wall-safety.js" "wall safety JavaScript" "/api/family/safety-status"
check_live_route "/static/js/wall-fullscreen.js" "wall fullscreen JavaScript" "requestFullscreen"
check_live_route "/static/js/admin.js" "home administration JavaScript" "adminSections"
check_live_route "/static/js/admin-render.js" "admin render JavaScript" "renderActions"
check_live_route "/static/js/admin-page.js" "admin page JavaScript" "initializeAdmin"
check_live_route "/static/js/admin-screens.js" "admin screen management JavaScript" "screenAdminPanel"
check_live_route "/static/js/setup.js" "setup JavaScript" "credentials = \"same-origin\""
check_live_route "/static/css/tokens.css" "shared design tokens" "--jarvis-color-bg"
check_live_route "/static/css/base.css" "shared base stylesheet" "button:focus-visible"
check_live_route "/static/css/components.css" "shared component stylesheet" ".jarvis-card"
check_live_route "/static/css/layout.css" "shared layout stylesheet" ".jarvis-grid"
check_live_route "/static/css/login.css" "login stylesheet"
check_live_route "/static/css/family.css" "family dashboard stylesheet"
check_live_route "/static/css/weather.css" "weather stylesheet"
check_live_route "/static/css/calendar.css" "calendar stylesheet"
check_live_route "/static/css/routines.css" "routine stylesheet"
check_live_route "/static/css/routine-editor.css" "routine editor stylesheet"
check_live_route "/static/css/wall-mode.css" "wall dashboard stylesheet" ".wall-safety-strip"
check_live_route "/static/css/wall-safety-polish.css" "wall safety stylesheet" ".wall-safety-item.ok"
check_live_route "/static/css/admin.css" "home administration stylesheet" ".admin-shell"
check_live_route "/static/css/admin-connections.css" "Home Assistant administration stylesheet" ".entity-selector-grid"
check_live_route "/static/css/setup.css" "setup stylesheet" ".setup-shell"
check_live_route "/static/pictograms/routines.svg" "routine pictograms" "symbol id=\"complete\""

echo "[8/10] Checking protected technical API behavior"
check_live_status_code "/api/health" "200" "redacted public health API"
check_live_status_code "/api/mission" "200" "redacted public mission API"
check_live_status_code "/openapi.json" "401" "protected API schema"

if [ -n "$VALIDATE_OWNER_USERNAME" ] && [ -n "$VALIDATE_OWNER_PASSWORD" ]; then
  rm -f "$COOKIE_JAR"
  login_payload=$(VALIDATE_OWNER_USERNAME="$VALIDATE_OWNER_USERNAME" VALIDATE_OWNER_PASSWORD="$VALIDATE_OWNER_PASSWORD" "$PYTHON_BIN" -c 'import json, os; print(json.dumps({"username": os.environ["VALIDATE_OWNER_USERNAME"], "password": os.environ["VALIDATE_OWNER_PASSWORD"]}))')
  login_code=$(curl -sS -c "$COOKIE_JAR" -o /tmp/jarvis-validate-login.json -w "%{http_code}" --max-time 10 -H "Content-Type: application/json" -d "$login_payload" "${APP_URL}/api/auth/login" || true)
  [ "$login_code" = "200" ] || fail "Owner validation login returned HTTP ${login_code}."
  AUTHENTICATED_OWNER=true
  AUTH_COOKIE_ARGS=(-b "$COOKIE_JAR")
  check_live_status_code "/openapi.json" "200" "owner-authenticated API schema" "${AUTH_COOKIE_ARGS[@]}"
  echo "OK: validation owner login succeeded"
fi

for endpoint in "${PROTECTED_ENDPOINTS[@]}"; do
  if [ "$AUTHENTICATED_OWNER" = true ]; then
    check_live_status_code "$endpoint" "200" "owner-authenticated technical API" "${AUTH_COOKIE_ARGS[@]}"
  else
    check_live_status_code "$endpoint" "401" "anonymous technical API protection"
  fi
done

if [ "$AUTHENTICATED_OWNER" = true ]; then
  echo "[9/10] Reading authenticated live Docker, asset, event, policy, and action snapshots"
  curl -fsS "${AUTH_COOKIE_ARGS[@]}" --max-time 10 "${APP_URL}/api/containers" -o /tmp/jarvis-containers.json || fail "Could not read /api/containers"
  curl -fsS "${AUTH_COOKIE_ARGS[@]}" --max-time 10 "${APP_URL}/api/mission" -o /tmp/jarvis-mission.json || fail "Could not read /api/mission"
  curl -fsS "${AUTH_COOKIE_ARGS[@]}" --max-time 10 "${APP_URL}/api/assets" -o /tmp/jarvis-assets.json || fail "Could not read /api/assets"
  curl -fsS "${AUTH_COOKIE_ARGS[@]}" --max-time 10 "${APP_URL}/api/events/latest" -o /tmp/jarvis-events.json || fail "Could not read /api/events/latest"
  curl -fsS "${AUTH_COOKIE_ARGS[@]}" --max-time 10 "${APP_URL}/api/policies" -o /tmp/jarvis-policies.json || fail "Could not read /api/policies"
  curl -fsS "${AUTH_COOKIE_ARGS[@]}" --max-time 10 "${APP_URL}/api/policy-decisions/latest" -o /tmp/jarvis-policy-decisions.json || fail "Could not read /api/policy-decisions/latest"
  curl -fsS "${AUTH_COOKIE_ARGS[@]}" --max-time 10 "${APP_URL}/api/actions" -o /tmp/jarvis-actions.json || fail "Could not read /api/actions"

  echo "[10/10] Checking live Docker, Asset Registry, Event Engine, Policy Engine, and Action Engine consistency"
  PYTHONPATH=. "$PYTHON_BIN" tests/test_live_validation.py
else
  echo "[9/10] Skipping authenticated live snapshots; set VALIDATE_OWNER_USERNAME and VALIDATE_OWNER_PASSWORD to enable them"
  echo "[10/10] Protected endpoint access checks completed"
fi

echo "Validation OK."
