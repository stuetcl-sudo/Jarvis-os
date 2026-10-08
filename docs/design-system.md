# Jarvis family application design

Approved direction: Dennis's pet dashboard reference, 7 October 2026. This
supersedes the earlier navy-first direction for the family application.

## Visual language

- Pale neutral background, white cards, subtle borders and soft shadows.
- Green selected states and primary actions, with restrained pastel accents.
- Dark readable text, clear headings, generous spacing and rounded cards.
- Consistent outline icons; no new icon libraries are required for the shell.
- Desktop/tablet navigation in a left sidebar. Small screens use horizontally
  scrollable module links, without squeezing desktop columns onto a phone.
- Controls should have at least 44px touch targets. Preserve keyboard focus and
  accessible labels. Do not rely on color alone for status.
- Verify at Surface's 1368×912 viewport, iPad 1024×768 and a narrow phone width.

## Structure and extension

`app/static/css/app-shell.css` owns the scoped light theme and navigation layout.
`app/static/js/app-shell.js` owns module navigation, active state and URL hashes.
Existing module code still owns data loading, validation and mutation behavior.

Navigation presents one module at a time. Existing cards stay in the DOM so
refreshes and forms keep their existing state; routing uses a separate CSS class
rather than taking ownership of modules' `hidden` loading/permission states.
Back/forward navigation and reloads restore the selected section. Unknown or
unavailable destinations fall back to Overblik. The sidebar is built only from
available cards, respecting the server-rendered role/module visibility.

Current sections: Overblik, Kalender, Opgaver, Rutiner, Madplan, Hjemmet, Vejr,
and owner-only System where available. Administration remains an owner-only
server route. Kæledyr now has a local profile, care and reminder module; see
`docs/pets.md`. Indkøb, Energi and Kamera now have functional module views;
see `docs/home-modules.md`. Tractive and direct FoxCloud integration remain
future work. Energy and camera data currently use Home Assistant.

New modules should reuse this shell, the scoped color variables, card treatment
and navigation behavior. Add real integration states (loading, unconfigured,
unavailable, empty, ready); never replace missing data with plausible numbers.
Use textContent for data. Navigation must never grant API permissions.

The dedicated `/wall` dashboard retains its existing screen-specific behavior
in this first bounded change. A later wall redesign needs explicit visual checks
of fullscreen, screen profiles and routines before adopting the new shell.
Administration now shares the family appearance; see the October 2026 follow-up
below. Authentication screens remain separate follow-up work.

## Rollout

Start with the shared shell and existing sections, then build individual modules
inside it. Follow up with a compact summary-only overview as integrations land.
Do not copy the mockup's family names, veterinary records, dates or encryption
claim into production as if they were actual data or verified capabilities.

This change does not change the release number or authorize a production
deployment. Run local tests and Docker staging before proposing a release.

## Validation of the first shell change

- 78 focused Python tests passed in `.venv` (roles, visibility, modules, frontend
  safety, wall dashboard, tasks, routines, calendar and staging configuration).
- `node --check app/static/js/app-shell.js` and `git diff --check` passed.
- The application started locally on 127.0.0.1:8098 with a temporary database,
  SAFE_MODE/DRY_RUN enabled and the worker disabled. This is not Docker staging.
- `scripts/staging.sh test` passed its Python configuration check, then stopped
  because Docker is unavailable. No ServerHub staging deployment was performed.
- Browser layout/navigation testing remains pending: Chromium is absent and its
  download failed. Before release, verify module selection, back/forward,
  reload, hidden modules, keyboard navigation and all three target viewports.
- Dennis approved committing and pushing this feature branch on 7 October
  2026. Production deployment is not approved; production has not been modified.

## Daily summaries and personal care

The main application's Overblik now uses compact summary links rather than full
module cards. Summaries focus on today; future dates belong in their module tabs.
New modules should provide a short truthful summary using their existing
permission checks. Keep detailed forms, histories and charts off the home screen.
Medication editing is adult-only; wall accounts have a read-only today summary.
Financial records are
adult-only. See `docs/daily-care.md` for recurring pet reminders, pet expenses
and the shared adult medication tracker.

