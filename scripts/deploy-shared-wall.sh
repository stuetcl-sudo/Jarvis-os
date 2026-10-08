#!/usr/bin/env bash
set -euo pipefail
cd /docker/Jarvis-os
[ -z "$(git status --porcelain)" ] || { echo 'STOP: Der er lokale ændringer i projektet.'; exit 1; }
[ "$(docker inspect jarvis-os --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}')" = /docker/Jarvis-os/docker-compose.yml ] || { echo 'STOP: Uventet Compose-fil.'; exit 1; }
project=$(docker inspect jarvis-os --format '{{index .Config.Labels "com.docker.compose.project"}}')
[ -n "$project" ]
old_commit=$(git rev-parse HEAD)
old_image=$(docker inspect jarvis-os --format '{{.Image}}')
db_path=$(docker exec jarvis-os python -c 'from app.config import DB_PATH; print(DB_PATH)')
[ "$db_path" = /data/jarvis.db ] || { echo 'STOP: Uventet databaseplacering.'; exit 1; }
git fetch origin
new_commit=076fa0b84868d9f4cc8092b8b521c87ebaab33cb
git merge-base --is-ancestor "$new_commit" origin/fix/shared-wall-dashboard
backup="/docker/jarvis-backups/$(date +%Y%m%d-%H%M%S)-shared-wall"
mkdir -m 700 -p "$backup"
cp .env docker-compose.yml "$backup/"
printf '%s\n' "$old_commit" > "$backup/previous-commit.txt"
printf '%s\n' "$old_image" > "$backup/previous-image.txt"
docker tag "$old_image" "jarvis-os:rollback-$(basename "$backup")"
stopped=0
finish() {
  rc=$?
  trap - EXIT
  if [ "$rc" -ne 0 ]; then
    echo 'Opdateringen fejlede. Gendanner tidligere kode og image.'
    docker tag "$old_image" jarvis-os:local || true
    git switch --detach "$old_commit" || true
    if [ "$stopped" = 1 ]; then
      docker compose -p "$project" -f docker-compose.yml up -d --no-deps --force-recreate jarvis-os || echo 'ROLLBACK FEJLEDE: send hele outputtet.'
    fi
  fi
  exit "$rc"
}
trap finish EXIT
git switch --detach "$new_commit"
docker compose -p "$project" -f docker-compose.yml build jarvis-os
new_image=$(docker image inspect jarvis-os:local --format '{{.Id}}')
stopped=1
docker stop --time 30 jarvis-os >/dev/null
docker run --rm -i --network none --read-only \
  --volumes-from jarvis-os \
  --mount "type=bind,source=$backup,target=/backup" \
  "$old_image" python - <<'PY'
import sqlite3
import time
from pathlib import Path
assert Path('/data/jarvis.db').is_file(), 'Database mangler'
source = sqlite3.connect('/data/jarvis.db', timeout=10)
target = sqlite3.connect('/backup/jarvis.db')
try:
    deadline = time.monotonic() + 60
    def progress(status, remaining, total):
        if time.monotonic() > deadline:
            raise TimeoutError("Databasebackup tog mere end 60 sekunder")
    source.backup(target, pages=1024, progress=progress)
    result = target.execute('PRAGMA quick_check').fetchall()
    assert result == [('ok',)], result
    print('Databasebackup OK')
finally:
    target.close()
    source.close()
PY
docker compose -p "$project" -f docker-compose.yml up -d --no-deps --force-recreate jarvis-os
ready=0
for attempt in $(seq 1 30); do
  if curl -fsS --max-time 3 http://127.0.0.1:8088/api/health > "$backup/health.json"; then ready=1; break; fi
  sleep 1
done
[ "$ready" = 1 ]
[ "$(docker inspect jarvis-os --format '{{.Image}}')" = "$new_image" ]
curl -fsS --max-time 5 http://127.0.0.1:8088/login >/dev/null
curl -fsS --max-time 5 http://127.0.0.1:8088/static/js/medication-display.js > "$backup/medication-display.js"
[ -s "$backup/medication-display.js" ]
docker exec jarvis-os python -c 'import sqlite3; from app.config import DB_PATH; c=sqlite3.connect(DB_PATH,timeout=10); print("Konti (brugernavn, navn, rolle, deaktiveret):"); print(*c.execute("SELECT username, display_name, role, disabled FROM auth_users ORDER BY username").fetchall(),sep="\n"); c.close()'
printf '\nProduktion opdateret. Backup: %s\n' "$backup"
cat "$backup/health.json"
printf '\n'
