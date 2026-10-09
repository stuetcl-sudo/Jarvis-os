# Jarvis som app, telefonbeskeder og lyd

Første version findes på `feature/jarvis-pwa-notifications`. Den tilføjer fanen **Beskeder** til ejer, voksen og vægskærm. Push er frivilligt, deaktiveret for hjemmet som standard og bruger Jarvis' egen database og baggrundsopgave. Home Assistant er ikke involveret.

## Brug

1. Åbn Jarvis via hjemmets **HTTPS-adresse**. Almindelig LAN-adgang over HTTP understøtter ikke telefonpush. På iPhone: Safari → Del → Føj til hjemmeskærm; åbn derefter Jarvis-ikonet. iPhone kræver iOS 16.4 eller nyere.
2. Ejeren åbner **Beskeder**, angiver kontaktmail og aktiverer telefonbeskeder for hjemmet. Kontaktmailen bruges i VAPID-afsenderoplysninger; den sender ikke e-mail.
3. På telefonen vælges personer, stilleperiode og eventuelt én gentagelse efter 15, 30 eller 60 minutter. Tryk **Tillad telefonbeskeder**, og acceptér telefonens tilladelse. Ingen personer er valgt som standard.
4. Tryk **Send testbesked** og kontrollér faktisk modtagelse på telefonen. »Accepteret« betyder, at push-tjenesten har accepteret beskeden, ikke at telefonen har vist den.
5. På vægskærmen kan **Aktivér lyd og afspil test** slå et diskret ding til. Lyd kræver brugerens klik efter åbning og fungerer kun, mens Jarvis er åbent og synligt. Vælg personer og gem valgene først.

Push sendes for dagens planlagte medicin, som mangler registrering. Første besked sendes ved eller efter tidspunktet, og den valgte gentagelse regnes fra første accepterede afsendelse. Der er højst én gentagelse. Medicin registreret som taget eller oversprunget stopper kommende beskeder. Beskeden åbner medicinoversigten og foretager ingen afkrydsning.

Stilleperioder og medicintidspunkter følger hjemmets tidszone; samme start/slut deaktiverer stilleperioden. Der sendes højst to timer efter medicinens planlagte tidspunkt, også efter serverens nedetid. Telefonpush og skærmlyd husker hver især afsendelser/afspilninger.

Brug en personlig konto på telefonen og en særskilt vægskærmskonto på fællestavlen. Den eksisterende loginmodel med én session pr. konto er bevaret. Push-tilmelding er knyttet til kontoen og fortsætter efter almindeligt sessionudløb. **Logout afmelder alle kontoens telefoner**, og passwordnulstilling, deaktivering eller sletning af kontoen ophæver også tilmeldingerne.

## Drift og begrænsninger

- Push kræver internet fra serveren til telefonens push-tjeneste og internet på telefonen. Understøttede browserudbydere er Apple, Google, Mozilla og Windows.
- Der er ingen garanteret leveringstid eller bekræftelse af, at brugeren har læst en besked. Telefonindstillinger, fokusfunktioner og netværk kan forsinke eller forhindre visning. Medicinoversigten fungerer uafhængigt af push.
- Standardbeskeder indeholder ikke person- eller medicinnavn. Brugeren kan vælge detaljer på sin enhed. Push indholdet krypteres inden afsendelse.
- Providerfejl genforsøges højst tre gange med mindst ét minut mellem forsøg. Udløbne abonnementer fjernes. Leveringshistorik opbevares syv dage; afsendelsen foretages uden en åben skrivetransaktion i databasen.
- En accepteret besked kan ikke trækkes tilbage, hvis medicinen registreres bagefter. Providerens TTL er fem minutter. Ved nedbrud mellem accept og databasekvittering kan et forsøg gentages; samme notifikationstag begrænser dubletter, men løsningen garanterer ikke præcis én levering.
- Service worker gemmer hverken sider, API-data eller afkrydsninger offline. Uden forbindelse vises en offlinebesked. Der er ikke en offline medicinkø.
- Ejeraktivering og personvalg er uafhængige af det eksisterende Docker-action-worker-flag. `PUSH_DELIVERY_ENABLED=false` stopper serverpush, inklusive testbeskeder. Skærmlyd styres separat på enheden.
- VAPID-nøgler er unikke for installationen og gemmes krypteret, ligesom enhedernes abonnementer. Backup skal bevare databasen og installationens eksisterende master-key-fil. Kopiér ikke ServerHubs database eller hemmeligheder til naboen eller staging.

## Staging og validering

Fra det eksisterende, rene staging-checkout på ServerHub:

```bash
cd /docker/Jarvis-os-ui-staging
git fetch origin
git switch --detach origin/feature/jarvis-pwa-notifications
bash scripts/staging.sh test
```

Staging bruger fortsat separat database, volume og netværk på `127.0.0.1:8098`; ingen Docker-socket eller produktionshemmeligheder. `compose.staging.yml` sætter eksplicit `PUSH_DELIVERY_ENABLED=false`, så en staging-kopi ikke sender telefonbeskeder. Reel telefonprøve kræver en særskilt, godkendt HTTPS-staging-adresse og et Compose override, der eksplicit sætter flaget til `true`; ændr ikke produktionsopsætningen som en del af stagingtesten.

Automatiske tests dækker adgang, CSRF, enhedsisolering, kryptering, udbyderadresser, udløb, genforsøg, stilleperioder, persistent afsendelseshistorik, gentagelser og tilbagekaldelse af tilmeldinger. Browserprøven bruger virkelig service worker, API/database og AudioContext, men syntetisk browserabonnement og simuleret provideraccept. Seks skærmstørrelse/tema-kombinationer er kontrolleret uden JavaScript-fejl eller vandret overløb.

Docker-build/staging kan ikke køres i udviklingsmiljøet, hvor Docker ikke findes. Reel iPhone/Android-modtagelse er endnu ikke verificeret. Før produktion skal en telefon modtage test og en planlagt påmindelse, åbne medicinfanen ved tryk, stoppe gentagelse efter registrering samt overholde stilleperiode. Produktionsdeployment kræver særskilt godkendelse.
