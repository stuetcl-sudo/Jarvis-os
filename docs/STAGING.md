# Isolated staging environment

Jarvis staging has its own Compose project, container, loopback port, network, volume, and SQLite database. It does not mount the host Docker socket and cannot inspect or control production containers.

## Prepare

```bash
cp .env.staging.example .env.staging
```

Review the ignored file before use. Do not add production credentials, Home Assistant tokens, or production passwords.

Run local validation without Docker:

```bash
COMPOSE_PROJECT_NAME=jarvis-staging bash scripts/validate_staging.sh
```

## Start and validate later

```bash
docker compose --file compose.staging.yml --project-name jarvis-staging config
docker compose --file compose.staging.yml --project-name jarvis-staging up -d --build jarvis-os
COMPOSE_PROJECT_NAME=jarvis-staging bash scripts/validate_staging.sh --with-docker
```

The wrapper refuses port 8088, requires project `jarvis-staging`, and gives every Compose call the staging file and project name explicitly.

## Stop and clean up

Preserve the staging database:

```bash
docker compose --file compose.staging.yml --project-name jarvis-staging down
```

Delete the separate staging database as well:

```bash
docker compose --file compose.staging.yml --project-name jarvis-staging down --volumes --remove-orphans
```

The second command permanently deletes staging data. Verify its explicit file and project name first.

## Security boundaries

- Staging binds only to `127.0.0.1:8098`; production remains on 8088.
- Data lives in `jarvis_staging_data` at `/data/jarvis-staging.db`.
- No production volume, `.env`, login, or external-integration secret is referenced.
- The Docker socket is not mounted.
- `SAFE_MODE=false`, restart allowlists are empty, and the worker is disabled.
- `.env.staging` is ignored; `.env.staging.example` contains no secrets.

Authenticated live Docker inventory and Action Engine integration checks cannot run without a Docker API. If needed later, add a fake Docker API with fixture data as separate work. Never connect staging to the production Docker socket.
