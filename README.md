# Jarvis-os v0.2

Jarvis-os is a local server assistant for Docker monitoring, system health and safe self-healing.

v0.2 changes Jarvis from a simple dashboard into a real background assistant. The worker runs every 60 seconds even when the browser is closed.

## v0.2 features

- Background worker every 60 seconds
- Mission Control UI on port `8088`
- Docker container monitoring
- Host health checks: CPU, RAM, swap and root disk
- Service classification: critical, optional and stopped-by-design
- SQLite action log
- SQLite incidents table
- Safe optional container auto-start
- API endpoints for Mission Control, incidents and worker status

## Safety model

Jarvis-os v0.2 is safety-first.

It may auto-start stopped optional containers only when all of these are true:

- `SAFE_MODE=true`
- Container is not protected
- Container is listed in `ALLOWED_AUTO_START_CONTAINERS`
- Container has not failed more than 3 times inside 30 minutes

Jarvis must never auto-start:

- `gluetun`
- `qbittorrent` unless `gluetun` is running
- Protected containers

Jarvis does not contain destructive actions. It does not delete files, delete containers, delete Docker volumes, prune Docker, change firewall rules, change DNS settings or run arbitrary shell commands.

All allowed, denied, skipped and failed automated actions are logged.

## Default service classes

### Critical services

```env
CRITICAL_SERVICES=jarvis-os,adguardhome,caddy,homeassistant
```

Critical services create active incidents when they are not running. Jarvis does not auto-start protected services.

### Protected containers

```env
PROTECTED_CONTAINERS=jarvis-os,adguardhome,caddy,gluetun
```

Protected containers are never auto-started.

### Optional services

```env
OPTIONAL_SERVICES=sonarr,radarr,readarr,prowlarr,jellyfin,filebrowser,glances
```

Optional services may be auto-started only if they are also listed in `ALLOWED_AUTO_START_CONTAINERS`.

### Stopped-by-design services

```env
IGNORED_SERVICES=
```

Use this for containers that are normally stopped. Jarvis shows them separately and skips self-healing.

## Recommended install on Dennis' server

Use `/docker/jarvis` so it matches the rest of the server layout.

```bash
cd /docker
git clone https://github.com/stuetcl-sudo/Jarvis-os.git jarvis
cd jarvis
git checkout jarvis-v0.1
cp .env.example .env
docker compose up -d --build
```

Open Mission Control:

```text
http://SERVER-IP:8088
```

On the local LAN this may be:

```text
http://192.168.68.135:8088
```

## Update commands

```bash
cd /docker/jarvis
git checkout jarvis-v0.1
git pull
docker compose up -d --build
```

## Configuration

Important `.env` values:

```env
SAFE_MODE=true
ALLOW_RESTART_STOPPED=true
WORKER_ENABLED=true
WORKER_INTERVAL_SECONDS=60
CRITICAL_SERVICES=jarvis-os,adguardhome,caddy,homeassistant
PROTECTED_CONTAINERS=jarvis-os,adguardhome,caddy,gluetun
OPTIONAL_SERVICES=sonarr,radarr,readarr,prowlarr,jellyfin,filebrowser,glances
IGNORED_SERVICES=
ALLOWED_AUTO_START_CONTAINERS=sonarr,radarr,readarr,prowlarr,jellyfin,filebrowser,glances
AUTO_START_FAILURE_LIMIT=3
AUTO_START_FAILURE_WINDOW_MINUTES=30
DB_PATH=/data/jarvis.db
```

Recommended first run:

```env
SAFE_MODE=true
WORKER_ENABLED=true
ALLOWED_AUTO_START_CONTAINERS=filebrowser,glances
```

When the system has proven stable, add more optional services to `ALLOWED_AUTO_START_CONTAINERS`.

## API

- `GET /api/mission`
- `GET /api/incidents`
- `GET /api/worker/status`
- `POST /api/worker/run-once`
- `GET /api/health`
- `GET /api/containers`
- `POST /api/containers/{name}/restart`
- `GET /api/actions`

## Validation

Run:

```bash
bash scripts/validate.sh
```

The script checks Python imports, FastAPI app loading and Docker Compose config.

## Status

This is v0.2 foundation code for a real background assistant. It is still intentionally conservative and does not include broad autonomous control.
