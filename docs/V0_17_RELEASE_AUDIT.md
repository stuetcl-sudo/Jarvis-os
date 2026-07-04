# Jarvis-os v0.17 release audit

This checklist is for the private home release track before v1.0.

Goal:

```text
Familie først.
Teknik bagefter.
Farlige ting låst.
```

v0.17 is not a feature release. It is a stability, privacy, and demo-readiness checkpoint.

## Scope

v0.17 should prove that the current family, wall, admin, role, action, and privacy model is stable enough to keep building toward v1.0.

Do not add these during v0.17.2:

- new dashboard modules
- camera live view
- AI or voice control
- layout editor
- public install cleanup
- automatic dangerous actions

## Required command checks

Run from the repository root:

```bash
source .venv/bin/activate

PYTHONPATH=. python tests/test_family_visibility.py
PYTHONPATH=. python tests/test_family_api_visibility.py
PYTHONPATH=. python tests/test_auth_roles.py
PYTHONPATH=. python tests/test_family_role_views.py
PYTHONPATH=. python tests/test_wall_dashboard.py
PYTHONPATH=. python tests/test_screen_module_layout.py
PYTHONPATH=. python tests/test_frontend_safety.py
PYTHONPATH=. python tests/test_calendar_integration.py
PYTHONPATH=. python tests/test_weather_integration.py

bash scripts/privacy_check.sh
bash scripts/validate.sh
```

Release status is not green unless all commands pass.

## Admin demo flow

1. Log in as owner.
2. Open `/admin#users`.
3. Confirm the page shows:
   - `Hvem må se hvad?`
   - `Hvem må ændre hvad?`
4. Confirm owner controls are locked and owner still sees everything.
5. Toggle child visibility for calendar, weather, meal, tasks, and safety.
6. Toggle child task actions:
   - task add
   - task complete
   - task edit
   - task remove
7. Save visibility and action settings.
8. Refresh the page and confirm the saved values persist.

## Family role demo flow

Test these roles separately:

- owner
- adult
- child
- wall_display

For each role:

1. Open `/`.
2. Confirm the visible cards match admin visibility rules.
3. Confirm technical status is hidden for adult, child, and wall display.
4. Confirm owner can access `/admin`.
5. Confirm adult, child, and wall display cannot access `/admin`.
6. Confirm the wall display does not expose a private display name.

## API privacy demo flow

When a role is not allowed to see a feature, the API must return a quiet hidden payload instead of data.

Expected examples:

```text
/api/family/calendar      -> status: hidden, no events
/api/family/weather       -> status: hidden, no forecast
/api/family/meal-plan     -> status: hidden, no days
/api/family/tasks         -> status: hidden, no lists, no task actions
/api/family/safety-status -> status: hidden, labels hidden
```

Task write requests must also be blocked if tasks are hidden for the role, even when the CSRF token is valid.

## Wall demo flow

1. Open `/wall` without login.
2. Confirm redirect to `/login?next=/wall`.
3. Log in as a wall display user.
4. Open `/wall`.
5. Confirm the wall dashboard loads without technical details.
6. Confirm safety status updates calmly.
7. Confirm screen-specific visibility options still apply.
8. Confirm no admin link is shown unless enabled and the user is owner.

## Frontend safety requirements

Frontend code must not introduce:

```text
innerHTML
insertAdjacentHTML
outerHTML
document.write
eval
localStorage
sessionStorage
inline event handlers
```

Same-origin fetches must explicitly preserve credentials.

Admin writes and family writes must preserve CSRF handling.

## Privacy requirements

The privacy check must stay green.

Do not add broad allowlists just to silence the scanner.

False positives should be fixed in the scanner rules when possible.

## Release decision

v0.17 is green when:

- full validation passes
- family visibility works in both UI and API
- task action permissions work per role
- wall screen is calm and non-technical
- admin remains owner-only
- no private tokens or personal setup data are committed
- no unsafe frontend sinks are introduced

## Next after v0.17

Preferred next private-home track:

```text
v0.17.3 — Demo-klar wall/family
```

Public install readiness belongs later:

```text
v1.1 — Andre hjem
```
