# Family pictogram routines

## Purpose

The routine card gives a child one clear task at a time. Pressing **Færdig** stores the completed step on the Jarvis server and shows the next pictogram without reloading the page.

The fixed routine IDs remain:

- `morning`
- `evening`

## Adult editor

Owner and adult accounts can open **Rediger rutine** from the family dashboard. Child and wall-display accounts can use progress controls but cannot read or write routine definitions.

The editor supports:

- routine label
- task title
- local pictogram choice
- optional guidance time in `HH:MM`
- active weekdays
- add and delete
- drag-and-drop ordering
- accessible **Flyt op** and **Flyt ned** controls
- reset to the original default definition

Saving happens without a page reload. Delete, closing with unsaved changes and reset-to-default require confirmation.

## Default routines and weekday behavior

The default morning routine contains waking, TV, breakfast, clothes, teeth, iPad time, outerwear and school.

The default evening routine contains homework, exercise, free play, dinner, table cleanup, bath, free play, teeth, undressing, laundry basket, bed, audio and sleep.

The default **Gå i bad** task is positioned immediately after **Rydde af bordet** and is active only on Wednesday and Sunday. Weekdays are stored as fixed values `0` through `6`, from Monday through Sunday. An empty weekday list means every day.

The server uses `ROUTINE_TIMEZONE`, safely defaulting to:

```text
ROUTINE_TIMEZONE=Europe/Copenhagen
```

Suggested times are guidance only. Jarvis never completes or skips a task because of the clock.

## Separate persistence

Editable definitions are stored in:

```text
/data/family_routine_definitions.json
```

Daily progress remains stored separately in:

```text
/data/family_routines.json
```

Both stores use an in-process lock, a temporary file, filesystem flush and atomic replace. Missing or malformed definition data falls back safely to the original defaults. Valid custom definitions are not overwritten during startup.

## Validation

Only `morning` and `evening` are accepted. A routine must have a short safe label and between 1 and 30 tasks.

Each task contains only:

- a stable safe ID
- a required trimmed title
- one allowlisted pictogram key
- an optional `HH:MM` time
- zero or more allowlisted weekdays

Missing IDs for newly added tasks are generated server-side. Duplicate IDs, HTML-like input, scripts, URLs, unknown pictograms, invalid times, invalid weekdays and arbitrary fields are rejected.

The pictogram allowlist matches the symbols in `app/static/pictograms/routines.svg`. No upload or external image URL is supported.

## Progress reconciliation after edits

Task IDs are the stable progress key.

- Renaming a task or changing its pictogram preserves progress when its ID and order remain valid.
- Removed task IDs disappear from progress.
- Newly added tasks remain incomplete.
- Reordering keeps only the longest still-valid completed prefix.
- The current position is clamped to the active tasks for the local date.
- Resetting a definition resets only that routine's progress for the current day.
- The other routine is not changed.

## One task at a time

The dashboard shows one local pictogram, one short Danish task title, current progress, **Færdig**, **Tilbage**, a morning/evening switch and **Godt klaret!** after the final step.

## Roles, privacy and CSRF

Owner, adult, child and wall-display sessions may read and update daily progress. Anonymous visitors receive no task data.

Only owner and adult may use:

```text
GET  /api/family/routines/definitions
PUT  /api/family/routines/definitions/morning
PUT  /api/family/routines/definitions/evening
POST /api/family/routines/definitions/morning/reset-default
POST /api/family/routines/definitions/evening/reset-default
```

PUT and reset-default require the existing `X-CSRF-Token`. The session role is resolved server-side; query parameters and body fields cannot elevate access. Existing owner-only APIs outside the routine namespace are unchanged.

## Pictograms

The original neutral line drawings are stored locally in:

```text
app/static/pictograms/routines.svg
```

No external library, CDN, tracking URL, base64 image or personal photo is used. Pictograms always have accompanying text and accessible labels.

## Safe restart

```bash
docker compose up -d --build --force-recreate jarvis-os
```

## Safe checks

Anonymous progress privacy check:

```bash
curl -sS http://localhost:8088/api/family/routines
```

Definition endpoints require an authenticated owner/adult session. Write checks also require the matching CSRF token. Never place session or CSRF values in documentation or source control.

Use the dashboard's **Gendan standard** action to reset one definition without deleting unrelated Jarvis data. Use **Nulstil rutine** to reset only daily progress.
