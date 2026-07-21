#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE=(
  docker compose
  -p jarvis-staging
  -f compose.staging.yml
)

APP_URL="${STAGING_URL:-http://127.0.0.1:8098}"

case "${1:-test}" in
  test)
    .venv/bin/python tests/test_staging_compose.py
    "${COMPOSE[@]}" config >/dev/null
    "${COMPOSE[@]}" up -d --build --remove-orphans

    for attempt in $(seq 1 30); do
      if curl -fsS --max-time 3 "$APP_URL/login" >/dev/null; then
        echo "Staging svarer korrekt på $APP_URL"
        "${COMPOSE[@]}" ps
        exit 0
      fi
      sleep 1
    done

    echo "Staging blev ikke klar"
    "${COMPOSE[@]}" logs --tail=80
    exit 1
    ;;

  status)
    "${COMPOSE[@]}" ps
    ;;

  logs)
    "${COMPOSE[@]}" logs --tail="${2:-80}"
    ;;

  down)
    "${COMPOSE[@]}" down
    ;;

  *)
    echo "Brug: scripts/staging.sh {test|status|logs|down}"
    exit 2
    ;;
esac
