# Indkøb, Energi og Kamera — staging-opdatering

Branch: `feature/home-modules`, baseret på Kæledyr inkl. skjult chipnummer og
dyrlægeoplysninger. Ingen ændring af releaseversion eller produktionsdeployment.

## Indkøb

- Flere lokale lister med oprettelse, omdøbning og sletning.
- Varer med navn, mængde, kategori og note. Redigér, slet, markér købt og fortryd.
- Søgning, gruppering og fjernelse af købte varer. Print af den valgte listes
  ikke-købte varer med listenavn. Sletninger kræver bekræftelse.
- Voksne administrerer lister og varer. Børn kan tilføje og markere varer.
  Wall display har læseadgang via API. Anonyme har ingen adgang.
- Automatisk opdatering hvert 30. sekund, mens Indkøb er åbent. Ikke offline-sync.
- Gemmes i to additive SQLite-tabeller; ingen Home Assistant-afhængighed.
- Eksisterende Home Assistant todo-lister importeres/synkroniseres ikke.

## Energi

Owner vælger sensorer under **Energi → Vælg energisensorer**. Home Assistant skal
først være tilsluttet i Administration. Voksne og wall display kan læse; børn har ingen adgang til energimodulets API.

Kort til: solproduktion og forbrug nu, dagens produktion/forbrug/import/eksport,
batteriprocent, strømpris nu, dagens udgift og salgsindtægt. Manglende sensorer,
utilgængelige tilstande og forkerte enheder vises uden erstatningstal.

W/Wh normaliseres til kW/kWh. Pris understøtter DKK/kr/EUR pr. kWh eller Wh;
beløb understøtter DKK/kr/EUR. NaN og uendelige værdier afvises.
Dagens energikort kræver dagsmålinger, ikke anlæggets levetidstællere. Den aktuelle
strømpris multipliceres aldrig med hele dagens forbrug eller eksport: udgift og
indtægt skal komme fra særskilte korrekt beregnede sensorer.

24 timers historik fra HA Recorder, med valg af måling, minimum/maksimum og
lokale tidsangivelser. Utilgængelige målinger giver brud i grafen. Responsen
begrænses til ca. 400 punkter; minimum/maksimum angår de viste punkter.
Der indsamles ikke egen energihistorik i Jarvis endnu. Hvis Recorder ikke har
historik, vises en tom eller utilgængelig tilstand.

Fox ESS kan levere disse sensorer gennem en allerede konfigureret HA-integration.
Denne opdatering opretter ikke en direkte FoxCloud-forbindelse eller adgang til
Fox ESS-udstyr. Den styrer heller ikke batteri, opladning eller eksport.

## Kamera

Owner vælger op til 12 HA-kameraer under **Kamera → Opsæt kameraer**, med navn og
valgfrie http/https-links til livevisning/optagelser. Scrypted-adressen kan også
angives; den eksisterende `SCRYPTED_URL` fungerer som fallback.

- Kameraoversigt med tilgængelighedsstatus fra HA og tidspunkt for hentet snapshot.
- Snapshots hentes gennem en autentificeret Jarvis-rute fra HA camera_proxy.
  HA-tokenet findes kun på serveren. Kun valgte kameraer kan tilgås.
- Tokenet sendes ikke videre ved HTTP-redirects. Responsen er begrænset til 5 MB
  og JPEG/PNG/WebP. Kortvarig servercache (10 sek.), ingen snapshotfiler på disk.
- Kamera-billeder hentes ved åbning af fanen eller **Opdatér billeder**; ikke
  kontinuerlig streaming eller baggrundsoptagelse.
- Livevisning, optagelser og Scrypted åbnes eksternt og kan kræve eget login.
  Links skal kunne nås fra klienten; en SSH-tunnel til Jarvis giver ikke automatisk
  adgang til en anden tjeneste eller en intern kameraadresse.
- Owner/adult/wall display kan læse kameraer og snapshots; child og anonym
  afvises også på API-niveau. Opsætning er fortsat owner-only.
- Status er tilgængelighed i HA, ikke et selvstændigt ping eller løfte om livefeed.

Ingen komplet NVR, AI-kameraanalyse, Tractive eller direkte FoxCloud i dette trin.

## Datamodel og drift

Lokale lister ligger i `shopping_lists` og `shopping_items`, initialiseret
idempotent ved opstart. Kamera- og energikonfiguration ligger i `app_settings`.
HA-forbindelsen genbruger den eksisterende opsætning, inkl. serverens beskyttede
hemmeligheder. Alle writes kræver CSRF samt korrekt servervalideret rolle.
Den eksisterende `/wall`-visning og produktion berøres ikke af deployment til
`jarvis-staging`. Modulerne har endnu ikke særskilte on/off-knapper eller
individuelle synlighedsregler i den gamle moduladministration.

## Validering

- 94 tests bestået i `.venv`: nye modul-API'er, roller, CSRF, persistens,
  listetilhørsforhold, enheder, NaN, historik, snapshot-allowlist, tokenhåndtering,
  redirect-afvisning, eksisterende pets/tasks/rutiner/wall og staging-konfiguration.
- Browser med isoleret DB og en lokal HA-testserver: opret liste og vare,
  afkryds/fortryd/genindlæs, vælg energisensorer, normalisering/historik,
  kameraopsætning og serverbeskyttet snapshot. Ingen JS-fejl eller side-overflow.
- Visuelt kontrolleret ved 1368×912, 1024×768 og 390×844.
- Browserens målinger og kamera er testdata; ingen adgang til brugerens server
  eller enheder er anvendt til lokal kontrol.
- Node-syntakskontrol og diff-check. Docker-build skal køres på ServerHub;
  Docker er ikke tilgængelig i udviklingsmiljøet.

Diff: nye API-moduler `shopping.py` og `home_modules.py`, HTML/CSS/JavaScript til
de tre sider, tre nye menupunkter, initialisering af indkøbstabeller og målrettet
write-policy i `main_auth.py`. Nye backendtests og opdateret frontend-sikkerhedstest.

API-grundlag verificeret mod Home Assistants officielle REST-dokumentation:
https://developers.home-assistant.io/docs/api/rest/

## Opdater staging på ServerHub

```bash
(
  set -e
  cd /docker/Jarvis-os-ui-staging
  git fetch origin
  git switch feature/home-modules
  git pull --ff-only
  docker compose -p jarvis-staging -f compose.staging.yml up -d --build
  docker compose -p jarvis-staging -f compose.staging.yml ps
)
```

Kontrollér derefter `/login`, `/api/health` og fanerne med SSH-tunnelen åben.
Staging-databasen bevares. Der bruges ingen produktionshemmeligheder.
