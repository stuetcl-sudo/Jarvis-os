#!/usr/bin/env bash
set -euo pipefail

echo "[1/3] Checking Python imports"
python - <<'PY'
import app.config
import app.db
import app.docker_monitor
import app.health
import app.main
import app.safety
import app.worker
print('Python imports OK')
PY

echo "[2/3] Checking FastAPI app loads"
python - <<'PY'
from app.main import app
assert app.title == 'Jarvis-os'
print('FastAPI app OK')
PY

echo "[3/3] Checking Docker Compose config"
docker compose config >/dev/null

echo "Validation OK"
