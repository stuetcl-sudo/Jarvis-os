# Jarvis-os v0.9

Jarvis-os is a local server assistant for Docker monitoring, system health, Event Engine, Asset Registry, Policy Engine, Action Engine, family dashboards, local authentication, calendar, weather and routines.

Release branch: `feature/jarvis-v0.9`.

## Current status

- Background worker runs every 60 seconds.
- Mission Control UI runs on port `8088`.
- Event Engine remains enabled.
- Asset Registry persists observed assets in SQLite.
- Policy Engine evaluates events and stores explainable decisions.
- Action Engine stores queued, approved, denied, completed and failed actions.
- Docker containers are represented as assets such as `docker:example-app`.
- System resources are represented as assets such as `system:cpu` and `system:memory`.
- Recommendations and incidents are non-destructive.
- Auto-start remains disabled by default.
- Unknown Docker containers are discovered dynamically and stay visible until classified.
- The authenticated family dashboard is available at `/`.
- The dedicated tablet wall dashboard is available at `/wall`.

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

Supported action types:

- `docker.start_container`
- `recommendation.create`
- `incident.create`
- `notification.create_stub`

`docker.start_container` is the only Docker executor. It uses Docker SDK, never shell execution.

Docker start is allowed only when `SAFE_MODE=true`, the asset exists, the asset type is `docker_container`, the asset state is `exited`, the asset is not protected, the asset classification is `optional`, the asset is not unknown, approval is present when required, and dependency guards pass.

No stop, delete, prune, exec, compose or shell actions exist.

## Manual approval workflow

Mission Control shows an Action Queue section. A stopped optional Docker asset shows **Request restart**. That button queues `docker.start_container`. The user must approve and run the action. Safety checks run immediately before execution. After execution, Jarvis verifies live Docker state and stores the result and explanation.

## Policy Engine

Default policies:

- Unknown asset discovered → recommend classification.
- Critical asset stopped → create critical incident and recommendation.
- Optional asset stopped → recommend restart and queue a waiting-approval action.
- Stopped-by-design asset stopped → ignore with explanation.

Dependency guard behavior is generic and relationship-driven. Define dependencies with `ASSET_DEPENDENCIES`, for example:

```env
ASSET_DEPENDENCIES=docker:example-app>docker:example-network,docker:worker>docker:database
```

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

## Safety model

Jarvis must never auto-start unknown containers, protected containers, stopped-by-design containers, or containers blocked by dependency guards.

Jarvis does not delete files, delete containers, delete Docker volumes, prune Docker, change firewall rules, change DNS settings, change Docker volumes or run arbitrary shell commands.

Assistant reasoning may explain and suggest, but it cannot execute actions directly and cannot bypass policies, approvals or Action Engine safety checks.

## Recommended Docker installation

Use any suitable Docker project directory on a trusted host.

```bash
git clone https://github.com/stuetcl-sudo/Jarvis-os.git jarvis-os
cd jarvis-os
git checkout feature/jarvis-v0.9
cp .env.example .env
docker compose up -d --build
```

Open the family dashboard from a trusted network:

```text
http://localhost:8088/
```

Open the tablet wall dashboard after login:

```text
http://localhost:8088/wall
```

Mission Control remains available to the owner role at `/admin`.

For remote access, use a trusted LAN, Tailscale, or an authenticated reverse proxy. Do not expose port `8088` directly to the public internet.

## Configuration

Safe generic defaults:

```env
APP_NAME=Jarvis-os
SAFE_MODE=true
ALLOW_RESTART_STOPPED=true
WORKER_ENABLED=true
WORKER_INTERVAL_SECONDS=60
CRITICAL_SERVICES=jarvis-os
PROTECTED_CONTAINERS=jarvis-os
OPTIONAL_SERVICES=
IGNORED_SERVICES=
ALLOWED_RESTART_CONTAINERS=
ALLOWED_AUTO_START_CONTAINERS=
ASSET_DEPENDENCIES=
DB_PATH=/data/jarvis.db
```

Optional containers must be configured explicitly before they can be considered optional. Auto-start remains disabled unless `ALLOWED_AUTO_START_CONTAINERS` or saved asset classification allows it and the Action Engine safety checks pass.

See `.env.example`, `docs/WEATHER.md`, `docs/CALENDAR.md` and `docs/ROUTINES.md` for the family integrations.

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

Core, Brain, Event Engine, Asset Registry, Policy Engine, family and classification APIs remain available.

## Validation

```bash
bash scripts/privacy_check.sh
bash scripts/validate.sh
```

The validation script checks privacy rules, focused Python regressions, Docker Compose configuration, a rebuilt live service, protected routes, family assets and the Docker, Event Engine, Asset Registry, Policy Engine and Action Engine consistency checks.

## Security

See `SECURITY.md` before deploying. Jarvis includes local session authentication, role-based access and CSRF protection for write requests. Docker socket access remains highly privileged, so deploy only on a trusted host and network.

## Architecture docs

```text
docs/ARCHITECTURE.md
docs/EVENT_ENGINE.md
docs/ASSET_REGISTRY.md
docs/POLICY_ENGINE.md
docs/ACTION_ENGINE.md
docs/WEATHER.md
docs/CALENDAR.md
docs/ROUTINES.md
```

## Future compatibility

Future integrations can publish events, register assets, evaluate policies and queue safe actions without changing the core. Product-specific integrations should remain optional plugins with explicit safety boundaries.
