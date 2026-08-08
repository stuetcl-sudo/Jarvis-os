# Jarvis-os v0.22.3

Jarvis-os is a local, private home dashboard with family views, local authentication, calendar, weather, routines, Home Assistant family content, Docker monitoring, system health and a safety-first Action Engine.

The product direction for v1.0 is a flexible home dashboard that works without AI. Jarvis AI remains an optional future module rather than a requirement for the dashboard.

Current release version: `0.22.3`.

## What is new in v0.22.3

- Home Assistant entity selections saved in Administration are now used by the weather, calendar, meal-plan and family-task runtime services.
- Existing environment-based entity configuration remains available as a fallback for installations without saved selections.
- Normal Scrypted root URLs can safely follow same-origin redirects to the public endpoint.
- Administration page access is enforced as owner-only on the server.

## What is new in v0.22.2

v0.22.2 resolves a Docker-read incident after a later successful Docker inventory check. Resolved incidents remain in history, while current Docker read failures continue to be reported as active problems.

## What is new in v0.22.0

v0.22.0 adds practical owner configuration for family modules and independent wall or tablet screens.

- Owners can configure calendar days, meal-plan days and UV guidance for the normal family dashboard.
- Existing family modules can be enabled or disabled without changing the dashboard layout.
- Multiple named screen profiles can use independent modules, screen types and assigned wall-display accounts.
- Screen URLs, responsive viewport behavior and existing privacy boundaries remain intact.

## What is new in v0.21.0

v0.21.0 adds safe, owner-only integration visibility to Administration without introducing automatic corrective actions.

- Home Assistant, Scrypted, electricity prices and Jarvis have consistent, privacy-preserving status cards.
- Status is based on actual service and configured-entity health checks rather than configuration presence alone.
- Fixed Danish guidance explains safe next steps without exposing URLs, credentials, entity IDs or raw errors.
- Owners can refresh integration status manually with same-origin credentials; no automatic integration polling is added.
- Allowlisted technical details are available in secondary, collapsed sections.
- Integration problems appear in the admin overview with deterministic severity and integration ordering.
- Existing owner-only access, session protections and privacy boundaries remain unchanged.

## What is new in v0.20.0-alpha.1

v0.20.0-alpha.1 begins the self-service installation foundation. This alpha establishes one authoritative application version before bootstrap, setup-state and migration work is introduced.

- Weather, calendar, meal plans, family lists and routines keep the last successfully displayed data during temporary refresh failures.
- Clear stale-data messages replace disappearing dashboard cards.
- Isolated staging runs on `127.0.0.1:8098`.
- Staging has its own database, volume and network.
- Staging does not use the Docker socket, production `.env` or production secrets.

## Managed Home Assistant connectivity

Jarvis probes a managed Home Assistant only through its fixed container address on the dedicated managed network. Browser navigation uses a separate, explicit server setting:

```env
MANAGED_HOME_ASSISTANT_PUBLIC_URL=https://home-assistant.example.com
```

The value must be a valid `http://` or `https://` Home Assistant base URL without credentials, query parameters or fragments. It is never derived from browser headers or request data. If it is unset, backend readiness and token validation continue, but Jarvis suppresses the browser link and shows a configuration message.

Normal Compose deliberately does not reference the managed network, so it starts safely before managed Home Assistant is installed. After the one-shot installer has created and verified the external network, explicitly attach Jarvis with:

```text
docker compose -f docker-compose.yml -f compose.managed-home-assistant.yml up -d jarvis-os
```

The overlay keeps Jarvis on its normal network for the restricted Docker proxy and additionally joins only the externally owned `jarvis-managed-home-assistant-network`. Compose does not create or delete that external network. Do not enable the overlay before the installer has successfully created the network.

## Earlier dashboard milestone: v0.13

v0.13 expands the family dashboard with practical list editing, clearer UV guidance and a more flexible shared wall layout.

- Home Assistant `todo.shopping_list` is included as the standard shopping list.
- Owner and adult roles can add, rename and remove family-list items.
- Authenticated family roles can mark items completed.
- List changes retain the existing session, role and CSRF protection.
- The UV indicator uses clear green, yellow and red guidance.
- The remove control is compact while preserving an accessible text label.
- The wall dashboard now uses a responsive CSS grid across large displays, landscape tablets, portrait tablets and mobile.
- With 1 calendar day selected, the routine and calendar share the row at half width.
- With 3, 5 or 7 days selected, the calendar uses the full available width.

v0.13 does not add a layout editor, camera access, energy-price automation or Jarvis AI.

## Family dashboard foundation introduced in v0.12

- `calendar.madplan` supplies the family meal plan.
- `todo.familieopgaver` supplies shared family tasks.
- `todo.lektier` supplies homework items.
- Today's dinner is shown prominently, followed by the upcoming meal plan.
- Family tasks and homework are shown as separate lists with deadlines and descriptions when available.
- Authenticated family members and the shared wall display can mark items completed through Home Assistant.
- Task completion uses the existing session, role and CSRF protection and only calls `todo.update_item` with status `completed`.
- The family calendar defaults to 3 days; 1, 3, 5 and 7 day choices remain available.
- Meal plans, tasks and homework are shown on both `/` and `/wall` and refresh automatically.
- No additional family-content database is introduced in Jarvis.

## Calendar and wall display introduced in v0.11

- The family calendar can show 1, 3, 5 or 7 days.
- Calendar events are grouped clearly by day with family-friendly empty states.
- Completed timed events disappear automatically after their end time.
- Events in progress remain visible, and all-day events remain visible until midnight.
- The visible calendar is refreshed every 30 seconds without requiring a page reload.
- `/wall` reuses the same family dashboard, calendar, weather and routines as `/`.
- The shared wall display hides personal names and owner-only technical details.

## Administration introduced in v0.10

- Danish administration areas: **Oversigt**, **Hjemmet**, **Funktioner**, **Forbindelser**, **Brugere og adgang**, **Systemstatus** and **Avanceret**.
- A simple overview answers whether the home is operating normally and whether anything needs approval.
- Docker, policies, queued actions, events and technical asset details are grouped under **Avanceret**.
- Technical actions use clearer explanations, confirmations and inline status messages.
- Desktop, tablet, mobile and keyboard navigation are improved.

## Current status

- The family dashboard is available at `/`.
- The authenticated shared wall display is available at `/wall` and uses the same family dashboard foundation.
- Home Assistant meal plans, family tasks, homework and shopping lists are available after login when the configured entities exist.
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

On first use Jarvis generates `/data/config-master.key` inside the persistent
`jarvis_data` volume. This key encrypts locally stored integration tokens. Back
up the volume and do not delete or replace the key after saving secrets.

Jarvis reads Docker only through its restricted, read-only socket proxy. The
default `DOCKER_SOCKET_PATH=/var/run/docker.sock` matches normal Debian/Ubuntu
Docker Engine installations. If `docker context inspect` reports a different
Unix socket (for example rootless Docker under `/run/user/<uid>/docker.sock`),
set that host path in `.env` before starting Jarvis. A missing or incorrect path
now stops the proxy at startup instead of creating a directory and later
reporting a misleading 502 response.

Open the family dashboard:

```text
http://localhost:8088/
```

Open the shared wall display after login:

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
```
