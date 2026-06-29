# Jarvis-os v0.1

Local server assistant for Docker monitoring and basic host health.

## What v0.1 does

- FastAPI backend
- Simple web UI dashboard on port `8088`
- Docker container list
- Server health: CPU, memory, swap and root disk
- SQLite action log
- Safe mode restart rules

## Safety rules

Jarvis-os v0.1 will only start containers that are already stopped and only when safe mode allows it.

It will never delete volumes, delete containers, prune Docker, change firewall rules, change DNS settings or run arbitrary shell commands.

Protected containers are never restarted automatically. By default these are:

```env
jarvis-os,adguardhome,caddy,gluetun
```

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

Open:

```text
http://SERVER-IP:8088
```

On the local LAN this may be:

```text
http://192.168.68.135:8088
```

## Update later

```bash
cd /docker/jarvis
git pull
docker compose up -d --build
```

## Configuration

Important `.env` values:

```env
SAFE_MODE=true
ALLOW_RESTART_STOPPED=true
ALLOWED_RESTART_CONTAINERS=
PROTECTED_CONTAINERS=jarvis-os,adguardhome,caddy,gluetun
DB_PATH=/data/jarvis.db
```

Use `PROTECTED_CONTAINERS` for critical services that Jarvis must not restart.

Use `ALLOWED_RESTART_CONTAINERS` if Jarvis should only be allowed to start selected containers.

Example:

```env
ALLOWED_RESTART_CONTAINERS=homebridge,filebrowser,glances
```

## API

- `GET /api/health`
- `GET /api/containers`
- `POST /api/containers/{name}/restart`
- `GET /api/actions`

## Status

This is v0.1 foundation code. It is not a fully autonomous agent yet.

Next target: v0.2 system agent with scheduled checks, memory, and smarter self-healing rules.
