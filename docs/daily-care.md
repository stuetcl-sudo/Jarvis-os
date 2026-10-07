# Daily overview, pet expenses and family medication

Branch `feature/daily-care` extends `feature/home-modules`. No release number
change, merge or production deployment is included.

## Home screen

The application home screen now contains short links and summaries, rather than
all full module views. Calendar appointments intersecting today (and not already
ended), meals dated today, tasks due today, today's pet care and today's medicine
records are shown. Future days remain in the module tabs. Shopping is a current
outstanding count; energy uses available daily meter values; cameras and weather
show current status. Overdue tasks and pet reminders remain accessible in their
modules and are deliberately not represented as appointments due today.

Summaries reuse the authorized module data and respect server-rendered module
and role visibility. No new overview API can bypass those permissions. Date
filtering uses the household timezone. The dedicated `/wall` dashboard retains
its existing rendering; the new overview applies to the main family application.

## Pet reminders

A reminder can repeat every N days, weeks, months or years, or remain a one-off.
Completing a repeating reminder records that occurrence and advances one
interval from its scheduled date. It does not silently skip overdue occurrences.
The original calendar day is retained: January 31 -> February 28 -> March 31;
February 29 annual reminders return to February 29 in a leap year.

A database write lock and expected occurrence date prevent duplicate completion
from advancing twice. Out-of-range next dates fail without changing the record.
Editing a reminder resets its calendar anchor; changing its date or interval resets its completed flag. Deleting a
reminder or pet removes the dependent history. There are no background scheduler
jobs or external notification deliveries.

## Pet expenses

Owners and adults can add and delete actual expenses per pet. Store positive
integer Danish øre, expense date, category, description and optional notes.
Categories: food, veterinarian, medicine, insurance, care and other. The view
selects a month, totals the registered costs and displays category subtotals and
the underlying entries. Other pets' entries remain isolated. Children and wall
accounts cannot read or write financial records. No bank connection, future
expense prediction or automatic recurring charges are included.

## Medication

Dennis selected a shared overview for adults. Owners and adults can see and
manage all household medication plans, including plans for children. Children,
wall displays and anonymous users cannot access the view or its API. Writes
require CSRF; responses are no-store. Plans reference active household accounts,
not freely typed people. Account deletion removes that person's plans and records.

Each user-entered plan contains a name, instructions, start/end dates, selected
weekdays, daily times and an active/pause state. The UI separates today from all
plans and the last 30 days of manual records. At each scheduled time an adult can
record taken, skipped, or undo the record, with actor and timestamp. Only today's
scheduled times can be changed. One record per plan/day/time prevents duplicate
rows. A revision check rejects changes from stale plan editors and records from
an outdated plan; writes are serialized inside SQLite transactions. Historical
records preserve the name/instructions in effect when they were recorded.

This is a manual tracker, not clinical decision support. The application does
not calculate doses, check interactions, recommend treatments, verify ingestion,
handle prescriptions or deliver push reminders. An empty record means only
'unrecorded'. PRN/as-needed medication and missed-dose guidance are outside this
version. Do not put medication names or dose details on shared or child screens;
the adult home screen contains only an aggregate number of unrecorded slots.

## Storage and rollout

Initialization additively extends existing pet reminder tables and creates pet
expense, reminder occurrence, medication plan and medication record tables.
Existing profiles, one-off reminders and other modules are preserved. Use the
isolated staging database before considering a production release.

On ServerHub:

```bash
cd /docker/Jarvis-os-ui-staging
git fetch origin
git switch feature/daily-care
git pull --ff-only
docker compose -p jarvis-staging -f compose.staging.yml up -d --build
```

Review the today-only overview, recurring reminder month boundaries, expenses
and adult/child access with real staging accounts on port 8098. Production 8088
requires separate approval.

## Validation

- 133 focused Python tests passed in `.venv`, covering existing modules, role
  access, migrations, authentication, staging config and the new care behavior.
- The final plan/history/editor adjustments passed another 33 focused tests.
- Real Chromium browser checks passed at 1368x912, 1024x768 and 390x844. The
  checks covered today-only filtering, recurring month-end dates, expense
  registration, medication creation, taken/reload/undo and horizontal overflow;
  no JavaScript exceptions were reported. These used an isolated temporary
  database and synthetic calendar/task/meal responses, not ServerHub accounts.
- JavaScript syntax checks and `git diff --check` passed.
- `scripts/staging.sh test` passed its compose configuration test, then stopped
  with `docker: command not found`. No actual Docker staging deployment or
  ServerHub health check has been performed from this workspace.
