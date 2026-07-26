# VacatureWatcher

Een self-hosted applicatie om vacatures automatisch te volgen -- van
individuele werkgevers ("werken bij"-pagina's) én van vacatureplatforms
(sites met veel werkgevers/vacatures door elkaar).

VacatureWatcher controleert je bronnen periodiek, detecteert nieuwe en
verdwenen vacatures, en stuurt een melding als er iets verandert. De
applicatie draait volledig lokaal via Docker en bewaart alle gegevens
in een lokale SQLite-database.

---

## Wat is er nieuw in v2

v1 kon alleen simpele werkgeverspagina's volgen (één link-scrapertje
voor iedereen). v2 voegt een **adapter-architectuur** toe: per bron
kies je hoe die uitgelezen wordt, en een ingebouwde **Adapter Helper**
zoekt dat grotendeels voor je uit.

* Eén bron-formulier voor zowel werkgevers als vacatureplatforms
* Vier adapters: gestructureerde data (JSON-LD/microdata) met
  voorrang boven CSS-selectors, plus een generieke fallback
* Adapter Helper: geef een URL op, en de applicatie test automatisch
  welke aanpak werkt -- inclusief locatie, datum en paginering
* "Bron testen": een snelle preview zonder een volledige scan te
  starten
* Bronstatus per bron: laatste (succesvolle) controle, laatste fout,
  aantal nieuwe vacatures
* Systeem → Adapters: overzicht van alle adapters en wat ze
  ondersteunen
* Een kleine bibliotheek met voorbeeldbronnen om mee te beginnen

## Wat is er nieuw in v3

v3 herbouwt de Adapter Helper van "HTML → JSON in één stap" naar een
**Website Detective**-pijplijn (Analyse → Detectie → Adapter → JSON),
met als doel: minder gokwerk bij herhaalde analyses, en herkenning van
bekende ATS-platformen zonder heuristieken.

* **Detectie met geheugen**: een domein dat al eerder succesvol
  geanalyseerd is, wordt bij een volgende analyse direct herkend
  zonder de pagina opnieuw zwaar te hoeven doorzoeken (`site_fingerprint.py`).
  Vink "Forceer nieuwe analyse" aan bij **Analyseren** om dit te
  negeren en alsnog een volledige, verse detectie te draaien.
* **`greenhouse`-adapter**: automatische herkenning van Greenhouse
  Job Board-vacatures (`boards.greenhouse.io`, of een embed-widget op
  een eigen domein), via de officiële, stabiele Job Board API in
  plaats van HTML-scraping.
* **"Ruwe respons bekijken"**: knop op de bronpagina die de bron-URL
  rechtstreeks ophaalt (kale fetch, geen adapter ertussen) en toont
  wat er echt binnenkomt -- lengte, alle `<a href>`-links, een
  blokkade-hint, en of de geconfigureerde selector er iets in matcht.
  Bedoeld voor het scenario waarbij zowel de Adapter Helper als een
  handmatige adapter 0 vacatures vinden: eerst uitsluiten of het
  probleem bij het ophalen zit vóór je aan selectors gaat sleutelen.
* **Controledagen per bron**: naast het bestaande controle-interval
  (dagelijks/wekelijks) kun je nu ook zelf kiezen op welke dagen van
  de week een bron gecontroleerd mag worden.
* **Tijdlijn** (`/vacatures/tijdlijn`): chronologisch overzicht van
  alle vacatures over alle bronnen heen (datum -- vacature -- bron),
  als aanvulling op het bestaande per-bron overzicht.
* **Geautomatiseerde image-builds**: `.github/workflows/docker-publish.yml`
  bouwt en publiceert bij elke push naar `main` een multi-arch
  (`amd64`/`arm64`) Docker image naar GitHub Container Registry --
  `docker-compose.yml` trekt die binnen (`image: ghcr.io/...`), je NAS
  hoeft dus niet zelf te bouwen.
* **"Analyseren" gebruikt nu altijd een echte browser** (Playwright/
  Chromium, via het nieuwe `browser_analysis.py`), niet langer een
  kale HTTP-fetch. Reden: sommige sites laden hun vacaturewidget pas
  na JavaScript (zoals we bij Werken bij Wassenaar en vermoedelijk
  Werk bij Dunea tegenkwamen) -- een kale fetch zag dan simpelweg
  andere/lege HTML dan wat een bezoeker in de browser ziet, wat tot
  een verkeerde of ontbrekende aanbeveling leidde. `browser_listing`
  (voor de geplande controles) gebruikt dezelfde gedeelde
  infrastructuur, zodat analyse en daadwerkelijke controle altijd
  consistent gedrag vertonen. Kost wel een grotere Docker-image en een
  tragere analyse dan voorheen -- zie "Vereisten".
