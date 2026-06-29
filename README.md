# Jarvis-os v0.7 + Action Engine

Jarvis-os is a local server assistant for Docker monitoring, system health, Event Engine, Asset Registry, Policy Engine, Action Engine, safe self-healing and learning normal server behavior over time.

Current branch: `feature/action-engine`.

## Current status

- Background worker runs every 60 seconds
- Mission Control UI runs on port `8088`
- Event Engine remains enabled
- Asset Registry persists observed assets in SQLite
- Policy Engine evaluates events and stores explainable decisions
- Action Engine stores queued, approved, denied, completed and failed actions
- Docker containers are represented as assets such as `docker:example-app`
- Recommendations and incidents are non-destructive
- Auto-start remains disabled by default
- Unknown Docker containers are discovered dynamically and stay visible until classified

## Action Engine

Actions are separate from policies. Policies may recommend or queue actions, but they do not execute them.

```text
Policy Decision
↓
Action Queue
↓
Safety Check
↓
Executor
↓
Verification
↓
Action History
↓
Explanation
```

Supported v0.7 action types:

- `docker.start_container`
- `recommendation.create`
- `incident.create`
- `notification.create_stub`

`docker.start_container` is the only Docker executor. It uses Docker SDK, never shell execution.

Docker start is allowed only when:

- `SAFE_MODE=true`
- Asset exists
- Asset type is `docker_container`
- Asset state is `exited`
- Asset is not protected
- Asset classification is `optional`
- Asset is not unknown
- Manual approval is present, unless `auto_actions_allowed=true`
- Dependency guards pass

No stop, delete, prune, exec, compose or shell actions exist.

## Manual approval workflow

Mission Control shows an Action Queue section.

A stopped optional Docker asset shows **Request restart**. The user must approve and run the queued action. Safety checks run immediately before execution. After execution, Jarvis verifies live Docker state and stores the result and explanation.

## Policy Engine

Policies decide what Jarvis may consider.

Default policies:

- Unknown asset discovered → recommend classification
- Critical Docker asset stopped → create critical incident and recommendation
- Optional Docker asset stopped → recommend restart and queue a waiting-approval action
- Stopped-by-design asset stopped → ignore with explanation

Service-specific dependency guards are supported through Asset Registry relationships and policy configuration examples, but they are not enabled as universal defaults.

## Asset Registry

An Asset is anything Jarvis can observe, reason about, show in Mission Control or eventually manage through explicit safe policies.

Generic examples:

- `docker:example-app`
- `docker:database`
- `docker:reverse-proxy`
- `system:cpu`
- `system:memory`
- `system:disk`

Assets and relationships are persisted in SQLite and survive container restart through `/data/jarvis.db`.

## Dynamic container discovery

Jarvis reads the current live Docker state directly from Docker Engine. Mission Control does not use baselines, event history or previous observations as the source of truth for current Docker status.

Unknown containers are never auto-started and cannot receive restart actions.

## Safety model

Jarvis-os is safety-first.

Jarvis must never auto-start:

- Unknown containers
- Protected containers
- Stopped-by-design containers
- Any asset whose dependency guards fail

Jarvis does not delete files, delete containers, delete Docker volumes, prune Docker, change firewall rules, change DNS settings, change Docker volumes or run arbitrary shell commands.

AI may explain and suggest, but AI cannot execute actions directly and cannot bypass policies, approvals or Action Engine safety checks.

## Recommended Docker installation

```bash
git clone https://github.com/stuetcl-sudo/Jarvis-os.git jarvis
cd jarvis
git checkout feature/action-engine
cp .env.example .env
docker compose up -d --build
```

Open Mission Control on the trusted host or trusted private network:

```text
http://localhost:8088
```

Do not expose port `8088` directly to the public internet.

## Update commands

```bash
cd jarvis
git checkout feature/action-engine
git pull
docker compose up -d --build
```

## Configuration

Safe generic `.env` defaults:

```env
SAFE_MODE=true
ALLOW_RESTART_STOPPED=true
WORKER_ENABLED=true
WORKER_INTERVAL_SECONDS=60
CRITICAL_SERVICES=jarvis-os
PROTECTED_CONTAINERS=jarvis-os
OPTIONAL_SERVICES=
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

Configure your own critical, protected, optional and stopped-by-design services locally in `.env` or through Mission Control classification.

## API

Existing APIs remain available where possible. Legacy `/api/containers/{name}/restart` now queues a safe action instead of executing directly.

Action Engine:

- `GET /api/actions`
- `GET /api/actions/{action_id}`
- `POST /api/actions/queue`
- `POST /api/actions/{action_id}/approve`
- `POST /api/actions/{action_id}/deny`
- `POST /api/actions/{action_id}/cancel`
- `POST /api/actions/{action_id}/run`
- `GET /api/action-log`

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
bash scripts/privacy_check.sh
bash scripts/validate.sh
```

The validation script checks endpoint health plus Docker, Event Engine, Asset Registry, Policy Engine and Action Engine regressions. The privacy check scans tracked Git files only.

## Architecture docs

See:

```text
docs/ARCHITECTURE.md
docs/EVENT_ENGINE.md
docs/ASSET_REGISTRY.md
docs/POLICY_ENGINE.md
docs/ACTION_ENGINE.md
SECURITY.md
```

## Future compatibility

Future integrations can publish events, register assets, evaluate policies and queue safe actions without changing the core:

- Home Assistant integrations
- Network-controller integrations
- DNS-filter integrations
- UPS integrations
- Private-network integrations
- Calendar integrations
- Notification integrations
- LLM reasoning
