#!/usr/bin/env bash
set -euo pipefail

REPOSITORY_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-}"
STAGING_COMPOSE_FILE="$REPOSITORY_ROOT/compose.staging.yml"
STAGING_PORT="${STAGING_PORT:-8098}"
APP_URL="${APP_URL:-http://127.0.0.1:${STAGING_PORT}}"
MODE="${1:-local}"

fail() { echo "ERROR: $1" >&2; exit 1; }

[ "$COMPOSE_PROJECT_NAME" = "jarvis-staging" ] || fail "COMPOSE_PROJECT_NAME must be exactly jarvis-staging."
[ "$STAGING_PORT" != "8088" ] || fail "Staging must never use production port 8088."
[ "$STAGING_PORT" = "8098" ] || fail "STAGING_PORT must be 8098."
[ "$APP_URL" = "http://127.0.0.1:8098" ] || fail "APP_URL must be http://127.0.0.1:8098."
[ -f "$STAGING_COMPOSE_FILE" ] || fail "compose.staging.yml was not found."
[ -x "$REPOSITORY_ROOT/.venv/bin/python3" ] || fail "The existing .venv Python was not found."

cd "$REPOSITORY_ROOT"
export PATH="$REPOSITORY_ROOT/.venv/bin:$PATH"
export PYTHONPATH="$REPOSITORY_ROOT"

echo "[staging 1/2] Running privacy check"
bash scripts/privacy_check.sh
echo "[staging 2/2] Running local tests from validate.sh with .venv"
mapfile -t TEST_FILES < <(awk '/echo "\[3\/10\] Checking Docker"/ { exit } /^PYTHONPATH=\. "\$PYTHON_BIN" tests\// { print $3 }' scripts/validate.sh)
[ "${#TEST_FILES[@]}" -gt 0 ] || fail "No local tests were found in scripts/validate.sh."
for test_file in "${TEST_FILES[@]}"; do
  echo "RUNNING: $test_file"
  python3 "$test_file"
done

if [ "$MODE" = "local" ]; then
  echo "Local staging validation OK. No Docker commands were run."
  exit 0
fi
[ "$MODE" = "--with-docker" ] || fail "Usage: COMPOSE_PROJECT_NAME=jarvis-staging bash scripts/validate_staging.sh [local|--with-docker]"
[ -f "$REPOSITORY_ROOT/.env.staging" ] || fail ".env.staging is required for --with-docker."

staging_compose() {
  docker compose --file "$STAGING_COMPOSE_FILE" --project-name "$COMPOSE_PROJECT_NAME" "$@"
}

staging_compose config >/dev/null
staging_compose up -d --build --force-recreate jarvis-os
ready=false
for _attempt in $(seq 1 45); do
  if curl -fsS --max-time 3 "${APP_URL}/api/health" >/dev/null 2>&1; then ready=true; break; fi
  sleep 2
done
if [ "$ready" != true ]; then
  staging_compose logs --tail=120 jarvis-os || true
  fail "Staging did not become ready at ${APP_URL}."
fi
[ "$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 "${APP_URL}/")" = "200" ] || fail "Dashboard did not return HTTP 200."
[ "$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 "${APP_URL}/api/health")" = "200" ] || fail "Health did not return HTTP 200."
[ "$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 "${APP_URL}/openapi.json")" = "401" ] || fail "OpenAPI was not protected."
[ "$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 "${APP_URL}/api/containers")" = "401" ] || fail "Container API was not protected."
echo "Staging validation OK. Only the explicit staging Compose project was addressed."
