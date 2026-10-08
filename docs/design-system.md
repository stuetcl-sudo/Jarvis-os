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
The administration and authentication screens are also separate follow-up work.

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
