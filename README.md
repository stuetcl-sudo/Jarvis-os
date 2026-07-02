# Jarvis-os v0.10

Jarvis-os is a local, private home dashboard with family views, local authentication, calendar, weather, routines, Docker monitoring, system health and a safety-first Action Engine.

The product direction for v1.0 is a flexible home dashboard that works without AI. Jarvis AI remains an optional future module rather than a requirement for the dashboard.

Current release: `0.10.0`.

## What is new in v0.10

v0.10 makes owner administration easier for ordinary home users while preserving the existing backend and security model.

- New Danish administration areas: **Oversigt**, **Hjemmet**, **Funktioner**, **Forbindelser**, **Brugere og adgang**, **Systemstatus** and **Avanceret**.
- A simple overview answers whether the home is operating normally and whether anything needs approval.
- Docker, policies, queued actions, events and technical asset details are grouped under **Avanceret**.
- Technical actions use clearer explanations, confirmations and inline status messages.
- Desktop, tablet, mobile and keyboard navigation are improved.
- Existing roles, sessions, CSRF protection, APIs, policies and Action Engine behavior remain unchanged.

v0.10 does not add a wizard, a layout editor, module enable/disable APIs, new integrations or Jarvis AI.

## Current status

- The family dashboard is available at `/`.
- The dedicated tablet wall dashboard is available at `/wall`.
- Owner administration is available at `/admin`.
- The background worker runs every 60 seconds by default.
- Event Engine, Asset Registry, Policy Engine and Action Engine remain enabled.
- Recommendations and incidents are non-destructive.
- Auto-start remains disabled by default.
- Unknown Docker containers are discovered dynamically and remain visible until classified.

## Action Engine

Actions are separate from policies. Policies may recommend or queue actions, but they do not execute them directly.

```text
Policy Decision
↓
Action Queue
↓
Approval
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

`docker.start_container` is the only Docker executor. It uses the Docker SDK and never shell execution.

Docker start is allowed only when `SAFE_MODE=true`, the asset exists, the asset type is `docker_container`, the asset state is `exited`, the asset is not protected, the asset classification is `optional`, the asset is not unknown, required approval is present and dependency guards pass.

No stop, delete, prune, exec, compose or arbitrary shell actions exist.

## Manual approval workflow

Open **Administration → Avanceret → Handlinger og godkendelser**. A stopped optional Docker asset can create a safe restart request. The owner must approve and run the action. Safety checks run immediately before execution, and Jarvis verifies the live Docker state afterward.

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

An asset is anything Jarvis can observe, explain, show in Administration or eventually manage through explicit safe policies.

Generic examples:

- `docker:example-app`
- `docker:database`
- `docker:reverse-proxy`
- `system:cpu`
- `system:memory`
- `system:disk`

Assets and relationships are stored in SQLite and survive container restarts through `/data/jarvis.db`.

## Safety model

Jarvis must never auto-start unknown containers, protected containers, stopped-by-design containers or containers blocked by dependency guards.

Jarvis does not delete files, containers or Docker volumes, prune Docker, change firewall or DNS settings, change Docker volumes or run arbitrary shell commands.

Any future assistant reasoning may explain and suggest, but it cannot execute actions directly or bypass policies, approvals or Action Engine safety checks.

## Recommended Docker installation

Use a trusted host and network.

```bash
git clone https://github.com/stuetcl-sudo/Jarvis-os.git jarvis-os
cd jarvis-os
git checkout main
cp .env.example .env
docker compose up -d --build
```

Open the family dashboard:

```text
http://localhost:8088/
```

Open the tablet wall dashboard after login:

```text
http://localhost:8088/wall
```

Open owner administration:

```text
http://localhost:8088/admin
```

For remote access, use a trusted LAN, Tailscale or an authenticated reverse proxy. Do not expose port `8088` directly to the public internet.

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

Optional containers must be configured explicitly before they can be considered optional. Auto-start remains disabled unless `ALLOWED_AUTO_START_CONTAINERS` or a saved asset classification allows it and the Action Engine safety checks pass.

See `.env.example`, `docs/WEATHER.md`, `docs/CALENDAR.md` and `docs/ROUTINES.md` for family integrations.

## API

Existing APIs remain available. The legacy `/api/containers/{name}/restart` route queues a safe action instead of executing directly.

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

The validation script checks privacy rules, focused regressions, Docker Compose configuration, a rebuilt live service, protected routes, family assets and Docker, Event Engine, Asset Registry, Policy Engine and Action Engine consistency.

A successful run ends with:

```text
Validation OK.
```

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

Future integrations can publish events, register assets, evaluate policies and queue safe actions without changing the core. Product-specific integrations and Jarvis AI should remain optional modules with explicit safety boundaries.