* **"Analyseren" vangt nu ook netwerkverkeer op** tijdens het laden
  van de pagina: XHR/fetch-aanroepen (dus geen afbeeldingen/fonts/CSS,
  en bekende analytics-/advertentiedomeinen worden ook weggefilterd),
  met een voorzichtige hint of een JSON-respons "op een vacaturelijst
  lijkt". Te zien als nieuwe sectie bij de analyseresultaten. Er
  worden nooit cookies of request-/response-headers bewaard, alleen
  URL, methode, status, content-type en (indien JSON) de body.
* **Nieuwe adapter `discovered_api`**: hergebruikt zo'n ontdekt
  JSON-endpoint voor de geplande controles. Wordt inmiddels ook
  AUTOMATISCH aanbevolen door de Adapter Helper als de sterkste
  kandidaat op een vacaturelijst lijkt -- na de kant-en-klare opties
  (Greenhouse/JSON-LD/microdata), maar vóór de twee HTML-heuristieken
  (een echte JSON-API is architecturaal robuuster dan op CSS-structuur
  gokken). Vult `endpoint_url`/`items_path` automatisch in; `field_map`
  (welke JSON-sleutel bij titel/url/locatie hoort) laat je bewust zelf
  invullen aan de hand van de getoonde respons -- dat raden zou stille
  verkeerde matches kunnen opleveren.
* Interne herstructurering van de detectielogica in twee losse,
  onafhankelijk testbare stappen (`_gather_signals`/`_classify`), met
  een bijbehorende, groeiende `pytest`-testsuite (`tests/`, 89 tests) --
  zie "Testen" verderop in dit document.

---

## Functies

### Bronnen beheren

* Twee brontypes: **Werkgever** (één "werken bij"-pagina) en
  **Vacatureplatform** (een site met veel vacatures/werkgevers)
* Eén editor voor toevoegen én wijzigen, met de Adapter Helper erin
  ingebouwd
* Bronnen wijzigen, verwijderen, handmatig controleren of testen

### Adapters

Elke bron gebruikt een van de volgende adapters om vacatures op te
halen. Zie `adapters/EXAMPLES.md` voor configuratievoorbeelden per
adapter, en de docstring bovenin elk `adapters/*.py`-bestand voor de
volledige uitleg.

| Adapter | Werkt op | Paginering | Categorieën | Detailpagina's | Datum | Locatie | Account nodig |
|---|---|---|---|---|---|---|---|
| `jsonld_listing` | schema.org JobPosting als JSON-LD | ja | nee | ja | ja | ja | nee |
| `microdata_listing` | schema.org JobPosting als HTML-attributen | ja | nee | ja | ja | ja | nee |
| `html_listing` | herhalende HTML-blokken, via CSS-selectors | ja | ja | nee | ja | ja | nee |
| `browser_listing` | sites die vacatures via JavaScript laden (headless Chromium) | ja | nee | nee | ja | ja | nee |
| `generic_links` | simpele "vacature-achtige" links (v1-aanpak) | nee | nee | nee | nee | nee | nee |
| `cso_api` | CSO Vacature-API (Werken voor Nederland e.a.) | nee | ja | nee | nee | nee | ja |
| `greenhouse` | Greenhouse Job Board API (automatisch gedetecteerd) | nee | nee | nee | ja | ja | nee |
| `discovered_api` | Site-eigen JSON-endpoint, ontdekt tijdens Analyseren | nee | nee | nee | ja | ja | nee |

`browser_listing` vereist geen account en geen losse installatiestap
meer -- Playwright + Chromium zitten standaard in de Docker-image
(sinds "Analyseren" zelf ook altijd een echte browser gebruikt, zie
"Wat is er nieuw" hierboven). Gebruik deze adapter voor geplande
controles alleen als de andere adapters aantoonbaar niets vinden (zie
**Systeem → Diagnose** hieronder) -- een browser is trager en zwaarder
dan een simpele HTTP-fetch, dus niet de standaardkeuze voor elke bron.

Dit overzicht staat ook live in de applicatie onder **Systeem →
Adapters**, inclusief hoeveel bronnen elke adapter op dit moment
gebruiken.

### Adapter Helper

Bij het toevoegen of wijzigen van een bron kun je op "Analyseren"
klikken. Als het domein nog niet eerder (recent) geanalyseerd is,
opent de applicatie de pagina in een echte (headless) browser
(Playwright/Chromium, zie `browser_analysis.py`) -- niet langer een
kale HTTP-fetch, juist omdat sommige sites hun vacatures pas na
JavaScript tonen. Op de gerenderde pagina probeert de Adapter Helper,
in volgorde van voorkeur:

