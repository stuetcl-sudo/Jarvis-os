# Kæledyr — første udgave

Kæledyr åbnes via venstremenuen (`/#kaeledyr`). Data gemmes i Jarvis' eksisterende
SQLite-database og kræver hverken Home Assistant eller Tractive.

## Funktioner

- Flere kæledyr med navn, foto, race/dyreart, fødselsdato, chipnummer og vægt.
- Chipnummer er skjult på profilkortet, indtil man vælger "Vis chipnummer".
  Dette er visuel diskretion; autoriserede familiemedlemmer har stadig API-adgang.
- Dyrlægens navn, klinik og telefonnummer kan gemmes på profilen. Gyldige
  telefonnumre vises som ringelinks. Ældre profiler kræver ingen datamigrering.
- Opret, rediger og slet profiler. Sletning kræver bekræftelse og fjerner dyrets
  tjeklister og påmindelser i samme transaktion.
- Lokal JPEG/PNG-upload, nedskaleret til højst 720 pixels og gemt i databasen.
  Ingen eksterne billedlinks. HEIC er ikke understøttet i denne udgave.
- Daglig tjekliste: mad, vand og gåtur. Et flueben kan fortrydes. Datoen følger
  hjemmets tidszone. Dette er ikke en tæller for fodringer/ture eller en GPS-log.
- Sundhedspåmindelser: vaccination, medicin, dyrlæge eller andet, med dato og noter.
  Opret, rediger, markér klaret, fortryd og slet. Overskredne datoer vises tydeligt.
- Påmindelser vises i appen; ingen pushbeskeder, gentagelsesregler eller automatisk
  medicindosering. Indhold og datoer indtastes af familien.
- Oversigten viser antal dyr og en genvej til modulet. Tomme installationer har
  ingen forudfyldte personer, dyr eller medicinske oplysninger.

## Roller og API

| Rolle | Læs | Daglig pasning | Profiler og sundhed |
|---|---|---|---|
| Owner/adult | Ja | Ja | Opret/rediger/slet |
| Child | Ja | Markér/fortryd | Kun læsning |
| Wall display | API-læsning | Nej | Kun læsning |
| Anonym | Nej | Nej | Nej |

Den dedikerede wall-side er uændret. Kæledyr har endnu ikke en særskilt
aktiveringsknap i moduladministrationen eller rollebaserede synlighedsindstillinger.
Alle autentificerede familiemedlemmer kan læse oplysningerne, inkl. chipnummer.

API: `/api/family/pets`, `/{id}`, `/{id}/care/{food|water|walk}` og
`/{id}/reminders[/{reminder_id}]`. Alle writes har servervalideret rolle og CSRF.
Ukendte felter afvises. Der gemmes højst 30 dyr og 200 påmindelser pr. dyr.

Tre additive tabeller (`pets`, `pet_care`, `pet_reminders`) initialiseres idempotent
ved opstart. Eksisterende bruger- og familieoplysninger ændres ikke. Fotos indgår
nu i databasebackup. Kæledyrsdata er ikke krypteret separat af denne funktion.

## Review og validering

- 84 fokuserede tests bestået i `.venv`. Backendtests dækker roller, manglende/forkert CSRF, inputvalidering,
  persistens, gentagen initialisering, dato-skift, idempotente flueben,
  fortrydelse, påmindelser på tværs af dyr og sletning af afhængige data.
- Browserkontrol med isoleret testdatabase: oprettelse med foto, daglig pasning,
  påmindelse, genindlæsning, navigation samt 1368×912, 1024×768 og 390×844.
- Fotos og navne i browserkontrollen er udelukkende testdata.
- JavaScript-syntakskontrol og `git diff --check` bestået.
- Staging-scriptets konfigurationstest bestået; Docker-build blokeret lokalt
  af manglende Docker. Docker-staging på ServerHub skal stadig køres, før
  ændringen kan releases.
- Ingen produktionsændring eller releaseversionsændring.

Ændringsoversigt: ny `app/pets.py` med datamodel/API; additive tabeller via
`app/db.py`; router og afgrænset write-policy i `app/main_auth.py`; ny HTML,
CSS, JavaScript og SVG-ikoner; rollebegrænset indsættelse i familievisningen;
Kæledyr aktiveret i menuen; backendtests og frontend-sikkerhedskontrol.
