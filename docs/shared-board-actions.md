# Shared family board actions

Dennis approved everyday wall-account writes on 9 October 2026 and separately
approved production deployment after validation. Branch: `fix/shared-board-actions`.
This changes bounded `wall_display` capabilities, not the account's role.
It does not turn a shared screen into an owner or adult account.

## Module review

| View | Wall account behavior | Protected management |
| --- | --- | --- |
| Overblik | Quick routine, medication and voluntary wellbeing actions | No admin controls |
| Ugeoversigt / Madplan | Write shared meals, ingredients, pickup and reminders; send ingredients to shopping | HA calendar and HA meals remain read-only sources |
| Kalender | Read existing events | No new calendar-write API |
| Opgaver | Create with optional person, complete; daily reward chores in the same view | Existing task edit/reassignment/removal still follow owner's role rules |
| Rutiner | Complete, back, reset existing progress | Routine definitions remain adult-only |
| Indkøb | Create a list, add items and check/uncheck purchases | Rename/delete/clear lists and edit/delete items remain adult-only |
| Medicin | Today's scheduled slot: register taken or undo a registration, also on Overblik | Plans, instructions, history, skip and deletion remain adult-only |
| Belønningstavle | Read stars/badges, complete daily chores | Agreement editing and reward redemption remain adult-only |
| Dagsform | Existing voluntary shared mood/energy choices for visible family members | No inferred mood, points or private-history exposure |
| Kæledyr | Record food, water and repeated walks; undo today's care entry | Profiles, health reminders and expenses remain adult-only |
| Energi | Read configured metrics and history | Sensor setup and shared display selection remain owner-only |
| Kamera | Read overview, snapshots and configured live/recording links | Configuration remains owner-only |
| Hjemmet / Vejr | Existing read-only information | No broader HA service execution |
| System / Administration | No wall-account access | Owner-only |

The separate `/wall` display still uses its screen-specific layout/profile and
existing routine controls. It does not gain all application forms; Dennis's
tabbed shared family board is `/` with a `wall_display` session.

## Safety and compatibility

- All writes require an authenticated session, CSRF and backend role validation.
  UI permission flags match those backend checks. The adult `editor` dependency
  is deliberately unchanged; a separate `board_editor` permits only planning,
  shopping-list creation and the bounded medicine display endpoint.
- HA task defaults allow wall creation/completion, not edit/removal. Already
  saved owner action/visibility rules remain authoritative: no migration
  silently overwrites a denial. If these were saved as false, use Administration
  → Brugere → Hvem må ændre hvad? → wall preset **Tillad oprettelse og afkrydsning**,
  then **Gem rettigheder**. The preset changes only those two checkboxes.
- Person selection while creating a task belongs to `task_add`. Editing an
  existing assignment still requires `task_edit`. New HA UID matching remains
  conservative; ambiguous results are left unassigned with a notice.
- `/api/family/medication/display/{plan_id}/record` accepts only `taken` and
  `unmarked`, for today and an active scheduled slot. It uses the same existing
  record transaction, person check and optimistic plan revision as adult writes.
  The actor remains the wall account; it is not attributed to the medicine user.
  Display responses expose an opaque revision/plan ID for concurrency, not
  instructions, snapshots, history, hashes or secrets. A changed plan or day
  requires refresh. Missing registration never means an extra dose is advised.
- Browser write failures retain the server state, display an error and mark the
  summary freshness unknown until a successful refresh. No successful check-off
  is invented when saving fails. Existing reward deduplication is retained.
- Household data remain server-backed and shared across sessions/devices. No
  schema migration or bulk data rewrite is introduced.

## Validation and deployment

126 Python tests passed across board actions, pets/care, medication, planning,
tasks, visibility, rewards/wellbeing, roles/auth, routines, home modules and
frontend safety/foundation. Five Node theme/medicine-attention tests passed.
Additional real Chromium checks used temporary SQLite and synthetic HA tasks,
not household data: wall writes for all everyday modules, all available tabs at
six light/dark Surface/tablet/phone sizes, no horizontal overflow or JS errors,
medicine homepage/module save and undo, failed-save rollback/retry and the owner
admin task preset. Protected admin and full medication reads were rejected.

`scripts/staging.sh test` validated staging configuration but cannot build Docker
here (`docker: command not found`). Live ServerHub Docker/HA validation remains
necessary. No server production command has been executed from this workspace.

Staging (only port 8098):

```bash
(
  set -e
  cd /docker/Jarvis-os-ui-staging
  git fetch origin
  git switch --detach origin/fix/shared-board-actions
  docker compose -p jarvis-staging -f compose.staging.yml up -d --build
)
```

The production helper added after the approved code commit pins that exact
commit, takes a full data archive and checked SQLite backup, preserves a rollback
image, recreates only Jarvis, and checks the served board JS hashes, health and
DB readability. It does not bypass saved task rules or restart other services.