1. Een harde fingerprint-match met een bekend platform (op dit moment:
   Greenhouse, via een `greenhouse.io`-scriptbron of -URL) -- adapter
   `greenhouse`
2. JSON-LD (schema.org JobPosting)
3. Microdata (schema.org, als HTML-attributen)
4. Een ontdekt, site-eigen JSON-endpoint dat op een vacaturelijst
   lijkt (zie "Ontdekt netwerkverkeer" hieronder) -- adapter
   `discovered_api`
5. Een herhalend HTML-blok rond vacature-achtige links -- of, als dat
   niets oplevert, rond herhalende koppen (`<h2>`/`<h3>`/`<h4>`)
6. Generieke links (werkt bijna altijd wel een beetje)

`discovered_api` staat bewust ná de eerste drie (zero-config,
gestandaardiseerde) methodes maar vóór de twee HTML-heuristieken: een
echte JSON-API is robuuster dan op CSS-structuur gokken, maar vraagt
altijd nog een handmatige stap (zie hieronder) terwijl greenhouse/
JSON-LD/microdata meteen kant-en-klaar zijn.

Voor elke kandidaat die iets vindt, zie je een preview van de
gevonden vacatures (titel, en waar mogelijk locatie/datum) vóórdat je
iets opslaat -- de Adapter Helper gokt niet stilzwijgend, hij laat
zien wat elke aanpak daadwerkelijk oplevert. Paginering wordt apart
gedetecteerd en waar mogelijk automatisch meegenomen.

**Ontdekt netwerkverkeer**: tijdens het renderen vangt de Adapter
Helper ook XHR/fetch-aanroepen op die de pagina zelf deed (dus geen
afbeeldingen/fonts/CSS, en bekende analytics-/advertentiedomeinen
worden weggefilterd) -- er worden nooit cookies of request-/
response-headers bewaard, alleen URL, methode, status, content-type
en (indien JSON) de body. Lijkt zo'n respons op een vacaturelijst
(array van objecten met velden als `title`/`vacature`/`functie`), dan
wordt die getoond met een "Gebruik deze API"-knop, en -- als het de
sterkste kandidaat is -- automatisch aanbevolen als `discovered_api`.
`endpoint_url`/`items_path` worden dan voorgesteld, maar `field_map`
(welke JSON-sleutel bij titel/url/locatie hoort) laat de applicatie
bewust LEEG: dat verschilt per site en wordt niet geraden.

**Detectie met geheugen**: een domein dat al eerder succesvol
geanalyseerd is (binnen de laatste 30 dagen), wordt bij een volgende
analyse direct herkend zonder de pagina opnieuw te hoeven doorzoeken
-- je ziet dan een korte samenvatting in plaats van de volledige
kandidatenlijst. Vink **"Forceer nieuwe analyse"** aan om dit te
negeren en alsnog alle kandidaten opnieuw te testen (bv. als de
website intussen van structuur veranderd is).

Belangrijk: deze detectie draait alléén als je zelf op "Analyseren"
klikt. De geplande controles draaien op de vaste selectors/instellingen
die je opslaat, niet op een herhaalde live gok -- dat houdt het
gedrag van een bron voorspelbaar. Alleen adapters `browser_listing`
en `discovered_api` (als je die kiest) doen bij de geplande controle
zelf ook weer een live aanroep; de andere adapters gebruiken de
opgeslagen selectors op een kale HTTP-fetch.

### Bron testen

Op de detailpagina van een bron kun je "Bron testen" gebruiken: dit
voert de echte adapter uit, laat de eerste vijf gevonden vacatures
zien plus het totaal, en toont eventuele fouten direct. Er wordt
niets opgeslagen en er gaan geen meldingen uit -- handig om een
nieuwe configuratie te checken zonder een volledige controle te
starten.

### Ruwe respons bekijken

Ook op de detailpagina van een bron: haalt de bron-URL rechtstreeks op
met een kale HTTP-fetch (dezelfde als de geplande controle voor een
niet-browser-adapter gebruikt) -- zonder adapter, zonder selector
ertussen. Toont:

* de lengte van de respons en het totaal aantal `<a href>`-tags;
* een voorzichtige hint of de respons op een blokkade- of
  bot-detectiepagina lijkt (ongebruikelijk kort, of bekende teksten
  als "Just a moment... Checking your browser") -- geen zekerheid,
  wel een sterke aanwijzing;
* of de geconfigureerde `selectors.item` van de huidige adapter
  daadwerkelijk iets matcht in DEZE verse respons;
* bij een klein aantal links: een volledige tabel (href/class/tekst),
  zodat je niet handmatig door de HTML-preview hoeft te zoeken.

