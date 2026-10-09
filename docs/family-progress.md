# Medication attention, rewards and daily wellbeing

Current follow-up: `fix/quick-wellbeing`, based on `feature/family-rewards-wellbeing`.
No release version change or production deployment is included.

## Medication attention

The main home medicine card turns red and its border slowly pulses over four
seconds when today's scheduled household time has passed without a registration.
It displays the affected people/time and elapsed minutes, moves first in the
primary grid, and considers everyone even if another person is selected.
Taken and skipped slots do not trigger attention. The card remains readable.
The pulse can be disabled per device; reduced-motion preferences disable animation.

Only successfully fetched data less than 90 seconds old are used for attention.
A failed refresh clears the attention state and shows the existing unavailable
message; yesterday's slots cannot keep today's card red. This indicates missing
registration, not ingestion, clinical risk or instructions to take a dose.
The dedicated `/wall` layout remains separate; the shared application supports
its authenticated wall account with read-only medication controls.

## Reward board

Only active accounts with family visibility enabled appear here; owners remain
hidden by default until explicitly enabled in Administration.
Adults configure a goal, cost (1–1000 stars) and up to 40 rules per active person.
Each rule has 1–20 stars and references a morning/evening routine, an existing
Home Assistant task, or a new daily chore on the board. Existing routines and
linked tasks use their existing completion actions; daily chores are completed
on the board. No extra registration is needed for linked activities.

A server ledger records one award per person/source/day. Retries, reset/recomplete
and concurrent clicks cannot duplicate it. Only the final routine step earns the
configured stars. Linked tasks require a fresh unfinished HA item and a successful
HA completion, not merely a cached screen. Task UID links must be selected again
if an external integration recreates the task with a new UID.

Badges show five rewarded morning completions (Morgenmester) and ten rewarded
family chores/tasks (Hjælpsom hånd); no streak penalties or family rankings.
Historical stars and badge progress survive configuration edits. Adults approve
redemption against the current goal/cost; SQLite serializes concurrent redemptions.
Available stars are earned minus redeemed; lifetime earned/spent remain visible.
Medication and wellbeing have no reward hooks. No arbitrary child credit API.

Adults manage all boards. Children can complete their own configured daily chores.
Wall accounts can read and mark configured daily chores for family members,
with the same server-side per-day deduplication. They cannot set star values,
edit rules or redeem rewards. This supports the shared physical dashboard.
Existing routine/task permissions remain unchanged. No retrospective awards or
background reconciliation of earlier completions. If HA completion succeeds but
reward storage fails, the cross-system write is not atomic; inspect the error,
not automatically invent missing credit.

## Voluntary daily wellbeing

Two sets of large choices: good/okay/hard mood and high/low/empty energy.
The homepage and Dagsform tab offer direct buttons that save each choice immediately.
Either field may stand alone; missing answers are never inferred. Rapid choices are
queued per person and partial updates merge under a server transaction. Failed saves
show an error and restore the server's selection; successful choices persist across devices.

This is a shared family board. New answers are always shared; there is no privacy
checkbox, dialog or Save button. Legacy private records stay hidden and a new choice
replaces them without publishing the old counterpart. Personal accounts can write/remove
their own answer; adults may assist children. Wall accounts can enter shared answers
for family members with CSRF. Selecting a new day removes the person's previous-day
row; stale dates are rejected. There is no mood history, inferred feeling or reward hook.
Deleting a person cleans up records and anonymizes their actor references.

## Persistence and validation

All substantive data are stored in additive SQLite tables on the Jarvis server;
only the animation preference is stored locally. Reads are authenticated/no-store;
writes have CSRF and endpoint-specific role validation. No HA token is exposed.
The new modules follow the existing light shell and safe DOM text rendering.

- 95 focused Python tests passed across new progress, existing care/planning,
  roles/auth, tasks/routines, dedicated wall, user management and frontend safety.
- 27 progress/role/frontend tests passed after the final retention, family
  visibility and concurrency refinements.
- Node tests covered medicine times, household timezone, midnight and taken/skipped.
- Local Chromium exercised red attention, pulse preference/reload, medicine check,
  failed refresh/recovery, chore + final routine awards, redemption, private/shared
  check-ins, wall permissions, reduced motion and nine Surface/tablet/phone views.
  Synthetic accounts, temporary DB and disabled worker; no live household data.
- Syntax and diff checks passed. Staging configuration passed, but actual Docker
  build cannot run here (`docker: command not found`). Live ServerHub staging
  review remains required. Production/database-lock/login recovery is separate.

## Quick wellbeing follow-up validation

- 32 Python tests passed: progress, authentication roles, frontend safety and shared wall.
- Chromium verified partial autosave, rapid choices, reload persistence, shared wall,
  error/retry handling and Surface/tablet/phone layouts against a temporary database.
- JavaScript syntax and diff checks passed. Staging configuration passed; Docker
  is unavailable locally, so ServerHub staging still needs the actual build.

## ServerHub staging

### Unified tasks/rewards follow-up

Daily reward chores now appear in Tasks as a live projection of the existing
reward agreement. They are not copied into Home Assistant or a second task table.
Completing them from either view uses the same per-person/source/day ledger;
repeat clicks do not award extra stars, and a new day gets a new task ID.
Existing agreements and reward history are preserved without a schema migration.

Tasks initially shows **Alle**, including assigned and unassigned tasks. New HA
tasks can select a family member at creation. Assignment is only applied when
the new HA UID can be identified unambiguously; otherwise a notice explains
that the created task remains under Familien for manual assignment.

Reward agreement editing loads current HA tasks automatically. Changing the
selected task changes its label, labels support the same 160-character limit
as Tasks, and already-linked options are disabled. Projected daily chores are
excluded from the HA task picker to avoid linking the same activity twice.
Children can complete only their own daily reward chores. Wall accounts retain
their existing reward-chore permission, not permission to edit/complete HA tasks.
All writes still require CSRF and server-side role checks.

Validation: 76 focused Python tests and 5 JavaScript tests passed. Chromium
checked creation, task linking, long titles, assignment, completion and reward
credit against synthetic HA responses and a temporary real SQLite database.
Six light/dark Surface, tablet and phone layouts had no horizontal overflow or
JavaScript errors. Live Home Assistant and Docker staging still need ServerHub
review; Docker is unavailable in the local test environment.

Use this branch for the follow-up (it includes compact dashboard/energy work):

```bash
(
  set -e
  cd /docker/Jarvis-os-ui-staging
  git fetch origin
  git switch --detach origin/fix/unified-tasks-rewards
  docker compose -p jarvis-staging -f compose.staging.yml up -d --build
)
```

After startup, check `curl -fsS http://127.0.0.1:8098/api/health` and review the
task/reward flow using the existing SSH tunnel. Production is unchanged.

### Earlier quick-wellbeing staging

```bash
(
  set -e
  cd /docker/Jarvis-os-ui-staging
  git fetch origin
  git switch --detach origin/fix/quick-wellbeing
  docker compose -p jarvis-staging -f compose.staging.yml up -d --build
  curl -fsS http://127.0.0.1:8098/api/health
)
```

Open http://localhost:8098 using the existing SSH tunnel. First use an adult
account to create a reward agreement, then test a child and wall account. The
previous `deploy-shared-wall.sh` pins the earlier fix and is not a deploy command
for this feature. Production 8088 requires its own reviewed deployment.
