#!/usr/bin/env bash
set -Eeuo pipefail

readonly PROJECT="jarvis-managed-ha-e2e"
readonly EXPECTED_BRANCH="fix/v0.20.0-alpha.2-managed-ha-labels"
readonly ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly COMPOSE_FILE="$ROOT_DIR/compose.e2e-managed-home-assistant.yml"
readonly APP_URL="http://127.0.0.1:18088"
readonly COOKIE_FILE="$(mktemp)"
readonly HEADER_FILE="$(mktemp)"
readonly RESPONSE_FILE="$(mktemp)"
readonly BEFORE_FILE="$(mktemp)"
readonly AFTER_FILE="$(mktemp)"
readonly COMPOSE=(docker compose -p "$PROJECT" -f "$COMPOSE_FILE")
CLEANUP_DONE=0

fail() { printf 'E2E FAIL: %s\n' "$*" >&2; exit 1; }
note() { printf 'E2E: %s\n' "$*"; }

host_snapshot() {
  local ids
  ids="$(docker ps -q --filter "label=com.docker.compose.project!=$PROJECT")"
  if [[ -n "$ids" ]]; then
    docker inspect --format '{{.Id}}|{{.Name}}|{{.State.Status}}|{{.State.StartedAt}}' $ids | sort
  fi
}

cleanup() {
  local status=$?
  trap - EXIT INT TERM
  set +e
  "${COMPOSE[@]}" --profile installer down -v --remove-orphans >/dev/null 2>&1
  if docker ps -a --format '{{.Label "com.docker.compose.project"}}' | grep -Fxq "$PROJECT"; then
    printf 'E2E cleanup failed: project containers remain\n' >&2
    status=1
  fi
  if docker network ls --format '{{.Name}}' | grep -Eq "^${PROJECT}(_|-)|^${PROJECT}$"; then
    printf 'E2E cleanup failed: project networks remain\n' >&2
    status=1
  fi
  if docker volume ls --format '{{.Name}}' | grep -Eq "^${PROJECT}(_|-)|^${PROJECT}$"; then
    printf 'E2E cleanup failed: project volumes remain\n' >&2
    status=1
  fi
  host_snapshot >"$AFTER_FILE" 2>/dev/null || status=1
  if [[ -s "$BEFORE_FILE" ]] && ! cmp -s "$BEFORE_FILE" "$AFTER_FILE"; then
    printf 'E2E cleanup failed: non-E2E container identity/state snapshot changed\n' >&2
    status=1
  fi
  rm -f -- "$COOKIE_FILE" "$HEADER_FILE" "$RESPONSE_FILE" "$BEFORE_FILE" "$AFTER_FILE"
  CLEANUP_DONE=1
  exit "$status"
}
trap cleanup EXIT INT TERM

compose_config() { "${COMPOSE[@]}" --profile installer config; }
dind_docker() { "${COMPOSE[@]}" exec -T dind docker "$@"; }

assert_json() {
  local expression=$1
  python3 - "$RESPONSE_FILE" "$expression" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
if not eval(sys.argv[2], {"__builtins__": {}}, {"p": payload}):
    raise SystemExit("JSON assertion failed")
PY
}

api_post() {
  local path=$1 body=$2
  curl --fail-with-body --silent --show-error --max-time 15 \
    --cookie "$COOKIE_FILE" --cookie-jar "$COOKIE_FILE" \
    -H @"$HEADER_FILE" -H 'Content-Type: application/json' \
    --data "$body" "$APP_URL$path" >"$RESPONSE_FILE"
}

