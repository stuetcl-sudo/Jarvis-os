# Medication attention, rewards and daily wellbeing

Branch: `feature/family-rewards-wellbeing`, based on `fix/shared-wall-dashboard`.
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
Wall accounts can read the board but cannot award chores, edit rules or redeem.
Existing routine/task permissions remain unchanged. No retrospective awards or
background reconciliation of earlier completions. If HA completion succeeds but
reward storage fails, the cross-system write is not atomic; inspect the error,
not automatically invent missing credit.

## Voluntary daily wellbeing

Two sets of large choices: good/okay/hard mood and high/low/empty energy.
These are user-entered answers, never inferred or scored. The main home card is
compact; full person cards and the two-choice form are in the Dagsform tab.
No explanation, diagnosis, chart, reminder or point penalty is required.

Personal accounts can write/remove their own answer; adults may assist children.
Wall accounts may enter shared answers for family members with CSRF, but cannot
read or overwrite private answers or submit a private one. Private values are
returned only to that person's account; other readers see no shared answer.
The sharing checkbox explains visibility. Edits replace today's answer; saving a
new day's answer removes that person's previous-day row. There is no mood history
API. The active household date rejects stale submissions. Deleting a person
cleans up reward/check-in records and anonymizes their actor references.

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

## ServerHub staging

```bash
(
  set -e
  cd /docker/Jarvis-os-ui-staging
  git fetch origin
  git switch --detach origin/feature/family-rewards-wellbeing
  docker compose -p jarvis-staging -f compose.staging.yml up -d --build
  curl -fsS http://127.0.0.1:8098/api/health
)
```

Open http://localhost:8098 using the existing SSH tunnel. First use an adult
account to create a reward agreement, then test a child and wall account. The
previous `deploy-shared-wall.sh` pins the earlier fix and is not a deploy command
for this feature. Production 8088 requires its own reviewed deployment.
