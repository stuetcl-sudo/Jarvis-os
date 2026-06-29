# Jarvis-os Architecture

Jarvis-os is a local, safety-first server assistant. The current branch focuses on observation, memory, recommendations, policy decisions and a manual Action Queue.

## Core

The core is a FastAPI application. It exposes the Mission Control UI and JSON API endpoints.

Core responsibilities:

- Start the background worker
- Serve Mission Control on port `8088`
- Expose health, Docker, incident, worker, Brain, Event, Asset, Policy and Action APIs
- Keep destructive behavior out of the codebase
- Route executable work through the Action Engine

## Worker

The worker runs every 60 seconds when `WORKER_ENABLED=true`.

Each cycle:

1. Reads Docker container state
2. Reads system health
3. Publishes events
4. Updates incidents, observations and recommendations
5. Updates Jarvis Brain memory
6. Evaluates policies through the Event Engine
7. Performs safe database retention cleanup
8. Logs the check result

The worker loop catches exceptions and continues running. Worker status tracks last successful check, last failed check, consecutive failures and current task.

## Memory

Jarvis memory lives in SQLite at `/data/jarvis.db` by default. The Docker Compose volume keeps this data across container restarts.

Memory tables include:

- `service_baselines`
- `system_baselines`
- `observations`
- `recommendations`
- `worker_checks`
- `action_log`
- `incidents`
- `events`
- `assets`
- `asset_relationships`
- `policies`
- `policy_decisions`
- `actions`

Jarvis only deletes old rows from its own database tables according to retention settings. It does not delete files or Docker data.

## Event Engine

The Event Engine lets plugins, the worker, policies and actions communicate through events. Events describe facts and intent. Events do not grant permission to act.

## Asset Registry

The Asset Registry stores observable items such as Docker containers and system resources as assets. Plugins should register assets without changing the registry schema.

## Policy Engine

The Policy Engine evaluates events and creates explainable decisions. Policies may create recommendations, incidents or queued manual actions, but they do not execute actions directly.

## Action Engine

The Action Engine owns executable work. Actions are queued, optionally approved, checked for safety, executed by a narrow executor, verified, and stored with result and explanation.

Current executable action support is limited to safe `docker.start_container` for optional, exited, non-protected, known Docker assets after approval or explicit allow-listing.

## Safety model

Jarvis-os observes first and acts only inside narrow safe rules.

Allowed behavior:

- Read system health
- Read Docker container state
- Log actions
- Create observations, recommendations and incidents
- Mark recommendations dismissed
- Queue manual actions
- Start a stopped optional Docker container only through the Action Engine after safety checks

Auto-start is disabled by default because `ALLOWED_AUTO_START_CONTAINERS=` is empty.

## Plugin direction

Plugins should declare capabilities and safety boundaries before any action is allowed. Read-only collection should be the default starting point for new plugins.

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