Bedoeld voor precies het scenario waarbij zowel de Adapter Helper als
een handmatig ingestelde adapter 0 vacatures vinden: dan wil je eerst
weten of het probleem bij het OPHALEN zit (blokkade, JavaScript-
afhankelijke inhoud) of bij de SELECTOR, vóór je selectors gaat
aanpassen. Let op: dit is een kale fetch, geen browser -- gebruik
"Analyseren" (die wél een browser gebruikt) als je vermoedt dat een
site pas na JavaScript zijn vacatures toont.

### Bronstatus

Elke bron toont een statusoverzicht: laatste controle, laatste
geslaagde controle, aantal (actieve) vacatures, aantal nieuwe
vacatures bij de laatste geslaagde controle, de gebruikte adapter, en
de laatste foutmelding (indien van toepassing).

### Vacature-overzichten

Twee weergaven, beide met live data uit de database:

* **Alle vacatures** (`/vacatures`) -- per bron gegroepeerd, alleen
  actieve vacatures.
* **Tijdlijn** (`/vacatures/tijdlijn`) -- chronologisch over alle
  bronnen heen (datum, vacature, bron), nieuwste eerst, max. 200
  resultaten. Met `?toon=alle` (of de link op de pagina zelf) worden
  ook verdwenen vacatures getoond, met een "Verdwenen"-badge en de
  datum waarop ze voor het laatst gezien zijn.

### Systeem → Diagnose

Draait "Bron testen" in één keer tegen ALLE bronnen, en categoriseert
het resultaat: OK, geen resultaten, of fout -- met bij "geen
resultaten" een vermoeden of het om JavaScript-rendering gaat (weinig
zichtbare tekst / bekende SPA-kenmerken in de HTML). Handig zodra je
meerdere bronnen hebt: in plaats van bronnen één voor één handmatig na
te lopen, zie je in één overzicht welke aandacht nodig hebben en
waarom.

### Voorbeeldbronnen

Bij het toevoegen van een nieuwe bron kun je kiezen uit een aantal
voorbeelden (o.a. Werken voor Nederland, Culturele Vacatures, Werken
bij Gemeenten, een paar gemeentes en een provincie) om naam en URL
alvast in te vullen. Voor de meeste voorbeelden klik je daarna zelf op
"Analyseren" -- alleen bij Werken voor Nederland (CSO) is de volledige
configuratie al ingevuld (dat vereist wel een eigen API-account, zie
`adapters/EXAMPLES.md`).

### Zoekwoordenfilter

Per bron kun je zoekwoorden instellen, bijvoorbeeld:

```
ict, netwerk, beheer, asset, data
```

Alleen vacatures waarin één van deze woorden voorkomt worden als
relevant beschouwd. Dit kan via het eenvoudige "Zoekwoorden"-veld, of
preciezer via `settings.include_keywords`/`settings.exclude_keywords`
in de adapter-instellingen.

### Meldingen

Ondersteuning voor console-, e-mail- en Telegram-meldingen, verstuurd
bij nieuwe of verdwenen vacatures.

### Back-up

Automatische en handmatige database-back-ups; de SQLite-database
blijft behouden bij Docker-updates.

---

# Installatie met Docker

## Vereisten

* Docker
* Docker Compose

Getest met Docker Engine, Docker Compose v2, Linux / OpenMediaVault.

