# Jarvis-os Architecture

Jarvis-os is a local, safety-first server assistant. The current v0.3 line focuses on observation, memory, recommendations and conservative Docker monitoring.

## Core

The core is a FastAPI application. It exposes the Mission Control UI and JSON API endpoints.

Core responsibilities:

- Start the background worker
- Serve the dashboard on port `8088`
- Expose health, Docker, incident, worker and Brain APIs
- Enforce narrow manual actions
- Keep destructive behavior out of the codebase

## Worker

The worker runs every 60 seconds when `WORKER_ENABLED=true`.

Each cycle:

1. Reads Docker container state
2. Reads system health
3. Updates incidents
4. Updates Jarvis Brain memory
5. Evaluates safe auto-start rules
6. Performs safe database retention cleanup
7. Logs the check result

The worker loop catches exceptions and continues running. Worker status tracks last successful check, last failed check, consecutive failures and current task.

## Memory

Jarvis memory lives in SQLite at `/data/jarvis.db` by default. The Docker Compose volume keeps this data across container restarts.

Memory tables:

- `service_baselines`
- `system_baselines`
- `observations`
- `recommendations`
- `worker_checks`
- `action_log`
- `incidents`

Jarvis only deletes old rows from its own database tables according to retention settings. It does not delete files or Docker data.

## Safety model

Jarvis-os is designed to observe first and act only inside narrow safe rules.

Allowed behavior:

- Read system health
- Read Docker container state
- Log actions
- Create observations and recommendations
- Mark recommendations dismissed
- Start stopped optional containers only when explicitly allowed in `.env`

Auto-start is disabled by default because `ALLOWED_AUTO_START_CONTAINERS=` is empty.

## Plugin direction

v0.3 includes a minimal plugin skeleton for v0.4:

- `app/plugins/base.py`
- `app/plugins/docker_plugin.py`
- `app/plugins/system_plugin.py`

The current plugin direction is read-only collection first. Future plugins should declare capabilities and safety boundaries before any action is allowed.

## What Jarvis is not allowed to do

Jarvis must not:

- Run arbitrary shell commands
- Delete files
- Delete Docker volumes
- Run Docker prune
- Change firewall rules
- Change DNS settings
- Change Docker volumes
- Perform destructive automatic actions

These limits are part of the architecture, not just configuration defaults.
