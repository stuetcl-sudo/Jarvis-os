# Jarvis-os v0.3 + Policy Engine

Jarvis-os is a local server assistant for Docker monitoring, system health, Event Engine, Asset Registry, Policy Engine, safe self-healing and learning normal server behavior over time.

Current branch: `feature/policy-engine`.

## Current status

- Background worker runs every 60 seconds
- Mission Control UI runs on port `8088`
- Event Engine remains enabled
- Asset Registry persists observed assets in SQLite
- Policy Engine evaluates events and stores explainable decisions
- Docker containers are represented as assets like `docker:jellyfin`
- System resources are represented as assets like `system:cpu`, `system:memory`, `system:swap`, `system:disk`
- Recommendations and incidents are non-destructive
- Auto-start remains disabled by default
- Unknown Docker containers are discovered dynamically and stay visible until classified

## Policy Engine

Policies decide what Jarvis may do. Jarvis should not make decisions through scattered hardcoded logic.

Each decision records:

- What matched
- Why it matched
- What action was allowed
- What action was denied
- What rule caused the decision
- Whether the decision was dry-run only

The current Policy Engine can create incidents, recommendations, ignored decisions and denied decisions. It does not automatically restart containers.

Default policies:

- Unknown container discovered → recommend classification
- Critical Docker container stopped → create critical incident and recommendation
- Optional Docker container stopped → recommend manual restart
- Stopped-by-design container stopped → ignore with explanation
- qBittorrent dependency guard → deny future unsafe auto-start unless `docker:gluetun` is running

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

Assets and relationships are persisted in SQLite and survive container restart through `/data/jarvis.db`.

Relationships supported:

- `depends_on`
- `contains`
- `connected_to`
- `managed_by`
- `hosted_on`

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

## Safety model

Jarvis-os is safety-first.

Auto-start is disabled by default. A container must be explicitly added to `ALLOWED_AUTO_START_CONTAINERS` or saved with `auto_start_allowed=true` before Jarvis may auto-start it.

Jarvis must never auto-start:

- Unknown containers
- `gluetun`
- `qbittorrent` unless `gluetun` is running
- Protected containers
- Stopped-by-design containers

Jarvis does not delete files, delete containers, delete Docker volumes, prune Docker, change firewall rules, change DNS settings, change Docker volumes or run arbitrary shell commands.

AI may explain and suggest, but AI cannot execute actions directly and cannot bypass policies.

## Recommended install on Dennis' server

Use `/docker/jarvis` so it matches the rest of the server layout.

```bash
cd /docker
git clone https://github.com/stuetcl-sudo/Jarvis-os.git jarvis
cd jarvis
git checkout feature/policy-engine
cp .env.example .env
docker compose up -d --build
```

Open Mission Control:

```text
http://SERVER-IP:8088
```

## Update commands

```bash
cd /docker/jarvis
git checkout feature/policy-engine
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

Policy Engine:

- `GET /api/policies`
- `GET /api/policies/{policy_id}`
- `POST /api/policies/{policy_id}/enable`
- `POST /api/policies/{policy_id}/disable`
- `GET /api/policy-decisions`
- `GET /api/policy-decisions/latest`

Asset Registry:

- `GET /api/assets`
- `GET /api/assets/{id}`
- `GET /api/assets/search?q=...`
- `GET /api/assets/relationships`

Event Engine:

- `GET /api/events`
- `GET /api/events/latest`
- `GET /api/events/types`
- `GET /api/events/statistics`

Brain and recommendations:

- `GET /api/brain`
- `GET /api/observations`
- `GET /api/recommendations`
- `POST /api/recommendations/{id}/dismiss`

Classification:

- `GET /api/service-classifications`
- `POST /api/service-classifications/{service}`

## Validation

Run:

```bash
bash scripts/validate.sh
```

The script validates the Dockerized app, starts the stack with Docker Compose, waits for readiness and checks endpoint health plus Docker, Event Engine, Asset Registry and Policy Engine regressions.

It does not require Python dependencies on the Ubuntu host.

## Architecture docs

See:

```text
docs/ARCHITECTURE.md
docs/EVENT_ENGINE.md
docs/ASSET_REGISTRY.md
docs/POLICY_ENGINE.md
```

## Future compatibility

The Policy Engine is designed so future integrations can publish events and register assets without changing the core:

- Home Assistant
- UniFi
- AdGuard
- UPS
- Tailscale
- Calendar
- Notifications
- LLM reasoning