## Family colors and shared planning

Dennis requested more color and icons on 7 October 2026. Summary cards now use
soft module-specific colors with a darker top border and matching outline icon:
blue calendar, amber routines, peach meals, pink medication, cyan weather and
purple tomorrow reminders. Text and symbols accompany colors. Planning reuses
inline outline SVGs rather than depending on emoji fonts or a new icon library.
The shared Ugeoversigt and expanded meal tab follow the same card and touch
controls. See `docs/family-planning.md`. The family greeting is shared; role
permissions and person selectors remain intact.

## Family progress and attention

Belønningstavle and Dagsform extend the main shared shell with small status cards
and separate full tabs. Use voluntary, clearly labelled inputs and avoid points
for mood or medication. Missing medicine registration may use a red card and a
slow border pulse; keep text readable, offer an animation preference and respect
reduced motion. Never interpret its color as clinical severity. See
`docs/family-progress.md` for roles, storage and validation.

## Unified family and admin appearance — October 2026

Follow-up branch: `feature/unified-design-theme`, based on `fix/quick-wellbeing`.
The light reference remains the default visual language; dark mode uses navy
surfaces, soft green controls and lighter module accents. Text accompanies status
colors. Existing missing-medication attention/pulse and reduced-motion behavior
are preserved. This is a presentation change; no release version or production
deployment is included.

### Ownership and extension

- `design-tokens.css` owns the shared semantic colors for light/dark surfaces,
  text, borders, selected states, warnings and danger, with aliases for existing
  family/admin widgets. It loads after legacy page styles.
- `unified-design.css` owns the shared cards, touch controls, dialog surfaces,
  typography, sidebars and responsive adjustments. Scope new rules to
  `.jarvis-app` or `.jarvis-admin`; use the tokens rather than fixed white paints.
- `theme.js` sets appearance in the head before paint and supplies shared outline
  icons. `app-shell.js` still owns family navigation and existing admin scripts
  still own their tabs, forms, state and authorized actions.
- Family overview, week, calendar, tasks, routines, meals, shopping, medication,
  rewards, wellbeing, pets, energy, cameras, home, weather and owner system views
  now share these styles. All seven admin areas, dynamic user/screen forms,
  connection setup and status panels use the same primitives.
- The module list scrolls independently on desktop; theme/account controls stay
  visible. Phones retain a horizontal module list and stacked content. The
  dedicated `/wall` retains its screen profiles and separate layout. Login and
  first-run setup remain their separate flows.

### Theme preference

The sidebar offers Lyst, Mørkt and Følg enhed. The default is Følg enhed (light
fallback). Explicit themes override OS appearance; system mode reacts to OS
changes. `jarvis.appearance` is saved in browser localStorage, reused across
family/admin and synchronized between tabs. This is a device/browser setting,
not a family database preference; devices can use different themes. If storage
is blocked, the current page still switches and the next load follows the OS.
Unknown stored values fall back safely. No login tokens or household data are
stored by this preference. A CSS light fallback also works if theme JS fails.

Admin stays owner-only. Family role visibility and action permissions, CSRF,
session protections, no-store data endpoints and voluntary shared check-ins are
unchanged. Theme choice does not grant access to a hidden module.

### Validation

- 68 Python tests passed in `.venv`: admin UI, frontend safety/foundation,
  family/auth roles, shared wall, progress and dedicated wall behavior.
- Five Node tests passed (four theme cases plus the medication-attention suite),
  including blocked storage, invalid preferences, OS changes and tab synchronization.
- Chromium checked 138 family/admin layouts: 16 family destinations and seven
  admin tabs × two themes × Surface 1368×912, tablet 1024×768 and phone 390×844.
  It verified navigation, absence of horizontal page overflow, reload/system/theme
  persistence, cross-tab updates, shopping writes and dark medication dialog surfaces.
- Additional populated views used explicit synthetic read fixtures for calendar,
  tasks, weather, energy, cameras and admin status. Real temporary-DB writes
  exercised shared wellbeing; child/wall admin restrictions were checked directly.
  No live household records or production integrations were used. Local Docker
  status was unavailable, so normal admin status was reviewed with test fixtures.
