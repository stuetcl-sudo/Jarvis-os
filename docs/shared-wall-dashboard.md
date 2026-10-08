# Shared dashboard for wall accounts

The main family application previously omitted planning, pets, shopping,
medication, energy and camera templates for `wall_display`. Returning to that
account therefore looked like an older UI. This branch includes the shared
modules for the wall account without promoting it to owner. Navigation now shows
the signed-in account and its role. The shared header also uses the compact app
sizes instead of the legacy wall heading rules.

Wall accounts read shopping, planning and pets using existing read-only APIs.
Energy, history, selected cameras and snapshots now allow authenticated wall
accounts; configuration stays owner-only and child accounts remain denied.
Financial pet records remain adult-only.

Medication has a separate no-store GET `/api/family/medication/display`: only
active family members' scheduled entries for today, with person, name, time and
manual status. It excludes instructions, future plans, history, revisions and
actors. Wall checkboxes show status and are disabled. Full medication access
and writes remain owner/adult-only, with existing CSRF/revision/day checks.

The dedicated `/wall` screen explicitly opts out of these extra app modules and
retains its existing configured layouts. No account roles or passwords change.

## Validation

- 77 focused Python tests passed, including roles, auth, module access, planning,
  medication projection, CSRF, dedicated wall layouts and frontend safety.
- 11 relevant tests passed after the final status/rendering adjustments.
- Local Chromium checked all six module links, medication privacy/read-only
  controls, visible account role, reload, adult controls and horizontal overflow
  at 1368x912, 1024x768 and 390x844. No JavaScript exceptions. Isolated synthetic
  accounts and a temporary DB were used, with the worker disabled.
- Node syntax checks and `git diff --check` passed.
- Staging compose configuration passed; actual build stopped because Docker is
  unavailable here. ServerHub staging build and live review remain necessary.

The previously reported persistent SQLite lock has not been reproduced or
resolved by this change. The screenshot alone does not establish its recurrence.
The failed Dennis login and why the browser returned to the wall account also
remain unverified until server-side account/session evidence is available.
No production deployment, restart, database repair or release change is included.

## ServerHub staging

```bash
(
  set -e
  cd /docker/Jarvis-os-ui-staging
  git fetch origin
  git switch --detach origin/fix/shared-wall-dashboard
  docker compose -p jarvis-staging -f compose.staging.yml up -d --build
  curl -fsS http://127.0.0.1:8098/api/health
)
```

Use the existing SSH tunnel and open http://localhost:8098. Verify using a real
wall account and a separate owner account. Production port 8088 needs separate
approval and the established backup/deployment procedure.
