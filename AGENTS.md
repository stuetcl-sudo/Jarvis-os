# Jarvis-os working agreement

- Check git status and branch before edits; use a feature branch, never main.
- Keep changes small and reviewable. Run local tests with `.venv`.
- Build and test with `compose.staging.yml`, project `jarvis-staging`, port
  `127.0.0.1:8098`. Keep its separate database, volume and network; no Docker
  socket or production secrets. Report explicitly when staging is unavailable.
- Show the diff and test results before requesting approval to commit/push.
- Commit and push only with explicit user approval.
- Production on ServerHub (`/docker/Jarvis-os`, port 8088) must never be changed,
  restarted or deployed without explicit, separate user approval.

## UI work

Read `docs/design-system.md` before changing the family application UI. The
approved reference is the light pet dashboard supplied by Dennis on 2026-10-07.
Use the shared application shell and theme for new modules. Keep role checks,
module visibility, CSRF and session protections intact. Do not fabricate live
integration data or imply planned features already work.
