# Family pictogram routines

## Purpose

The routine card gives a child one clear task at a time. Pressing **Færdig** stores the completed step on the Jarvis server and shows the next pictogram without reloading the page.

## Fixed routines

The fixed routine IDs are:

- `morning`
- `evening`

The morning routine contains waking, a short TV break, breakfast, clothes, teeth, iPad time, outerwear and school.

The evening routine contains homework, exercise, free play, dinner, table cleanup, free play, teeth, undressing, laundry basket, bed, music or audiobook and sleep.

On Wednesday and Sunday, **Gå i bad** is inserted immediately after **Rydde af bordet**. The weekday is determined on the server using `ROUTINE_TIMEZONE`.

Suggested times are guidance only. Jarvis never completes or skips a task because of the clock.

## One task at a time

The dashboard shows:

- one local pictogram
- one short Danish task title
- the current step number
- **Færdig** and **Tilbage** controls
- a morning/evening switch
- **Godt klaret!** after the final step

Owner and adult views also provide a reset action with confirmation. Child and wall-display views may start a completed routine again using the same reset endpoint.

## Server-side persistence

Progress is stored in:

```text
/data/family_routines.json
```

The JSON file contains only routine date, current index, completed task identifiers and timestamps. Writes use a temporary file, filesystem flush and atomic replace. Reads and writes are protected by an in-process lock.

Missing or malformed state returns a safe reset state. Morning and evening progress are separate.

## Automatic daily reset

Every request is evaluated against the local date in `ROUTINE_TIMEZONE`. When the date changes, prior progress is treated as expired and both routines begin at their first step. No scheduled background job is required.

Configuration:

```text
ROUTINE_TIMEZONE=Europe/Copenhagen
```

Invalid timezone names fall back safely to `Europe/Copenhagen`.

## Roles and privacy

Owner, adult, child and wall-display sessions may read and update routine progress. Anonymous visitors receive:

```json
{"status":"authentication_required","routines":[]}
```

Routine endpoints use the existing validated server session. Query parameters, body roles and headers cannot elevate access.

## CSRF and scoped writes

The progress endpoints are:

```text
POST /api/family/routines/morning/complete
POST /api/family/routines/morning/back
POST /api/family/routines/morning/reset
POST /api/family/routines/evening/complete
POST /api/family/routines/evening/back
POST /api/family/routines/evening/reset
```

They require the existing `X-CSRF-Token`. This exception applies only to the six fixed routine paths. Existing owner-only write APIs keep their existing authorization behavior.

## Pictograms

The pictograms are original, neutral line drawings stored locally in:

```text
app/static/pictograms/routines.svg
```

No external icon service, CDN, tracking URL, base64 image or personal photo is used. Every pictogram is accompanied by text and an accessible label.

## Safe restart

```bash
docker compose up -d --build --force-recreate jarvis-os
```

## Safe API checks

Anonymous privacy check:

```bash
curl -sS http://localhost:8088/api/family/routines
```

An authenticated GET may be checked through the normal browser session. POST checks must include the authenticated session cookie and CSRF token; never paste session values into documentation or source control.

## Reset one routine without deleting other Jarvis data

Use the selected routine reset endpoint from the dashboard. It resets only `morning` or `evening` for the current local date. Do not delete the Jarvis data directory or database.
