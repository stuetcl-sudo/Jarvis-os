# Jarvis-os v0.1

Local server assistant for Docker monitoring and basic host health.

## Features

- FastAPI backend
- Simple web UI dashboard on port `8088`
- Docker container list
- Server health: CPU, memory, swap and root disk
- SQLite action log
- Safe mode restart rules

## Safety rules

Jarvis-os v0.1 will only start containers that are already stopped and only when safe mode allows it.

It will never delete volumes, delete containers, prune Docker, change firewall rules, change DNS settings or run arbitrary shell commands.

## Install

1. Clone the repo.
2. Checkout branch `jarvis-v0.1`.
3. Copy `.env.example` to `.env`.
4. Start with Docker Compose.
5. Open `http://SERVER-IP:8088`.

Commands:

```bash
git clone https://github.com/stuetcl-sudo/Jarvis-os.git
cd Jarvis-os
git checkout jarvis-v0.1
cp .env.example .env
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

## API

- `GET /api/health`
- `GET /api/containers`
- `POST /api/containers/{name}/restart`
- `GET /api/actions`

## Status

This is v0.1 foundation code. It is not a fully autonomous agent yet.
