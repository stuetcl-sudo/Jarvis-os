# Home Assistant weather

## Architecture

The family dashboard reads weather through this one-way path:

```text
Home Assistant -> Jarvis backend -> family dashboard
```

The browser calls only `GET /api/family/weather`. Jarvis performs the Home Assistant requests on the server, normalizes the response and returns only approved weather fields. The Home Assistant URL, access credential, raw response, authorization header, latitude and longitude are never sent to the browser.

The integration is read-only. It reads the configured weather state, requests a daily forecast and optionally reads one UV sensor state. It does not control devices or change Home Assistant state.

## Configuration

Add these values to the local, untracked `.env` file:

```text
HOME_ASSISTANT_URL=""
HOME_ASSISTANT_TOKEN=""
HOME_ASSISTANT_WEATHER_ENTITY=""
HOME_ASSISTANT_UV_ENTITY="sensor.openuv_current_uv_index"
HOME_ASSISTANT_TIMEOUT_SECONDS=5
WEATHER_CACHE_SECONDS=300
WEATHER_STALE_SECONDS=3600
```

Required for an active integration:

- `HOME_ASSISTANT_URL`: the base URL of the Home Assistant instance, using `http` or `https`
- `HOME_ASSISTANT_TOKEN`: a Home Assistant long-lived access token
- `HOME_ASSISTANT_WEATHER_ENTITY`: an entity ID beginning with `weather.`

Optional UV configuration:

- `HOME_ASSISTANT_UV_ENTITY`: a sensor entity beginning with `sensor.`
- the default is `sensor.openuv_current_uv_index`, provided by the existing Home Assistant OpenUV integration
- an unavailable or invalid UV sensor does not make weather unavailable; the UV value is simply omitted

The timeout and cache values must be positive whole seconds. `WEATHER_STALE_SECONDS` must be at least as large as `WEATHER_CACHE_SECONDS`.

Do not commit the local `.env` file. The access token belongs only in that local untracked file.

## Find the weather and UV entities

In Home Assistant:

1. Open **Settings**.
2. Open **Devices & services**.
3. Open **Entities**.
4. Filter the domain to **weather** and copy the weather provider entity ID.
5. For UV, confirm that `sensor.openuv_current_uv_index` exists, or copy another OpenUV current-index sensor into `HOME_ASSISTANT_UV_ENTITY`.

Jarvis accepts only a weather entity in the `weather` domain and a UV entity in the `sensor` domain. The dashboard cannot select other entities through query parameters.

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

## Public UV field

The normalized response may include:

```text
uv_index
```

Jarvis accepts the UV sensor state only when it is present, numeric, finite and greater than or equal to zero. Missing, empty, boolean, negative, NaN, infinity and invalid values become `null`. A real numeric value of `0` remains valid.

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

To disable only UV display, set:

```text
HOME_ASSISTANT_UV_ENTITY=""
```

The family dashboard then returns to the disconnected weather state when the required weather values are cleared.
