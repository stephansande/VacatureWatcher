# VacatureWatcher

Een self-hosted applicatie om vacatures automatisch te volgen -- van
individuele werkgevers ("werken bij"-pagina's) én van vacatureplatforms
(sites met veel werkgevers/vacatures door elkaar).

VacatureWatcher controleert je bronnen periodiek, detecteert nieuwe en
verdwenen vacatures, en stuurt een melding als er iets verandert. De
applicatie draait volledig lokaal via Docker en bewaart alle gegevens
in een lokale SQLite-database.

---

## Functies

### Bronnen beheren

* Twee brontypes: **Werkgever** (één "werken bij"-pagina) en
  **Vacatureplatform** (een site met veel vacatures/werkgevers)
* Eén editor voor toevoegen én wijzigen, met de Adapter Helper erin
  ingebouwd
* Bronnen wijzigen, verwijderen, handmatig controleren of testen
* Naast het controle-interval (dagelijks/wekelijks) kun je per bron
  ook zelf kiezen op welke dagen van de week een controle mag draaien

### Adapters

Elke bron gebruikt een van de volgende adapters om vacatures op te
halen. Zie `adapters/EXAMPLES.md` voor configuratievoorbeelden per
adapter, en de docstring bovenin elk `adapters/*.py`-bestand voor de
volledige uitleg.

| Adapter | Werkt op | Paginering | Categorieën | Detailpagina's | Datum | Locatie | Account nodig |
|---|---|---|---|---|---|---|---|
| `jsonld_listing` | schema.org JobPosting als JSON-LD | ja | nee | ja | ja | ja | nee |
| `microdata_listing` | schema.org JobPosting als HTML-attributen | ja | nee | ja | ja | ja | nee |
| `embedded_json` | Hydration-payload in de pagina-bron (bv. Next.js/Nuxt) | nee | nee | nee | ja | ja | nee |
| `html_listing` | herhalende HTML-blokken, via CSS-selectors | ja | ja | nee | ja | ja | nee |
| `browser_listing` | sites die vacatures via JavaScript laden (headless Chromium) | ja | nee | nee | ja | ja | nee |
| `generic_links` | simpele "vacature-achtige" links | nee | nee | nee | nee | nee | nee |
| `cso_api` | CSO Vacature-API (Werken voor Nederland e.a.) | nee | ja | nee | nee | nee | ja |
| `greenhouse` | Greenhouse Job Board API (automatisch gedetecteerd) | nee | nee | nee | ja | ja | nee |
| `discovered_api` | Site-eigen JSON-endpoint, ontdekt tijdens Analyseren | nee | nee | nee | ja | ja | nee |

`browser_listing` en `embedded_json` vereisen geen account, maar
gebruiken bij de geplande controle wel een echte headless browser
(Playwright/Chromium, standaard onderdeel van de Docker-image) --
trager en zwaarder dan een simpele HTTP-fetch, dus niet de
standaardkeuze voor elke bron. Gebruik ze voor geplande controles
alleen als de andere adapters aantoonbaar niets vinden (zie
**Systeem → Diagnose** hieronder).

Dit overzicht staat ook live in de applicatie onder **Systeem →
Adapters**, inclusief hoeveel bronnen elke adapter op dit moment
gebruiken.

### Adapter Helper

Bij het toevoegen of wijzigen van een bron kun je op "Analyseren"
klikken. Als het domein nog niet eerder (recent) geanalyseerd is,
opent de applicatie de pagina in een echte (headless) browser
(Playwright/Chromium, zie `browser_analysis.py`) -- niet een kale
HTTP-fetch, juist omdat sommige sites hun vacatures pas na JavaScript
tonen. Op de gerenderde pagina probeert de Adapter Helper, in volgorde
van voorkeur:

1. Een harde fingerprint-match met een bekend platform (op dit moment:
   Greenhouse, via een `greenhouse.io`-scriptbron of -URL) -- adapter
   `greenhouse`
2. JSON-LD (schema.org JobPosting)
3. Microdata (schema.org, als HTML-attributen)
4. Een gevonden hydration-payload die het framework al in de EERSTE
   HTML-bron meestuurt (zie "Embedded JSON" hieronder) -- adapter
   `embedded_json`
5. Een ontdekt, site-eigen JSON-endpoint dat op een vacaturelijst
   lijkt (zie "Ontdekt netwerkverkeer" hieronder) -- adapter
   `discovered_api`
6. Een herhalend HTML-blok rond vacature-achtige links -- of, als dat
   niets oplevert, rond herhalende koppen (`<h2>`/`<h3>`/`<h4>`)
7. Generieke links (werkt bijna altijd wel een beetje)

`embedded_json` en `discovered_api` staan bewust ná de eerste drie
(zero-config, gestandaardiseerde) methodes maar vóór de twee
HTML-heuristieken: een echte JSON-bron is robuuster dan op
CSS-structuur gokken, maar vraagt altijd nog een handmatige stap (zie
hieronder) terwijl greenhouse/JSON-LD/microdata meteen kant-en-klaar
zijn. `embedded_json` staat vóór `discovered_api`: een hydration-
payload zit gegarandeerd al in de eerste pagina-aanvraag, een ontdekt
netwerk-endpoint is iets minder zeker aanwezig.

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

**Embedded JSON**: sommige sites (met name Next.js/Nuxt/Vue-gebouwde
"werken bij"-pagina's) zetten hun vacaturedata al als JSON in de
EERSTE HTML-pagina zelf (geen aparte netwerkaanroep nodig) -- bv.
Next.js' `<script id="__NEXT_DATA__">` of Nuxt's `window.__NUXT__=`.
Wordt dat gevonden, dan zie je dat als aparte sectie met een "Gebruik
deze instellingen"-knop als het de sterkste kandidaat is; adapter
`embedded_json` haalt de pagina bij elke geplande controle opnieuw op
(via dezelfde headless browser als "Analyseren") om bij die payload te
kunnen. `items_path` wordt automatisch voorgesteld, `field_map` laat
je -- net als bij `discovered_api` -- bewust zelf invullen.

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
gedrag van een bron voorspelbaar. Alleen `browser_listing`,
`embedded_json` en `discovered_api` doen bij de geplande controle zelf
ook weer een live aanroep; de andere adapters gebruiken de opgeslagen
selectors op een kale HTTP-fetch.

### Validatie vóór opslaan

Bij het opslaan van een bron controleert de applicatie automatisch of
de configuratie klopt, in twee stappen:

1. **Structureel**: is de settings-JSON geldig, en heeft de gekozen
   adapter de velden die hij sowieso nodig heeft (bv.
   `selectors.item` bij `html_listing`, `items_path` bij
   `embedded_json`, `endpoint_url` bij `discovered_api`)? Deze stap is
   altijd verplicht -- er gaat geen netwerkverkeer aan te pas, dus er
   is geen reden om 'm ooit over te slaan.
2. **Live**: voert de daadwerkelijke adapter (`fetch()`+`parse()`) uit
   tegen de ingevulde instellingen, dezelfde check als "Bron testen"
   hieronder. Vangt fouten die de structurele check niet ziet, zoals
   een pad dat er geldig uitziet maar niet naar de juiste plek in de
   JSON wijst, of een 404 op de opgegeven URL. Draait niet voor elke
   adapter automatisch:
   * gewone HTTP-adapters (`generic_links`, `html_listing`,
     `jsonld_listing`, `microdata_listing`, `discovered_api`,
     `greenhouse`) -- altijd automatisch, snel en zonder credentials;
   * `browser_listing`/`embedded_json` -- alleen als je het vinkje
     "Ook live testen" aanzet, want dit start een headless browser en
     kost een paar seconden;
   * `cso_api` -- nooit automatisch, want de benodigde credentials
     komen uit `.env` en zeggen niets over of DEZE bron goed is
     ingesteld.

Faalt de live-check, dan wordt het opslaan geblokkeerd met de
foutmelding erbij -- met een optie "Ik weet dat de live-test nu faalt,
toch opslaan" voor het geval de doelsite tijdelijk plat ligt. Een
structurele fout (ongeldige JSON, ontbrekend verplicht veld) heeft
geen overslaan-optie: dat moet je eerst herstellen.

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

De Docker-image bevat standaard een headless Chromium (via
Playwright) -- dit maakt de image groter (~½-1 GB extra) en de eerste
build trager dan een kale Python-image. Dit is een bewuste keuze:
"Analyseren" gebruikt die browser om JavaScript-afhankelijke
vacaturesites correct te herkennen, in plaats van dat je daar zelf pas
achter komt nadat een aanbevolen adapter live 0 resultaten blijkt te
geven.

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
```

`git pull` is hier vooral voor je eigen `.env`/`docker-compose.yml`-
aanpassingen en dit README-bestand; de daadwerkelijke applicatiecode
komt via `docker compose pull` binnen (de image die GitHub Actions
bij de laatste push naar `main` heeft gebouwd, zie "Docker image
bouwen via GitHub Actions"). De database blijft behouden.

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

├── app.py                     routes, formulierverwerking, validatie vóór opslaan
├── auth.py                    login/logout (Flask-Login)
├── config.py
├── database.py
├── models.py

├── scraper.py                 kale HTTP-fetch (o.a. raw_fetch_debug, diagnose_source)
├── browser_analysis.py        gedeelde Playwright-infrastructuur (Analyseren + browser_listing/embedded_json)
├── adapter_helper.py          orchestrator: alleen analyze()
├── signal_detection.py        Website Detective: "wat is er te zien" (JSON-LD/microdata/embedded JSON/HTML/pagination)
├── strategy_selector.py       Website Detective: "wat betekent dat" (_gather_signals/_classify)
├── diagnostics.py             "Bron testen" / "Ruwe respons bekijken" / Systeem-diagnose
├── site_fingerprint.py        cache: onthoudt eerder gedetecteerde adapter per domein
├── example_sources.py
├── export_import.py           database export/import

├── adapters/
│   ├── base.py               gedeelde helpers (settings, keyword-filter, fetch)
│   ├── registry.py           koppelt adapternamen aan modules + capabilities + validate_settings()
│   ├── generic_links.py
│   ├── html_listing.py
│   ├── jsonld_listing.py
│   ├── microdata_listing.py
│   ├── browser_listing.py    JavaScript-sites, via de gedeelde Playwright-infrastructuur
│   ├── cso_api.py
│   ├── greenhouse.py         Greenhouse Job Board API, automatisch gedetecteerd
│   ├── discovered_api.py     hergebruikt een via Analyseren ontdekt JSON-endpoint
│   ├── embedded_json.py      hergebruikt een hydration-payload uit de pagina-bron
│   └── EXAMPLES.md           configuratievoorbeelden per adapter

├── notifications.py
├── backup.py

├── services/
│   ├── vacancy_checker.py
│   ├── scheduler_service.py
│   └── notification_service.py

├── tests/                    pytest -- zie sectie "Testen" hieronder
│   ├── test_strategy_selector.py          _classify()-precedentie (incl. discovered_api/embedded_json)
│   ├── test_greenhouse_adapter.py
│   ├── test_source_scheduling.py
│   ├── test_html_listing_link_attr.py     onclick-widgets (bv. Werken bij Wassenaar)
│   ├── test_raw_fetch_debug.py            "Ruwe respons bekijken"
│   ├── test_browser_analysis.py           Playwright-navigatie (gemockt)
│   ├── test_browser_analysis_requests.py  netwerkverkeer-opvang tijdens analyse (gemockt)
│   ├── test_embedded_json.py              detectie van hydration-payloads (Next.js/Nuxt)
│   ├── test_embedded_json_adapter.py      adapters/embedded_json.py (fetch/parse)
│   ├── test_discovered_api.py
│   └── test_source_validation.py          validatie vóór opslaan (structureel + live)

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

Het project heeft een `pytest`-testsuite (149 tests) voor de
detectielogica van de Adapter Helper (inclusief de `discovered_api`-
en `embedded_json`-precedentie), de adapters zelf, de weekdag-
planning, de `onclick`-widget-ondersteuning in `html_listing` (zie
Werken bij Wassenaar), "Ruwe respons bekijken", de Playwright-
aansturing in `browser_analysis.py`, en de validatie vóór opslaan
(structureel + live, inclusief de always/opt_in/skip-policy per
adapter). Alleen nodig voor ontwikkeling, niet voor gewoon gebruik --
de Docker-image bevat `pytest` niet.

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
* Playwright (headless Chromium, voor Analyseren/`browser_listing`/`embedded_json`)
* Docker

---

# Beperkingen

* Sommige vacaturepagina's laden inhoud via JavaScript; "Analyseren"
  herkent dit automatisch (gebruikt altijd een echte browser), maar
  voor de geplande controles moet je zelf nog `browser_listing` of
  `embedded_json` kiezen -- zwaarder qua resources (een echte
  browserpagina per controle) dan de andere adapters.
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
* `discovered_api` en `embedded_json` gebruiken een ONOFFICIEEL,
  intern JSON-endpoint respectievelijk een hydration-payload van de
  website zelf (geen gedocumenteerde publieke API) -- dit kan zonder
  aankondiging veranderen. Test na het instellen altijd met "Bron
  testen", en houd er rekening mee dat dit vaker onderhoud kan vragen
  dan `cso_api`/`greenhouse`.
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
* [ ] `browser_listing`/`embedded_json`: detailpagina-modus (mode
      "detail", zoals `jsonld_listing`/`microdata_listing` al hebben)
* [ ] Tweede platform-adapter (bv. Workday) bovenop de
      fingerprint-aanpak uit `greenhouse.py`
* [ ] `generic_links` positioneren als allerlaatste redmiddel in de
      detectie-precedentie (staat nu op gelijke voet met de andere
      fallbacks)
* [ ] `browser_listing` herontwerpen als losse fetch-strategie
      (herbruikbaar door andere adapters) in plaats van een eigen
      adapter -- architecturaal zuiverder, maar raakt de
      schema-/UI-laag
* [ ] Robots.txt-check inbouwen in `scraper.fetch_html()`
* [ ] CSRF-bescherming (Flask-WTF)
* [ ] Overstap naar Flask-Migrate/Alembic voor toekomstige
      schema-wijzigingen
* [ ] Meerdere gebruikers
* [ ] API voor externe integraties

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
