#!/usr/bin/env bash
set -euo pipefail

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "ERROR: Neither python3 nor python was found."
  echo "Install Python on Ubuntu 24.04 with: sudo apt update && sudo apt install -y python3 python3-venv"
  exit 1
fi

echo "Using Python: $($PYTHON_BIN --version)"

echo "[1/4] Checking Python imports"
"$PYTHON_BIN" - <<'PY'
import app.config
import app.db
import app.docker_monitor
import app.health
import app.main
import app.safety
import app.worker
import fastapi
import uvicorn
print('Python imports OK')
PY

echo "[2/4] Checking FastAPI app object"
"$PYTHON_BIN" - <<'PY'
from fastapi import FastAPI
from app.main import app
assert isinstance(app, FastAPI)
assert app.title == 'Jarvis-os'
print('FastAPI app object OK')
PY

echo "[3/4] Checking FastAPI startup route registration"
"$PYTHON_BIN" - <<'PY'
from app.main import app
routes = sorted([getattr(route, 'path', '') for route in app.routes])
required = ['/', '/api/mission', '/api/worker/status', '/api/incidents']
missing = [path for path in required if path not in routes]
if missing:
    raise SystemExit(f'Missing required routes: {missing}')
print('FastAPI routes OK')
PY

echo "[4/4] Checking Docker Compose config"
if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker was not found. Install Docker Engine and Docker Compose plugin first."
  exit 1
fi

docker compose version >/dev/null
docker compose config >/dev/null

echo "Validation OK"
