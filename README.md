# Jarvis-os v0.3

Jarvis-os is a local server assistant for Docker monitoring, system health, safe self-healing and learning normal server behavior over time.

Current status: v0.3 is stabilized and prepared for a future v0.4 plugin architecture. No new major automation features are enabled.

## v0.3 status

- Background worker runs every 60 seconds
- Mission Control UI runs on port `8088`
- Jarvis Brain learns conservative baselines
- Anomaly detection is observation-only
- Recommendations are non-destructive
- Auto-start remains disabled by default
- Validation tests the Dockerized app, not host Python dependencies
- Unknown Docker containers are discovered dynamically and stay visible until classified

## Dynamic container discovery

Jarvis reads the current live Docker state directly from Docker Engine. Mission Control does not use baselines, event history or previous observations as the source of truth for current Docker status.

Each container includes:

- `docker_state` from Docker Engine state
- `docker_status` from the Docker SDK
- `health_status` when Docker health checks are available
- `classification`
- `protected`
- `auto_start_allowed`

Unknown containers are never auto-started.

Examples such as `jellyseerr`, `qbittorrent`, `gluetun`, `bazarr` and other new services remain `unknown` unless they are configured in `.env` or saved through Mission Control classification.

## Unknown container classification workflow

Mission Control has an **Unknown containers** section near Docker status.

For each unknown container, Jarvis shows:

- Name
- Docker state
- Image
- Recommended classification
- Classification controls
- Protected yes/no
- Auto-start yes/no

Available classifications:

- `critical`
- `optional`
- `stopped_by_design`
- `unknown`

The UI saves classification through:

```text
POST /api/service-classifications/{service}
```

Request body:

```json
{
  "classification": "optional",
  "protected": false,
  "auto_start_allowed": false
}
```

After saving, Mission Control refreshes and the container moves into the correct section.

Recommended safe defaults:

- Use `critical` for services the server depends on, such as reverse proxy, DNS and Home Assistant.
- Use `optional` for media/tools that may safely be down for a while.
- Use `stopped_by_design` for services that are intentionally off, test containers, VPN-dependent services or one-shot containers.
- Keep `auto_start_allowed=false` until you have verified the service is safe to restart automatically.

## Jarvis Brain memory

Jarvis stores memory in SQLite under the existing Docker volume. Memory survives container restart because `jarvis_data` is mounted at `/data` and the database path defaults to `/data/jarvis.db`.

Memory tables:

- `service_baselines`
- `system_baselines`
- `observations`
- `recommendations`
- `service_classifications`

## Memory retention

Jarvis safely cleans up only old rows from its own SQLite database tables. It never deletes files, Docker data, Docker volumes or external data.

Default retention:

- Observations: 30 days
- Worker checks: 30 days
- Action log: 90 days
- Resolved incidents: 90 days

Settings:

```env
OBSERVATIONS_RETENTION_DAYS=30
WORKER_CHECKS_RETENTION_DAYS=30
ACTION_LOG_RETENTION_DAYS=90
RESOLVED_INCIDENTS_RETENTION_DAYS=90
```

## Baseline learning

During each worker check, Jarvis stores and updates:

- CPU percentage
- RAM percentage
- Swap percentage and normal swap range
- Root disk percentage
- Container status
- Service classification
- Normal running/stopped state per service

Baseline updates are conservative. One spike is limited by `BASELINE_MAX_STEP_PERCENT` and should not move the baseline too much.

Anomaly detection does not become active until the minimum sample count is reached.

Default:

```env
BASELINE_MIN_SAMPLES=20
BASELINE_MAX_STEP_PERCENT=2
```

## Anomaly detection limits

Jarvis v0.3 detects and records observations for:

- Critical service stopped
- Optional service repeatedly failing
- RAM much higher than baseline
- Swap much higher than baseline
- Disk usage trending upward
- Unknown container appears
- Service status differs from learned normal behavior

Jarvis does not auto-fix anomalies in v0.3. It only logs observations and creates recommendations.

## Recommendations

Recommendations have lifecycle status:

- `active`
- `dismissed`
- `resolved`

Active duplicate recommendations for the same service and title are avoided. Dismissing a recommendation only marks it as dismissed. It does not delete anything.

Examples Jarvis may create:

- `Swap is higher than normal`
- `Disk usage is trending upward`
- `This service is usually stopped`
- `This container is unknown; classify it?`

## Safety model

Jarvis-os v0.3 is safety-first.

Auto-start is disabled by default. A container must be explicitly added to `ALLOWED_AUTO_START_CONTAINERS` or saved with `auto_start_allowed=true` before Jarvis may auto-start it.

It may auto-start stopped optional containers only when all of these are true:

- `SAFE_MODE=true`
- Container is classified as `optional`
- Container is not protected
- Container is explicitly allowed for auto-start
- Container has fewer than 3 failed auto-start attempts inside 30 minutes

Jarvis must never auto-start:

- Unknown containers
- `gluetun`
- `qbittorrent` unless `gluetun` is running
- Protected containers
- Stopped-by-design containers

Jarvis does not contain destructive actions. It does not delete files, delete containers, delete Docker volumes, prune Docker, change firewall rules, change DNS settings, change Docker volumes or run arbitrary shell commands.

Allowed and failed automated actions are logged. Repeated denied or skipped auto-start decisions are rate-limited to at most once per hour per container and reason.

## Plugin architecture direction

v0.3 prepares a read-only plugin structure for v0.4:

- `app/plugins/base.py`
- `app/plugins/docker_plugin.py`
- `app/plugins/system_plugin.py`

The current plugins are structure only. Existing behavior still uses the current Docker and system modules.

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

Protected containers are never auto-started. If a protected container is not otherwise configured, it can still appear as `unknown` but protected.

### Optional services

```env
OPTIONAL_SERVICES=sonarr,radarr,readarr,prowlarr,jellyfin,filebrowser,glances
```

Optional services may be auto-started only if they are explicitly allowed for auto-start.

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
git checkout feature/event-engine
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
git checkout feature/event-engine
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
BASELINE_MIN_SAMPLES=20
BASELINE_MAX_STEP_PERCENT=2
ANOMALY_RAM_DELTA_PERCENT=20
ANOMALY_SWAP_DELTA_PERCENT=20
DISK_TREND_DELTA_PERCENT=2
OBSERVATIONS_RETENTION_DAYS=30
WORKER_CHECKS_RETENTION_DAYS=30
ACTION_LOG_RETENTION_DAYS=90
RESOLVED_INCIDENTS_RETENTION_DAYS=90
DB_PATH=/data/jarvis.db
```

Recommended first run:

```env
SAFE_MODE=true
WORKER_ENABLED=true
ALLOWED_AUTO_START_CONTAINERS=
```

When the system has proven stable, explicitly add selected optional services to auto-start.

## API

- `GET /api/mission`
- `GET /api/brain`
- `GET /api/observations`
- `GET /api/recommendations`
- `POST /api/recommendations/{id}/dismiss`
- `GET /api/service-classifications`
- `POST /api/service-classifications/{service}`
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

The script validates the Dockerized app, starts the stack with Docker Compose, waits for readiness and checks the API endpoints plus a live Docker consistency regression between `/api/containers` and `/api/mission`.

It does not require Python dependencies on the Ubuntu host.

## Architecture docs

See:

```text
docs/ARCHITECTURE.md
docs/EVENT_ENGINE.md
```

## Status

This is stabilized v0.3 foundation code for a learning local assistant and event-driven platform. It is intentionally conservative and does not include broad autonomous control.