De Docker-image bevat sinds kort standaard een headless Chromium
(via Playwright) -- dit maakt de image aanzienlijk groter (~½-1 GB
extra) en de eerste build trager dan je misschien gewend bent. Dit is
een bewuste keuze: "Analyseren" gebruikt die browser om
JavaScript-afhankelijke vacaturesites correct te herkennen (zie "Wat
is er nieuw" bovenaan), in plaats van dat je daar zelf pas achter komt
nadat een aanbevolen adapter live 0 resultaten blijkt te geven.

## Installatie

```bash
git clone https://github.com/<gebruikersnaam>/vacaturewatcher.git
cd vacaturewatcher
cp .env.example .env
nano .env
docker compose pull
docker compose up -d
docker ps
docker logs -f vacaturewatcher
```

`docker compose pull` haalt de kant-en-klare image binnen die
`.github/workflows/docker-publish.yml` bij elke push naar `main`
bouwt (zie "Docker image bouwen via GitHub Actions" verderop) -- je
NAS hoeft dus niet zelf te bouwen. Bouw je liever lokaal (bv. tijdens
ontwikkelen), zie de `build:`-alternatief in `docker-compose.yml`.

## Bestaande installatie bijwerken naar v2

Als je al vacatures/werkgevers had opgeslagen (v1, of een eerdere
v2-tussenversie), draai dan **eenmalig** het migratiescript voordat je
de nieuwe code voor het eerst start. Dit draait BINNEN de container
(niet op de NAS zelf) -- daar staan de juiste Python-afhankelijkheden
en wijst `DATABASE_PATH` naar het gekoppelde `data`-volume:

```bash
docker compose pull
docker compose up -d
docker compose exec vacaturewatcher python migrate_v1_to_v2.py
docker compose restart vacaturewatcher
```

Dit script is idempotent: het is veilig om het bij elke upgrade
opnieuw te draaien, het pakt dan alleen de kolommen op die nog
ontbreken. Nieuwe installaties hebben dit niet nodig.

---

# Gebruik

Open de webinterface:

```
http://<server-ip>:1276
```

## Eerste bron toevoegen

Ga naar **Bron toevoegen**. Kies eventueel eerst een voorbeeld uit de
lijst om naam en URL in te vullen, of vul ze zelf in:

| Veld | Voorbeeld |
|---|---|
| Type bron | Werkgever, of Vacatureplatform |
| Naam bron | Gemeente Rotterdam |
| URL | `https://www.website.nl/vacatures` |
| Zoekwoorden | ict, netwerk, beheer |
| Controle interval | Dagelijks |
| Controledagen | Alle dagen (standaard), of zelf kiezen (bv. alleen ma/wo/vr) |

Klik op **Analyseren** om de Adapter Helper de pagina te laten testen,
kies een van de voorgestelde instellingen (of laat "generic_links"
staan voor een simpele werkgeverspagina), en sla op. Gebruik daarna
**Bron testen** op de detailpagina om snel te checken of het werkt,
of **Nu controleren** voor een volledige scan (inclusief opslaan en
meldingen).

> **Let op** bij "Controle interval" = Wekelijks: dit betekent altijd
> "op maandag", ongeacht welke dagen je bij Controledagen aanvinkt.
> Kies dus geen Controledagen-selectie zonder maandag in combinatie
> met Wekelijks, anders draait de bron nooit.

---

# Configuratie

De configuratie staat in `.env`:

```env
APP_NAME=VacatureWatcher

SECRET_KEY=verander_dit

DATABASE_PATH=/app/data/vacaturewatcher.db

# Wordt bij de EERSTE opstart gebruikt om de admin-inlog aan te maken.
# Vul dus vóór de eerste start in -- zonder deze twee kun je niet
# inloggen.
ADMIN_USERNAME=admin
ADMIN_PASSWORD=verander_dit


EMAIL_ENABLED=false

SMTP_SERVER=
SMTP_PORT=587

SMTP_USERNAME=
SMTP_PASSWORD=

EMAIL_FROM=
EMAIL_TO=


TELEGRAM_ENABLED=false

TELEGRAM_TOKEN=
TELEGRAM_CHAT_ID=


# Alleen nodig voor bronnen met adapter "cso_api"
# (account aanvragen via helpdesk@werkenvoornederland.nl)
CSO_USERNAME=
CSO_PASSWORD=
```

## Tijdzone en controledagen

`docker-compose.yml` zet `TZ=Europe/Amsterdam` voor de container. Dit
bepaalt op welke weekdag een controle volgens de klok van de
container valt -- essentieel voor de "Controledagen"-instelling per
bron (`Source.check_days`, zie **Bron bewerken**). Draai je de NAS in
een andere tijdzone, pas dan deze regel in `docker-compose.yml` aan.
Zonder een correcte tijdzone-instelling rekent de container in UTC,
wat rond middernacht tot een verschoven weekdag kan leiden.

## Problemen oplossen

**`sqlite3.OperationalError: unable to open database file`** bij het
opstarten -- de container kan niet schrijven naar het gemounte
`/app/data`-volume. Meestal doordat de map op de host (NAS) een
andere eigenaar heeft dan de vaste gebruiker in de image. Twee opties:
* Zet `PUID`/`PGID` in `docker-compose.yml` op de UID/GID van de
  gewenste eigenaar op je NAS -- `entrypoint.sh` past dit bij het
  opstarten toe en corrigeert de eigendom van `./data` automatisch.
* Of chown de map zelf op de NAS: `chown -R 1000:1000 ./data`
  (1000 is de standaard-UID in de image, zonder `PUID`/`PGID`).

**Zorg dat `docker-compose.yml` naar de juiste image wijst** --
`ghcr.io/<jouw-github-gebruiker>/<jouw-reponaam>:latest`. Gebruik je
een andere repo-naam of -eigenaar dan `stephansande/vacaturewatcher`,
pas dan de `image:`-regel aan.

**OMV/Portainer-templatesyntax zoals `${{ sf:"appdata" }}`** in het
`volumes:`-pad is geen standaard docker-compose-syntax. Gebruik een
gewoon relatief of absoluut pad (zoals hierboven, `./data:/app/data`)
als je twijfelt of zo'n macro correct wordt vervangen.

## Docker image bouwen via GitHub Actions (CI/CD)

`.github/workflows/docker-publish.yml` bouwt bij elke push naar `main`
automatisch een nieuwe image en publiceert die naar GitHub Container
Registry (`ghcr.io`), voor zowel `amd64` als `arm64`. Je NAS hoeft dan
nooit zelf te bouwen -- `docker-compose.yml` trekt gewoon de kant-en-
klare image binnen (`image: ghcr.io/...`, zie hierboven).

Wat je zelf moet doen, eenmalig:

1. **Push deze code naar GitHub** (een repo met daarin `Dockerfile`,
   `.github/workflows/docker-publish.yml`, en de rest van dit
   project). Geen extra instellingen nodig -- de workflow gebruikt de
   ingebouwde `GITHUB_TOKEN`, geen apart secret.
2. **Wacht tot de eerste run klaar is** (tab **Actions** in je repo).
   Duurt door de `arm64`-build via emulatie een paar minuten langer
   dan een gewone lokale build.
3. **Zet het package op publiek**, anders kan `docker compose pull`
   op je NAS niet inloggen: ga naar je GitHub-profiel → **Packages**
   → `vacaturewatcher` → **Package settings** → **Change visibility**
   → **Public**. (Alternatief: privé laten en `docker login ghcr.io`
   met een Personal Access Token op je NAS draaien -- maar publiek is
   voor een side-project simpeler.)
4. Op je NAS: `docker compose pull && docker compose up -d`.

Elke volgende push naar `main` bouwt automatisch een nieuwe `:latest`.
Om te updaten op je NAS: `docker compose pull && docker compose up -d`
(geen `--build` nodig, je bouwt niet meer lokaal). Elke image krijgt
ook een tag met de korte commit-hash (bv. `:a1b2c3d`), zodat je nodig
terug kan naar een specifieke eerdere versie door die tag in
`docker-compose.yml` te zetten in plaats van `:latest`.

Wil je dit automatisch laten trekken zodra er een nieuwe `:latest`
verschijnt (zonder zelf `docker compose pull` te draaien), kijk dan
naar [Watchtower](https://github.com/containrrr/watchtower) -- niet
door dit project meegeleverd, maar een veelgebruikte, aparte
self-hosted tool hiervoor.

## E-mail notificaties

```env
EMAIL_ENABLED=true

SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587

SMTP_USERNAME=jouw@email.nl
SMTP_PASSWORD=wachtwoord

EMAIL_FROM=jouw@email.nl
EMAIL_TO=jouw@email.nl
```

Gebruik bij Gmail bij voorkeur een app-wachtwoord.

## Telegram notificaties

Maak een Telegram-bot via <https://core.telegram.org/bots>, en vul
daarna in:

```env
TELEGRAM_ENABLED=true

TELEGRAM_TOKEN=<bot-token>
TELEGRAM_CHAT_ID=<chat-id>
```

## CSO Vacature-API (Werken voor Nederland)

Alleen nodig als je een bron met adapter `cso_api` gebruikt. Vraag een
account aan bij de CSO-helpdesk, zie `adapters/EXAMPLES.md` en de
docstring in `adapters/cso_api.py` voor details.

---

# Data opslag

```
data/
├── vacaturewatcher.db
└── backups/
    ├── vacaturewatcher_20260710.db
    └── ...
```

De map `data` wordt als Docker-volume behouden.

## Back-up maken

Via de webinterface (**Instellingen → Backup maken**), of handmatig:

```bash
cp data/vacaturewatcher.db backup.db
```

---

# Update

```bash
git pull
docker compose pull
docker compose up -d
docker compose exec vacaturewatcher python migrate_v1_to_v2.py
docker compose restart vacaturewatcher
```

`git pull` is hier vooral voor je eigen `.env`/`docker-compose.yml`-
aanpassingen en dit README-bestand; de daadwerkelijke applicatiecode
komt via `docker compose pull` binnen (de image die GitHub Actions
bij de laatste push naar `main` heeft gebouwd, zie "Docker image
bouwen via GitHub Actions"). De database blijft behouden. Vergeet de
migratiestap niet -- draai die ná `up -d` (de container met de nieuwe
code moet al draaien om het script binnenin te kunnen uitvoeren) maar
vóór je erop vertrouwt dat nieuwe kolommen/functies werken.

---

# Verwijderen

```bash
docker compose down
rm -rf vacaturewatcher
rm -rf data   # inclusief database
```

---

# Projectstructuur

```
vacaturewatcher/

├── .github/
│   └── workflows/
│       └── docker-publish.yml   bouwt + publiceert de image naar ghcr.io bij elke push naar main

├── app.py
├── auth.py                    login/logout (Flask-Login)
├── config.py
├── database.py
├── models.py

├── scraper.py                 kale HTTP-fetch (o.a. raw_fetch_debug, diagnose_source)
├── browser_analysis.py        gedeelde Playwright-infrastructuur (Analyseren + browser_listing)
├── adapter_helper.py          Website Detective: _gather_signals / _classify / analyze
├── site_fingerprint.py        cache: onthoudt eerder gedetecteerde adapter per domein
├── example_sources.py
├── vacancy_parser.py         (legacy, vervangen door adapters/generic_links.py)
├── comparer.py                (legacy, ongebruikt)
├── export_import.py           database export/import

├── adapters/
│   ├── base.py               gedeelde helpers (settings, keyword-filter, fetch)
│   ├── registry.py           koppelt adapternamen aan modules + capabilities
│   ├── generic_links.py
│   ├── html_listing.py
│   ├── jsonld_listing.py
│   ├── microdata_listing.py
│   ├── browser_listing.py    JavaScript-sites, via de gedeelde Playwright-infrastructuur
│   ├── cso_api.py
│   ├── greenhouse.py         Greenhouse Job Board API, automatisch gedetecteerd
│   ├── discovered_api.py     hergebruikt een via Analyseren ontdekt JSON-endpoint
│   └── EXAMPLES.md           configuratievoorbeelden per adapter

├── notifications.py
├── backup.py
├── migrate_v1_to_v2.py

├── services/
│   ├── vacancy_checker.py
│   ├── scheduler_service.py
│   └── notification_service.py

├── tests/                    pytest -- zie sectie "Testen" hieronder
│   ├── test_adapter_helper_classify.py    _classify()-precedentie (incl. discovered_api)
│   ├── test_greenhouse_adapter.py
│   ├── test_source_scheduling.py
│   ├── test_html_listing_link_attr.py     onclick-widgets (bv. Werken bij Wassenaar)
│   ├── test_raw_fetch_debug.py            "Ruwe respons bekijken"
│   ├── test_browser_analysis.py           Playwright-navigatie (gemockt)
│   ├── test_browser_analysis_requests.py  netwerkverkeer-opvang tijdens analyse (gemockt)
│   └── test_discovered_api.py

├── templates/
├── static/

├── data/

├── Dockerfile
├── entrypoint.sh             past PUID/PGID toe en chown't /app/data bij het opstarten
├── docker-compose.yml
├── requirements.txt          bevat ook playwright (zie Vereisten)
├── requirements-dev.txt      optioneel: pytest, alleen voor lokaal testen
├── .env.example
└── .gitignore
```

---

# Testen

Het project heeft een `pytest`-testsuite (89 tests) voor de
detectielogica van de Adapter Helper (inclusief de
`discovered_api`-precedentie), de Greenhouse-adapter, de
weekdag-planning, de `onclick`-widget-ondersteuning in
`html_listing` (zie Werken bij Wassenaar), "Ruwe respons bekijken",
en de Playwright-aansturing in `browser_analysis.py`. Alleen nodig
voor ontwikkeling, niet voor gewoon gebruik -- de Docker-image bevat
`pytest` niet.

Belangrijk: **geen echte browser/Chromium nodig** om de testsuite te
draaien -- alle Playwright-gerelateerde tests gebruiken gemockte
`page`/`response`-objecten, precies zodat `pytest tests/` overal blijft
werken zonder dat er een browser-binary geïnstalleerd hoeft te zijn.

```bash
pip install -r requirements.txt -r requirements-dev.txt --break-system-packages
pytest tests/ -v
```

Of binnen een draaiende container (heeft `requirements.txt` al
geïnstalleerd, dan hoeft alleen `requirements-dev.txt` nog bij):
```bash
docker compose exec vacaturewatcher pip install -r requirements-dev.txt
docker compose exec vacaturewatcher pytest tests/ -v
```

---

# Techniek

* Python 3.12
* Flask, Flask-Login
* SQLite + SQLAlchemy
* APScheduler
* BeautifulSoup (`lxml`-parser)
* Docker

---

# Beperkingen

* Sommige vacaturepagina's laden inhoud via JavaScript; "Analyseren"
  herkent dit inmiddels vanzelf (gebruikt altijd een echte browser),
  maar voor de geplande controles moet je zelf nog `browser_listing`
  kiezen -- geen losse installatiestap meer nodig, wel zwaarder qua
  resources (een echte browserpagina per controle) dan de andere
  adapters.
* Sommige websites blokkeren geautomatiseerde toegang (robots.txt) of
  verbieden scraping in hun voorwaarden -- controleer dit zelf per
  site voordat je een bron toevoegt (de applicatie checkt dit op dit
  moment niet automatisch, zie Roadmap).
* De `html_listing`-heuristiek van de Adapter Helper is een gok op
  basis van herhalende structuur; controleer altijd de preview
  voordat je opslaat.
* Geplande controles gebruiken vaste, opgeslagen selectors -- als een
  site van structuur verandert, moet je de bron zelf opnieuw
  analyseren (**Analyseren** met **"Forceer nieuwe analyse"**
  aangevinkt), dit gebeurt niet automatisch.
* `check_interval` = Wekelijks betekent altijd "op maandag", ongeacht
  de gekozen Controledagen -- zie de noot bij "Eerste bron toevoegen".
* `discovered_api` gebruikt een ONOFFICIEEL, intern JSON-endpoint van
  de website zelf (geen gedocumenteerde publieke API) -- dit kan
  zonder aankondiging veranderen. Test na het instellen altijd met
  "Bron testen", en houd er rekening mee dat dit vaker onderhoud kan
  vragen dan `cso_api`/`greenhouse`.
* `cso_api` extraheert nog geen locatie/datum (de API levert dit wel,
  maar het exacte veldpad is nog niet geverifieerd -- zie de
  toelichting in `adapters/cso_api.py`).
* Gebruik **Systeem → Diagnose** om in één keer te zien welke bronnen
  niet (goed) werken en waarom, in plaats van dit per bron handmatig
  te moeten uitzoeken.

Gebruik de applicatie volgens de voorwaarden van de betreffende
websites.

---

# Roadmap

Mogelijke toekomstige uitbreidingen:

* [ ] Locatie/datum-extractie voor `cso_api` (na verificatie van het
      juiste veldpad in `jobFeatures.location`)
* [ ] `settings.categories` daadwerkelijk toepassen op sites die dat
      ondersteunen (nu alleen informatief veld)
* [ ] RSS-adapter
* [x] Browser automation voor JavaScript-zware pagina's
      (`adapters/browser_listing.py`, standaard onderdeel van de
      Docker-image via `browser_analysis.py`)
* [x] "Analyseren" gebruikt altijd een echte (headless) browser, zodat
      JavaScript-afhankelijke sites al bij analyse correct herkend
      worden i.p.v. pas na een verkeerde aanbeveling te ontdekken
      (zie "Wat is er nieuw" bovenaan)
* [x] Netwerkverkeer tijdens analyse opslaan/doorzoeken
      (`browser_analysis.py`, "Ontdekt netwerkverkeer tijdens het
      laden" op de bronpagina) + adapter `discovered_api` om zo'n
      gevonden JSON-endpoint te hergebruiken voor de geplande
      controles (handmatig via "Gebruik deze API" -- automatische
      herkenning/voorrang in `_classify()` is een logische
      vervolgstap, zie hieronder)
* [x] `_classify()` uitgebreid zodat een ontdekt JSON-endpoint dat
      duidelijk op een vacaturelijst lijkt automatisch wordt
      voorgesteld als `discovered_api`, ná de kant-en-klare opties
      (greenhouse/jsonld/microdata) maar vóór de HTML-heuristieken --
      "Gebruik deze instellingen" werkt hier meteen via de bestaande,
      generieke knop-infrastructuur
* [ ] `browser_listing`: detailpagina-modus (mode "detail", zoals
      jsonld_listing/microdata_listing al hebben)
* [x] Geautomatiseerde testsuite (pytest) -- `tests/`, tests voor
      de Adapter Helper-classificatie, de Greenhouse-adapter en de
      weekdag-planning
* [x] Chronologisch vacature-overzicht (datum -- vacature -- bron)
      over alle bronnen heen, als aanvulling op het bestaande
      per-bron overzicht -- **Tijdlijn** (`/vacatures/tijdlijn`)
* [ ] Tweede platform-adapter (bv. Workday) bovenop de
      fingerprint-aanpak uit `greenhouse.py`
* [ ] Robots.txt-check inbouwen in `scraper.fetch_html()`
* [ ] CSRF-bescherming (Flask-WTF)
* [ ] Overstap naar Flask-Migrate/Alembic i.p.v. handmatige
      migratiescripts
* [ ] Meerdere gebruikers
* [ ] API voor externe integraties
* [x] Docker image publiceren -- `.github/workflows/docker-publish.yml`,
      automatisch naar `ghcr.io` bij elke push naar `main`

---

# Licentie

Dit project wordt beschikbaar gesteld onder de MIT-licentie. Je mag de
software gebruiken, aanpassen, uitbreiden en verspreiden.

---

# Bijdragen

Pull requests en verbeteringen zijn welkom. Bijdragen graag voorzien
van een duidelijke beschrijving, testinformatie, en eventuele
screenshots.

---

# Disclaimer

VacatureWatcher is een hulpmiddel om openbare vacaturepagina's te
monitoren. Controleer altijd de gebruiksvoorwaarden en robots.txt van
de websites die je monitort.
