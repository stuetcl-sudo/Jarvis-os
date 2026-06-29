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

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  PYTHON_BIN=""
  echo "WARNING: no host Python found; endpoint checks continue."
fi

echo "[1/9] Running privacy check"
bash scripts/privacy_check.sh || {
  echo "ERROR: privacy check failed."
  exit 1
}

echo "[2/9] Running focused Action Engine tests"
if [ -z "$PYTHON_BIN" ]; then
  echo "ERROR: Python is required for focused Action Engine tests."
  exit 1
fi
PYTHONPATH=. "$PYTHON_BIN" tests/test_action_state_machine.py

echo "[3/9] Checking Docker"
command -v docker >/dev/null 2>&1 || fail "docker was not found."
docker compose version >/dev/null 2>&1 || fail "docker compose was not found."
docker --version
docker compose version

echo "[4/9] Checking Docker Compose config"
docker compose config >/dev/null || fail "docker compose config failed."

echo "[5/9] Building and starting stack"
docker compose up -d --build || fail "docker compose up -d --build failed."

echo "[6/9] Waiting for Jarvis-os at ${APP_URL}"
start_time=$(date +%s)
while true; do
  if curl -fsS --max-time 3 "${APP_URL}/api/health" >/dev/null 2>&1; then
    break
  fi
  elapsed=$(($(date +%s) - start_time))
  [ "$elapsed" -lt "$READY_TIMEOUT_SECONDS" ] || fail "Jarvis-os did not become ready within ${READY_TIMEOUT_SECONDS} seconds."
  sleep 2
done

echo "[7/9] Checking API endpoints"
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

echo "[8/9] Reading live Docker, asset, event, policy, and action snapshots"
curl -fsS --max-time 10 "${APP_URL}/api/containers" -o /tmp/jarvis-containers.json || fail "Could not read /api/containers"
curl -fsS --max-time 10 "${APP_URL}/api/mission" -o /tmp/jarvis-mission.json || fail "Could not read /api/mission"
curl -fsS --max-time 10 "${APP_URL}/api/assets" -o /tmp/jarvis-assets.json || fail "Could not read /api/assets"
curl -fsS --max-time 10 "${APP_URL}/api/events/latest" -o /tmp/jarvis-events.json || fail "Could not read /api/events/latest"
curl -fsS --max-time 10 "${APP_URL}/api/policies" -o /tmp/jarvis-policies.json || fail "Could not read /api/policies"
curl -fsS --max-time 10 "${APP_URL}/api/policy-decisions/latest" -o /tmp/jarvis-policy-decisions.json || fail "Could not read /api/policy-decisions/latest"
curl -fsS --max-time 10 "${APP_URL}/api/actions" -o /tmp/jarvis-actions.json || fail "Could not read /api/actions"

echo "[9/9] Checking live Docker, Asset Registry, Event Engine, Policy Engine, and Action Engine consistency"
"$PYTHON_BIN" - <<'PY'
import json
from pathlib import Path
containers_response = json.loads(Path('/tmp/jarvis-containers.json').read_text())
containers = containers_response['containers']
mission = json.loads(Path('/tmp/jarvis-mission.json').read_text())
assets = json.loads(Path('/tmp/jarvis-assets.json').read_text())['assets']
policies = json.loads(Path('/tmp/jarvis-policies.json').read_text())['policies']
decisions = json.loads(Path('/tmp/jarvis-policy-decisions.json').read_text())['decisions']
actions = json.loads(Path('/tmp/jarvis-actions.json').read_text())['actions']
asset_ids = {a['asset_id'] for a in assets}
mission_containers = mission.get('containers', [])
mission_by_name = {c['name']: c for c in mission_containers}
if not policies:
    raise SystemExit('Policy Engine has no policies')
for p in policies:
    for field in ['policy_id','name','enabled','priority','trigger_event_type','conditions','actions','safety_level']:
        if field not in p:
            raise SystemExit(f'Missing {field} on policy')
for d in decisions:
    for field in ['decision_id','policy_id','timestamp','matched','allowed','action','reason','explanation','dry_run']:
        if field not in d:
            raise SystemExit(f'Missing {field} on policy decision')
for a in actions:
    for field in ['action_id','created_at','updated_at','requested_by','source','asset_id','action_type','status','requires_approval','approved','safety_status','reason','explanation','payload','result']:
        if field not in a:
            raise SystemExit(f'Missing {field} on action')
    if a['action_type'] in {'docker.stop_container','docker.delete_container','docker.prune','docker.exec','file.delete','firewall.change','dns.change','volume.delete'}:
        raise SystemExit(f'Destructive action type present: {a["action_type"]}')
if 'docker_read_at' not in containers_response:
    raise SystemExit('Missing docker_read_at in /api/containers')
if 'docker_read_at' not in mission.get('docker', {}):
    raise SystemExit('Missing docker_read_at in /api/mission docker object')
if len(containers) != mission['docker']['total'] or len(containers) != len(mission_containers):
    raise SystemExit('Docker totals disagree')
for c in containers:
    name = c.get('name')
    expected_asset = f'docker:{name}'
    if c.get('asset_id') != expected_asset:
        raise SystemExit(f'Missing or wrong asset_id for {name}')
    if expected_asset not in asset_ids:
        raise SystemExit(f'Asset Registry missing {expected_asset}')
    if name not in mission_by_name:
        raise SystemExit(f'{name} missing from /api/mission containers list')
    m = mission_by_name[name]
    for item, label in [(c, '/api/containers'), (m, '/api/mission')]:
        if item.get('status') != item.get('docker_state'):
            raise SystemExit(f'{label} status/docker_state mismatch for {name}')
        for field in ['docker_state','docker_status','status','health_status','read_at','asset_id']:
            if field not in item:
                raise SystemExit(f'Missing {field} on {name} in {label}')
    if c.get('docker_state') != m.get('docker_state') or c.get('status') != m.get('status'):
        raise SystemExit(f'Docker state mismatch for {name}')
class_total = sum(len(mission.get(k, [])) for k in ['critical_services','optional_services','stopped_by_design','unknown_containers'])
if class_total != len(containers):
    raise SystemExit('Classified sections do not include all containers')
if sum(1 for c in containers if c.get('docker_state') == 'running') != mission['docker']['running']:
    raise SystemExit('Docker running count disagrees')
if sum(1 for c in containers if c.get('docker_state') == 'exited') != mission['docker']['stopped']:
    raise SystemExit('Docker stopped count disagrees')
print('Live Docker + Asset Registry + Event Engine + Policy Engine + Action Engine regression OK')
PY

echo "Validation OK."
