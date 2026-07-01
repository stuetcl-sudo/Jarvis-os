# Shared family calendar

## Architecture

The family calendar uses this read-only path:

```text
Apple Calendar -> Home Assistant CalDAV -> Jarvis backend -> family dashboard
```

The browser calls only `GET /api/family/calendar`. Jarvis requests events from the configured Home Assistant calendar entities, normalizes them and returns a limited safe response. It never sends the Home Assistant URL, access credential, raw response, descriptions, locations, attendee data, organizer details or calendar entity IDs to the browser.

Jarvis does not create, edit or delete calendar events.

## Configuration

Add the configuration to the local, untracked `.env` file:

```text
HOME_ASSISTANT_URL=""
HOME_ASSISTANT_TOKEN=""
HOME_ASSISTANT_CALENDARS=calendar.example_green|Green calendar|green,calendar.example_blue|Blue calendar|blue,calendar.example_violet|Violet calendar|violet,calendar.example_yellow|Shared calendar|yellow
CALENDAR_LOOKAHEAD_DAYS=7
CALENDAR_CACHE_SECONDS=300
CALENDAR_STALE_SECONDS=3600
CALENDAR_MAX_EVENTS=40
```

Each calendar entry has exactly three parts:

```text
calendar entity|display label|color key
```

Entries are separated by commas. Supported color keys are:

- `green`
- `blue`
- `violet`
- `yellow`

Entity IDs must belong to the `calendar` domain. Labels are short plain text. Duplicate entities, malformed entries and unsupported colors are rejected safely.

The Home Assistant token belongs only in the local `.env` file. Do not commit `.env` or paste the token into documentation, browser storage or shell commands.

## Find calendar entities

In Home Assistant:

1. Open **Settings**.
2. Open **Devices & services**.
3. Open **Entities**.
4. Filter the entity domain to **calendar**.
5. Copy the required `calendar.*` entity IDs into the structured configuration.

All configured calendars are shared with every authenticated Jarvis family role. The labels and colors are attribution only; they are not privacy filters.

## Anonymous privacy

The family dashboard is public. Anonymous users therefore receive only aggregate calendar information:

- number of events today
- number of events in the configured period
- start time of the next event

Anonymous responses contain no event titles, person labels or per-calendar counts. Owner, adult, child and wall-display sessions receive the same normalized shared events.

## Cache and failure states

- `ok`: all configured calendars were read
- `partial`: one or more calendars failed, while other events remain available
- `stale`: all calendars failed and a recent cached result is shown
- `not_configured`: no calendar mapping is configured
- `unavailable`: no usable calendar data is available

Successful and partial results are cached for `CALENDAR_CACHE_SECONDS`. If every calendar fails, cached data may be reused until `CALENDAR_STALE_SECONDS`. The stale period must be at least as long as the cache period.

## Restart after configuration

From the Jarvis repository:

```bash
docker compose up -d --build --force-recreate jarvis-os
```

## Safe endpoint check

This command reads only the normalized Jarvis response and does not print the Home Assistant token:

```bash
curl -sS http://localhost:8088/api/family/calendar
```

With no calendar mapping configured, the endpoint returns HTTP 200 with `not_configured`.

## Disable the integration

Clear the structured mapping in the local `.env` file:

```text
HOME_ASSISTANT_CALENDARS=""
```

Recreate the Jarvis container. The dashboard returns to **Ikke tilsluttet endnu**.

Descriptions and locations are intentionally excluded from the integration and cannot be shown by the family dashboard.
