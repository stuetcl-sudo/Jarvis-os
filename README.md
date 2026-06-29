# Jarvis-os v0.3

Jarvis-os is a local server assistant for Docker monitoring, system health, safe self-healing and learning normal server behavior over time.

v0.3 adds Jarvis Brain: persistent memory, simple baselines, anomaly observations and non-destructive recommendations.

## v0.3 features

- Background worker every 60 seconds
- Mission Control UI on port `8088`
- Jarvis Brain UI section
- Docker container monitoring
- Host health checks: CPU, RAM, swap and root disk
- Service classification: critical, optional, unknown and stopped-by-design
- SQLite action log
- SQLite incidents table
- SQLite memory tables
- Baseline learning for normal system behavior
- Observations and recommendations
- Safe optional container auto-start remains disabled by default

## Jarvis Brain memory

Jarvis stores memory in SQLite under the existing Docker volume. Memory survives container restart because `jarvis_data` is mounted at `/data` and the database path defaults to `/data/jarvis.db`.

Memory tables:

- `service_baselines`
- `system_baselines`
- `observations`
- `recommendations`

## Baselines

During each worker check, Jarvis stores and updates:

- CPU percentage
- RAM percentage
- Swap percentage and normal swap range
- Root disk percentage
- Container status
- Service classification
- Normal running/stopped state per service

The baseline is simple and transparent. It uses running averages and status counts, not a black-box model.

## Anomaly detection

Jarvis v0.3 detects and records observations for:

- Critical service stopped
- Optional service repeatedly failing
- RAM much higher than baseline
- Swap much higher than baseline
- Disk usage trending upward
- Unknown container appears
- Service status differs from learned normal behavior

Jarvis does not auto-fix anomalies in v0.3. It only logs observations and creates recommendations.

## Recommendation examples

Examples Jarvis may create:

- `Swap is higher than normal`
- `Disk usage is trending upward`
- `This service is usually stopped`
- `This container is unknown; classify it?`

Recommendations can be dismissed from the UI or API. Dismissing only changes recommendation status; it does not change Docker, files, firewall, DNS or volumes.

## Safety model

Jarvis-os v0.3 is safety-first.

Auto-start is disabled by default. A container must be explicitly added to `ALLOWED_AUTO_START_CONTAINERS` before Jarvis may auto-start it.

It may auto-start stopped optional containers only when all of these are true:

- `SAFE_MODE=true`
- Container is not protected
- Container is listed in `ALLOWED_AUTO_START_CONTAINERS`
- Container has fewer than 3 failed auto-start attempts inside 30 minutes

Jarvis must never auto-start:

- `gluetun`
- `qbittorrent` unless `gluetun` is running
- Protected containers

Jarvis does not contain destructive actions. It does not delete files, delete containers, delete Docker volumes, prune Docker, change firewall rules, change DNS settings, change Docker volumes or run arbitrary shell commands.

Allowed and failed automated actions are logged. Repeated denied or skipped auto-start decisions are rate-limited to at most once per hour per container and reason.

## Default service classes

### Critical services

```env
CRITICAL_SERVICES=jarvis-os,adguardhome,caddy,homeassistant
```

Critical services create active incidents and observations when they are not running. Jarvis does not auto-start protected services.

### Protected containers

```env
PROTECTED_CONTAINERS=jarvis-os,adguardhome,caddy,gluetun
```

Protected containers are never auto-started.

### Optional services

```env
OPTIONAL_SERVICES=sonarr,radarr,readarr,prowlarr,jellyfin,filebrowser,glances
```

Optional services may be auto-started only if they are also listed in `ALLOWED_AUTO_START_CONTAINERS`.

Default:

```env
ALLOWED_AUTO_START_CONTAINERS=
```

### Stopped-by-design services

```env
IGNORED_SERVICES=
```

Use this for containers that are normally stopped. Jarvis shows them separately and skips self-healing.

## Recommended install on Dennis' server

Use `/docker/jarvis` so it matches the rest of the server layout.

```bash
cd /docker
git clone https://github.com/stuetcl-sudo/Jarvis-os.git jarvis
cd jarvis
git checkout jarvis-v0.1
cp .env.example .env
docker compose up -d --build
```

Open Mission Control:

```text
http://SERVER-IP:8088
```

On the local LAN this may be:

```text
http://192.168.68.135:8088
```

## Update commands

```bash
cd /docker/jarvis
git checkout jarvis-v0.1
git pull
docker compose up -d --build
```

## Configuration

Important `.env` values:

```env
SAFE_MODE=true
ALLOW_RESTART_STOPPED=true
WORKER_ENABLED=true
WORKER_INTERVAL_SECONDS=60
CRITICAL_SERVICES=jarvis-os,adguardhome,caddy,homeassistant
PROTECTED_CONTAINERS=jarvis-os,adguardhome,caddy,gluetun
OPTIONAL_SERVICES=sonarr,radarr,readarr,prowlarr,jellyfin,filebrowser,glances
IGNORED_SERVICES=
ALLOWED_AUTO_START_CONTAINERS=
AUTO_START_FAILURE_LIMIT=3
AUTO_START_FAILURE_WINDOW_MINUTES=30
BASELINE_MIN_SAMPLES=3
ANOMALY_RAM_DELTA_PERCENT=20
ANOMALY_SWAP_DELTA_PERCENT=20
DISK_TREND_DELTA_PERCENT=2
DB_PATH=/data/jarvis.db
```

Recommended first run:

```env
SAFE_MODE=true
WORKER_ENABLED=true
ALLOWED_AUTO_START_CONTAINERS=
```

When the system has proven stable, explicitly add selected optional services to `ALLOWED_AUTO_START_CONTAINERS`.

Example:

```env
ALLOWED_AUTO_START_CONTAINERS=filebrowser,glances
```

## API

- `GET /api/mission`
- `GET /api/brain`
- `GET /api/observations`
- `GET /api/recommendations`
- `POST /api/recommendations/{id}/dismiss`
- `GET /api/incidents`
- `GET /api/worker/status`
- `POST /api/worker/run-once`
- `GET /api/health`
- `GET /api/containers`
- `POST /api/containers/{name}/restart`
- `GET /api/actions`

## Validation

Run:

```bash
bash scripts/validate.sh
```

The script validates the Dockerized app, starts the stack with Docker Compose, waits for readiness and checks all required API endpoints including Jarvis Brain.

## Status

This is v0.3 foundation code for a learning local assistant. It is intentionally conservative and does not include broad autonomous control.