bootstrap_owner() {
  local owner_value
  owner_value="$(python3 -c 'import secrets,string; alphabet=string.ascii_letters+string.digits+"!@#%^_+="; print("".join(secrets.choice(alphabet) for _ in range(32)))')"
  chmod 600 "$COOKIE_FILE" "$HEADER_FILE" "$RESPONSE_FILE"
  curl --fail-with-body --silent --show-error --max-time 15 \
    --cookie-jar "$COOKIE_FILE" -H 'Content-Type: application/json' \
    --data "$(python3 -c 'import json,sys; print(json.dumps({"display_name":"E2E Owner","username":"e2e-owner","password":sys.argv[1]}))' "$owner_value")" \
    "$APP_URL/api/bootstrap/owner" >"$RESPONSE_FILE"
  unset owner_value
  assert_json 'p["status"] == "created" and p["next"] == "/setup"'
  curl --fail --silent --show-error --max-time 10 --cookie "$COOKIE_FILE" \
    "$APP_URL/api/auth/me" >"$RESPONSE_FILE"
  python3 - "$RESPONSE_FILE" "$HEADER_FILE" <<'PY'
import json, os, sys
token = json.load(open(sys.argv[1], encoding="utf-8"))["csrf_token"]
fd = os.open(sys.argv[2], os.O_WRONLY | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as stream:
    stream.write("X-CSRF-Token: " + token + "\n")
PY
  note "bootstrap and owner session/CSRF succeeded (secret values suppressed)"
}

request_install() {
  api_post /api/admin/setup/home-assistant/managed/plan '{}'
  assert_json 'p["state"] == "ready_to_install" and p["container_name"] == "jarvis-managed-home-assistant"'
  api_post /api/admin/setup/home-assistant/managed/install-request '{}'
  assert_json 'p["installation_requested"] is True'
  note "fixed plan and explicit installation confirmation succeeded"
}

run_installer() {
  timeout --foreground 900 "${COMPOSE[@]}" --profile installer run --rm --no-deps installer-e2e
  note "one-shot installer completed against TLS DinD"
}

verify_nested_resources() {
  local inspect_file volume_file network_file
  inspect_file="$(mktemp)"; volume_file="$(mktemp)"; network_file="$(mktemp)"
  dind_docker inspect jarvis-managed-home-assistant >"$inspect_file"
  dind_docker volume inspect jarvis-managed-home-assistant-config >"$volume_file"
  dind_docker network inspect jarvis-managed-home-assistant-network >"$network_file"
  python3 - "$inspect_file" "$volume_file" "$network_file" <<'PY'
import json, sys
c, v, n = (json.load(open(path, encoding="utf-8"))[0] for path in sys.argv[1:])
labels = {"dk.jarvis.managed":"home-assistant", "dk.jarvis.component":"managed-home-assistant-installer"}
assert c["Name"] == "/jarvis-managed-home-assistant"
assert c["Config"]["Image"] == "homeassistant/home-assistant:stable"
assert all(c["Config"]["Labels"].get(key) == value for key, value in labels.items())
assert c["HostConfig"]["RestartPolicy"]["Name"] == "unless-stopped"
assert c["State"]["Running"] is True
assert set(c["NetworkSettings"]["Networks"]) == {"jarvis-managed-home-assistant-network"}
assert c["HostConfig"]["PortBindings"] == {"8123/tcp":[{"HostIp":"", "HostPort":"8123"}]}
mounts = c["Mounts"]
assert len(mounts) == 1 and mounts[0]["Type"] == "volume"
assert mounts[0]["Name"] == "jarvis-managed-home-assistant-config" and mounts[0]["Destination"] == "/config" and mounts[0]["RW"]
assert v["Name"] == "jarvis-managed-home-assistant-config" and v["Driver"] == "local" and v["Labels"] == labels
assert n["Name"] == "jarvis-managed-home-assistant-network" and n["Driver"] == "bridge" and n["Labels"] == labels
PY
  rm -f -- "$inspect_file" "$volume_file" "$network_file"
  [[ "$(dind_docker ps -a --format '{{.Names}}' | wc -l)" -eq 1 ]] || fail "unexpected nested container"
  [[ "$(dind_docker volume ls --filter name='^jarvis-managed-home-assistant-config$' -q | wc -l)" -eq 1 ]] || fail "managed volume count mismatch"
  [[ "$(dind_docker network ls --filter name='^jarvis-managed-home-assistant-network$' -q | wc -l)" -eq 1 ]] || fail "managed network count mismatch"
  note "exact nested container/image/volume/network/port/mount/labels/restart/running state verified"
}

cd "$ROOT_DIR"
[[ "$(git branch --show-current)" == "$EXPECTED_BRANCH" ]] || fail "must run on $EXPECTED_BRANCH"
[[ "$(docker compose -p "$PROJECT" -f "$COMPOSE_FILE" config --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["name"])')" == "$PROJECT" ]] || fail "Compose project name mismatch"
rendered="$(compose_config)"
[[ "$rendered" != *'/var/run/docker.sock'* ]] || fail "host Docker socket mount found"
python3 -c 'import sys,yaml; c=yaml.safe_load(sys.stdin); p=c["services"]["jarvis-e2e"]["ports"]; assert p == [{"mode":"ingress","host_ip":"127.0.0.1","target":8088,"published":"18088","protocol":"tcp"}]' <<<"$rendered" \
  || fail "Jarvis test port is not loopback-only"
for forbidden in 'jarvis-os_jarvis_data' 'jarvis_staging_data' 'jarvis_staging_network' 'jarvis-managed-home-assistant-network: external'; do
  [[ "$rendered" != *"$forbidden"* ]] || fail "production/staging resource found: $forbidden"
done
host_snapshot >"$BEFORE_FILE"
note "preflight security assertions passed; non-E2E containers snapshotted"

"${COMPOSE[@]}" up -d --build dind jarvis-e2e
for _ in $(seq 1 60); do
  [[ "$("${COMPOSE[@]}" ps --format json dind | python3 -c 'import json,sys; d=json.load(sys.stdin); d=d[0] if isinstance(d,list) and d else d; print(d.get("Health", "") if isinstance(d,dict) else "")')" == "healthy" ]] && break
  sleep 2
done
dind_docker info >/dev/null || fail "DinD did not become ready"
for _ in $(seq 1 60); do curl --fail --silent --max-time 2 "$APP_URL/api/bootstrap/status" >/dev/null && break; sleep 1; done
curl --fail --silent --max-time 3 "$APP_URL/api/bootstrap/status" >/dev/null || fail "E2E Jarvis did not become ready"

bootstrap_owner
request_install
run_installer
verify_nested_resources

"${COMPOSE[@]}" stop jarvis-e2e >/dev/null
"${COMPOSE[@]}" run --rm --no-deps --user root jarvis-e2e sh -c 'rm -f /e2e-data/jarvis-e2e.db'
rm -f -- "$COOKIE_FILE" "$HEADER_FILE" "$RESPONSE_FILE"
touch "$COOKIE_FILE" "$HEADER_FILE" "$RESPONSE_FILE"; chmod 600 "$COOKIE_FILE" "$HEADER_FILE" "$RESPONSE_FILE"
"${COMPOSE[@]}" up -d jarvis-e2e
for _ in $(seq 1 30); do curl --fail --silent --max-time 2 "$APP_URL/api/bootstrap/status" >"$RESPONSE_FILE" && assert_json 'p["bootstrap_required"] is True' && break; sleep 1; done
bootstrap_owner
request_install
run_installer
verify_nested_resources
note "idempotency verified through a fresh supported owner plan/request; no duplicate fixed resources"

# Use the retained owner session for the read-only onboarding endpoint.
for _ in $(seq 1 180); do
  curl --fail --silent --show-error --max-time 5 --cookie "$COOKIE_FILE" \
    "$APP_URL/api/admin/setup/home-assistant/managed/onboarding" >"$RESPONSE_FILE" || true
  if python3 - "$RESPONSE_FILE" <<'PY'
import json, sys
try: p=json.load(open(sys.argv[1], encoding="utf-8"))
except Exception: raise SystemExit(1)
raise SystemExit(0 if p.get("state") == "onboarding_required" and p.get("home_assistant_url") == "http://127.0.0.1:18123" else 1)
PY
  then break; fi
  sleep 2
done
assert_json 'p["state"] == "onboarding_required" and p["home_assistant_url"] == "http://127.0.0.1:18123"'
note "backend probe progressed to onboarding_required with safe loopback browser URL"

"${COMPOSE[@]}" exec -T jarvis-e2e sh -c 'test ! -S /var/run/docker.sock' || fail "raw socket present in Jarvis"
for container_id in $("${COMPOSE[@]}" ps -q); do
  docker inspect --format '{{range .Mounts}}{{println .Source "->" .Destination}}{{end}}' "$container_id" \
    | grep -Fq '/var/run/docker.sock' && fail "host socket mounted in an E2E container"
done
[[ "$("${COMPOSE[@]}" exec -T jarvis-e2e sh -c 'printf %s "${DOCKER_HOST-}"')" == "" ]] || fail "Jarvis has DOCKER_HOST"
host_snapshot >"$AFTER_FILE"; cmp -s "$BEFORE_FILE" "$AFTER_FILE" || fail "non-E2E containers changed during run"
note "socket, credential, binding, isolation, and unchanged-host security checks passed"
note "PASS; trap cleanup will remove the complete disposable project"