- JavaScript syntax and diff checks passed. `scripts/staging.sh test` passed the
  staging configuration check, then stopped because Docker is not installed.
  ServerHub staging still requires a build and a review with actual household data.

### ServerHub staging update

```bash
(
  set -e
  cd /docker/Jarvis-os-ui-staging
  git fetch origin
  git switch --detach origin/feature/unified-design-theme
  docker compose -p jarvis-staging -f compose.staging.yml up -d --build
  curl -fsS http://127.0.0.1:8098/api/health
)
```

Use the existing SSH tunnel to open http://localhost:8098. Test both themes in
family and admin, and a wall account's shared family board. Port 8088 production
requires separate deployment approval.

### Approved production deployment

Dennis separately approved production on 8 October 2026. The helper
`scripts/deploy-unified-design.sh` pins UI commit
`b488e296e6f71f54f1046342afc860f5d8e58633`, rather than deploying a moving branch.
It checks the production Compose identity and clean working tree, saves the old
image/code reference and `.env`/Compose configuration, builds only Jarvis, then
stops it to archive the entire data volume and create a checked SQLite backup.
The backup container uses a separate 256 MB temp filesystem and puts SQLite
temporary files in the backup directory, avoiding the earlier full `/tmp` issue.

Only Jarvis is recreated with `--no-deps`; the socket proxy and other services
are not restarted. Health, running image ID, exact theme asset hashes and database
readability are checked. Failure restores the old code/image, preserving database
contents; automatic rollback does not restore the data archive or undo migrations.

SSH from this workspace failed with `Network is unreachable`. No production
command has been executed by Codex. Syntax and five simulated deployment cases
passed locally (success, dirty checkout, build failure, backup failure, bad served
asset); this is not a real Docker execution. Run the reviewed helper in Dennis's
ServerHub SSH session and inspect the resulting output before claiming success.

## Compact daily board — 8 October 2026

`feature/compact-dashboard-energy` reduces overview padding, headings and empty
card height, keeping 44px touch targets. Routine completion and person controls
share a row when space allows. Secondary summaries use five columns on Surface;
smaller screens wrap naturally, without cropping content or hiding medication
attention. Larger families and more medication entries may still need scrolling.

Dagsform on the overview shows every visible person directly: three face choices
and three battery levels, each with a short label. Icons are inline SVG so they do
not depend on emoji fonts. There is no person-selection step or Save button.
The existing authorized, queued server writes, accessible pressed state, rollback
on failed saving and optional mood/energy fields are retained. The full Dagsform
tab still offers removal of today's answer. A saved family meal stays visible
even if the separate Home Assistant meal integration is unavailable.

The owner can select Energi → Vælg visning independently of sensor setup. The
shared database setting `family.home_modules.energy_display` selects metrics in
the Energy tab and an optional explicit overview metric. Default/null visibility
shows only configured sensors; an empty selection is an intentional empty view.
An explicitly selected unavailable main metric is labelled unavailable, rather
than replaced with another metric. Unselected metrics stay accessible to their
existing authorized APIs; display selection is presentation, not permissions.
Older configuration clients preserve the display preference when they omit it.

Validation: 61 Python tests passed (home modules, progress, frontend, roles,
shared wall and admin) and five Node theme/medication tests passed. Local Chromium
checks use a temporary database and explicit synthetic energy values: shared
selection, one-click mood and energy, rapid taps, reload persistence, failed-save
rollback, six light/dark layouts (1368×912, 1024×768, 390×844), no horizontal
overflow and touch targets. No live Home Assistant data was used. Docker is not
installed here: the staging configuration check passed, but the Docker build and
ServerHub staging review remain outstanding. Production has not been changed.

Staging update:

```bash
(
  set -e
  cd /docker/Jarvis-os-ui-staging
  git fetch origin
  git switch --detach origin/feature/compact-dashboard-energy
  docker compose -p jarvis-staging -f compose.staging.yml up -d --build
  curl -fsS http://127.0.0.1:8098/api/health
)
```
