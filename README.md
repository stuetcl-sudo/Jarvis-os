# Jarvis-os v0.3 + Asset Registry

Jarvis-os is a local server assistant for Docker monitoring, system health, Event Engine, Asset Registry, safe self-healing and learning normal server behavior over time.

Current branch: `feature/asset-registry`.

## Current status

- Background worker runs every 60 seconds
- Mission Control UI runs on port `8088`
- Event Engine remains enabled
- Asset Registry persists observed assets in SQLite
- Docker containers are represented as assets like `docker:jellyfin`
- System resources are represented as assets like `system:cpu`, `system:memory`, `system:swap`, `system:disk`
- Jarvis Brain learns conservative baselines
- Anomaly detection is observation-only
- Recommendations are non-destructive
- Auto-start remains disabled by default
- Unknown Docker containers are discovered dynamically and stay visible until classified

## Asset Registry

An Asset is anything Jarvis can observe, reason about, show in Mission Control or eventually manage through explicit safe policies.

Examples:

- `docker:jellyfin`
- `docker:adguardhome`
- `system:cpu`
- `system:memory`
- `system:disk`
- `ha:light.kitchen`
- `unifi:ap-livingroom`

Each asset contains:

- `asset_id`
- `asset_type`
- `plugin`
- `name`
- `display_name`
- `state`
- `health`
- `classification`
- `protected`
- `auto_actions_allowed`
- `metadata`
- `created_at`
- `updated_at`

Assets are persisted in SQLite and survive container restart through the existing `/data/jarvis.db` volume.

## Relationship Engine

Jarvis supports relationships between assets:

- `depends_on`
- `contains`
- `connected_to`
- `managed_by`
- `hosted_on`

Examples:

```text
system:docker contains docker:jellyfin
docker:qbittorrent depends_on docker:gluetun
docker:jellyfin depends_on system:docker
```

Relationships are also persisted in SQLite and are designed for future plugins.

## Dynamic container discovery

Jarvis reads the current live Docker state directly from Docker Engine. Mission Control does not use baselines, event history or previous observations as the source of truth for current Docker status.

Each container includes:

- `asset_id`
- `docker_state`
- `docker_status`
- `health_status`
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

After saving, Mission Control refreshes and the container moves into the correct section. Keep `auto_start_allowed=false` until you have verified the service is safe to restart automatically.

## Safety model

Jarvis-os is safety-first.

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

Jarvis does not delete files, delete containers, delete Docker volumes, prune Docker, change firewall rules, change DNS settings, change Docker volumes or run arbitrary shell commands.

## Jarvis Brain memory

Jarvis stores memory in SQLite under the existing Docker volume.

Memory tables include:

- `service_baselines`
- `system_baselines`
- `observations`
- `recommendations`
- `service_classifications`
- `assets`
- `asset_relationships`

## Memory retention

Jarvis safely cleans up only old rows from its own SQLite database tables. It never deletes files, Docker data, Docker volumes or external data.

Default retention:

```env
OBSERVATIONS_RETENTION_DAYS=30
WORKER_CHECKS_RETENTION_DAYS=30
ACTION_LOG_RETENTION_DAYS=90
RESOLVED_INCIDENTS_RETENTION_DAYS=90
```

## Recommended install on Dennis' server

Use `/docker/jarvis` so it matches the rest of the server layout.

```bash
cd /docker
git clone https://github.com/stuetcl-sudo/Jarvis-os.git jarvis
cd jarvis
git checkout feature/asset-registry
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
git checkout feature/asset-registry
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

## API

Existing APIs remain available.

Core:

- `GET /api/mission`
- `GET /api/health`
- `GET /api/containers`
- `POST /api/containers/{name}/restart`
- `GET /api/worker/status`
- `POST /api/worker/run-once`

Brain and recommendations:

- `GET /api/brain`
- `GET /api/observations`
- `GET /api/recommendations`
- `POST /api/recommendations/{id}/dismiss`

Classification:

- `GET /api/service-classifications`
- `POST /api/service-classifications/{service}`

Event Engine:

- `GET /api/events`
- `GET /api/events/latest`
- `GET /api/events/types`
- `GET /api/events/statistics`

Asset Registry:

- `GET /api/assets`
- `GET /api/assets/{id}`
- `GET /api/assets/search?q=...`
- `GET /api/assets/relationships`

## Validation

Run:

```bash
bash scripts/validate.sh
```

The script validates the Dockerized app, starts the stack with Docker Compose, waits for readiness and checks endpoints plus live Docker and Asset Registry consistency.

It does not require Python dependencies on the Ubuntu host.

## Architecture docs

See:

```text
docs/ARCHITECTURE.md
docs/EVENT_ENGINE.md
docs/ASSET_REGISTRY.md
```

## Future compatibility

The Asset Registry is designed so future integrations can register assets without changing the core:

- Home Assistant
- UniFi
- AdGuard
- UPS
- Tailscale
- Calendar
- Notifications
- LLM reasoning
