# Shared family week and meals

The main family application has a shared Ugeoversigt tab for today and the next
six days, using the home's configured timezone. It combines existing read-only
Home Assistant calendar and meal snapshots with local family plans. Adults and
owners can edit; children and wall accounts can read the API. Anonymous users
cannot read plans. The dedicated wall screen retains its existing layout.

Each day's local plan stores a meal title, cook's name, recipe link, ingredients,
meal notes, pickup name/time/notes and up to 20 reminders. Names are free text,
with suggestions from active family accounts; they do not assign permissions or
send notifications. Recipe links accept HTTP/HTTPS, reject embedded credentials,
and open with noopener/noreferrer. The server does not fetch recipe URLs.

A local meal title overrides the Home Assistant title for that day in the
shared overview, week and meal tab. Clearing it restores the integration title.
Recipes, ingredients and other details are kept in the full tabs. The homepage
shows today's meal plus a small Husk i morgen card: at most three reminders,
pickup details or tomorrow's calendar entries, with a link to the full week.
No tomorrow meal is added to today's meal card. No automatic medication,
packing, homework or pickup inference is made.

Calendar information is limited to its configured lookahead and event cap.
The week labels missing integrations, stale data and days outside the fetched
calendar range instead of claiming that a disconnected calendar is empty.
Meal data is requested for up to seven days, bounded by the integration's own
lookahead; missing days are explicitly labelled. Calendar end times are exclusive,
including midnight and all-day events.

Local data lives in an additive `family_plans(day,payload)` SQLite table.
Initialization is repeatable and preserves existing plans. Writes use adult
role checks and CSRF; responses are no-store. Inputs have bounded fields/lists
and validate dates, pickup times and recipe links. Old plans remain stored.

Adults can send saved ingredients to a chosen local shopping list. The operation
runs in a single BEGIN IMMEDIATE transaction, checks the 500-item limit before
inserting and skips case-insensitive matches among unchecked items. Matching is
by the full ingredient text; it does not combine quantities. Checked ingredients
can be added again for another shopping trip. This does not write to HA lists.

Family accounts use a shared greeting. Roles continue to determine access to
administration, medication, energy, camera and finance. Person selectors choose
the subject of a routine or medication registration, not a separate dashboard.

## Validation

Browser checks use a temporary local database with the worker disabled, safe
mode enabled and fixture calendar/meal responses. They verify saved daily plans,
tomorrow's summary, recipe links, editing from the meal tab, shopping transfers
and repeated imports, shared child read-only access, reload and no horizontal
overflow at 1368x912, 1024x768 and 390x844. They do not verify a live HA connection
or deployment on ServerHub. Docker staging must be built/tested separately.

89 focused Python tests passed, covering planning, family roles/visibility,
module settings, calendar, meals, auth, frontend safety, daily care, routines and
home modules. JavaScript syntax and git diff checks passed. The staging script's
configuration check passed, then stopped because Docker is unavailable locally;
ServerHub staging and production were not deployed by this session.
