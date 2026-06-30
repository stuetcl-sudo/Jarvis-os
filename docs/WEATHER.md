# Home Assistant weather

## Architecture

The family dashboard reads weather through this one-way path:

```text
Home Assistant -> Jarvis backend -> family dashboard
```

The browser calls only `GET /api/family/weather`. Jarvis performs the Home Assistant requests on the server, normalizes the response and returns only approved weather fields. The Home Assistant URL, access credential, raw response, authorization header, latitude and longitude are never sent to the browser.

The integration is read-only. It reads the configured weather state and requests a daily forecast. It does not control devices or change Home Assistant state.

## Configuration

Add these values to the local, untracked `.env` file:

```text
HOME_ASSISTANT_URL=""
HOME_ASSISTANT_TOKEN=""
HOME_ASSISTANT_WEATHER_ENTITY=""
HOME_ASSISTANT_TIMEOUT_SECONDS=5
WEATHER_CACHE_SECONDS=300
WEATHER_STALE_SECONDS=3600
```

Required for an active integration:

- `HOME_ASSISTANT_URL`: the base URL of the Home Assistant instance, using `http` or `https`
- `HOME_ASSISTANT_TOKEN`: a Home Assistant long-lived access token
- `HOME_ASSISTANT_WEATHER_ENTITY`: an entity ID beginning with `weather.`

The timeout and cache values must be positive whole seconds. `WEATHER_STALE_SECONDS` must be at least as large as `WEATHER_CACHE_SECONDS`.

Do not commit the local `.env` file. The access token belongs only in that local untracked file.

## Find the weather entity

In Home Assistant:

1. Open **Settings**.
2. Open **Devices & services**.
3. Open **Entities**.
4. Filter the domain to **weather**.
5. Copy the entity ID for the weather provider that should appear on the family dashboard.

Jarvis accepts only an entity ID in the `weather` domain. The dashboard cannot select another entity through a query parameter.

## Create a long-lived access token

In Home Assistant:

1. Open the user profile.
2. Find **Long-Lived Access Tokens**.
3. Create a token for Jarvis.
4. Copy it immediately into `HOME_ASSISTANT_TOKEN` in the local `.env` file.
5. Do not paste it into documentation, shell history, browser storage or source control.

## Restart after configuration

From the Jarvis repository:

```bash
docker compose up -d --build --force-recreate jarvis-os
```

## Safe checks

Check the public normalized endpoint without printing the Home Assistant credential:

```bash
curl -sS http://localhost:8088/api/family/weather
```

Confirm that the container received the variable names without printing their values:

```bash
docker compose config | grep -E 'HOME_ASSISTANT_|WEATHER_'
```

Read recent Jarvis logs:

```bash
docker compose logs --tail=100 jarvis-os
```

Jarvis uses generic weather failure messages and does not intentionally log the access token, configured URL or Home Assistant response body.

## Dashboard states

- `not_configured`: the card shows **Ikke tilsluttet endnu**
- `unavailable`: the card shows **Vejret kan ikke hentes lige nu**
- `stale`: cached weather remains visible with **Viser senest hentede vejrdata**
- `ok`: current weather and up to three daily forecast entries are shown

Successful data is cached for `WEATHER_CACHE_SECONDS`. If a refresh fails, cached data may be reused until it reaches `WEATHER_STALE_SECONDS`.

## Disable the integration

Clear these values in the local `.env` file and recreate the Jarvis container:

```text
HOME_ASSISTANT_URL=""
HOME_ASSISTANT_TOKEN=""
HOME_ASSISTANT_WEATHER_ENTITY=""
```

The family dashboard then returns to the disconnected weather state.
