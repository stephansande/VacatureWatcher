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
| `generic_links` | simpele "vacature-achtige" links (v1-aanpak) | nee | nee | nee | nee | nee | nee |
| `cso_api` | CSO Vacature-API (Werken voor Nederland e.a.) | nee | ja | nee | nee | nee | ja |

Dit overzicht staat ook live in de applicatie onder **Systeem →
Adapters**, inclusief hoeveel bronnen elke adapter op dit moment
gebruiken.

### Adapter Helper

Bij het toevoegen of wijzigen van een bron kun je op "Analyseren"
klikken. De applicatie haalt de pagina dan één keer op en probeert, in
volgorde van voorkeur:

1. JSON-LD (schema.org JobPosting)
2. Microdata (schema.org, als HTML-attributen)
3. Een herhalend HTML-blok rond vacature-achtige links -- of, als dat
   niets oplevert, rond herhalende koppen (`<h2>`/`<h3>`/`<h4>`)
4. Generieke links (werkt bijna altijd wel een beetje)

Voor elke kandidaat die iets vindt, zie je een preview van de
gevonden vacatures (titel, en waar mogelijk locatie/datum) vóórdat je
iets opslaat -- de Adapter Helper gokt niet stilzwijgend, hij laat
zien wat elke aanpak daadwerkelijk oplevert. Paginering wordt apart
gedetecteerd en waar mogelijk automatisch meegenomen.

Belangrijk: deze detectie draait alléén als je zelf op "Analyseren"
klikt. De geplande controles draaien op de vaste selectors die je
opslaat, niet op een herhaalde live gok -- dat houdt het gedrag van
een bron voorspelbaar.

### Bron testen

Op de detailpagina van een bron kun je "Bron testen" gebruiken: dit
voert de echte adapter uit, laat de eerste vijf gevonden vacatures
zien plus het totaal, en toont eventuele fouten direct. Er wordt
niets opgeslagen en er gaan geen meldingen uit -- handig om een
nieuwe configuratie te checken zonder een volledige controle te
starten.

### Bronstatus

Elke bron toont een statusoverzicht: laatste controle, laatste
geslaagde controle, aantal (actieve) vacatures, aantal nieuwe
vacatures bij de laatste geslaagde controle, de gebruikte adapter, en
de laatste foutmelding (indien van toepassing).

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

## Installatie

```bash
git clone https://github.com/<gebruikersnaam>/vacaturewatcher.git
cd vacaturewatcher
cp .env.example .env
nano .env
docker compose up -d --build
docker ps
docker logs -f vacaturewatcher
```

## Bestaande installatie bijwerken naar v2

Als je al vacatures/werkgevers had opgeslagen (v1, of een eerdere
v2-tussenversie), draai dan **eenmalig** het migratiescript voordat je
de nieuwe code voor het eerst start:

```bash
python migrate_v1_to_v2.py
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

Klik op **Analyseren** om de Adapter Helper de pagina te laten testen,
kies een van de voorgestelde instellingen (of laat "generic_links"
staan voor een simpele werkgeverspagina), en sla op. Gebruik daarna
**Bron testen** op de detailpagina om snel te checken of het werkt,
of **Nu controleren** voor een volledige scan (inclusief opslaan en
meldingen).

---

# Configuratie

De configuratie staat in `.env`:

```env
APP_NAME=VacatureWatcher

SECRET_KEY=verander_dit

DATABASE_PATH=data/vacaturewatcher.db


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
python migrate_v1_to_v2.py
docker compose down
docker compose up -d --build
```

De database blijft behouden. Vergeet de migratiestap niet als je van
een oudere versie komt (zie hierboven) -- draai die vóór je de
container herstart.

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

├── app.py
├── config.py
├── database.py
├── models.py

├── scraper.py
├── adapter_helper.py
├── example_sources.py
├── vacancy_parser.py        (legacy, vervangen door adapters/generic_links.py)
├── comparer.py               (legacy, ongebruikt)

├── adapters/
│   ├── base.py               gedeelde helpers (settings, keyword-filter, fetch)
│   ├── registry.py           koppelt adapternamen aan modules + capabilities
│   ├── generic_links.py
│   ├── html_listing.py
│   ├── jsonld_listing.py
│   ├── microdata_listing.py
│   ├── cso_api.py
│   └── EXAMPLES.md           configuratievoorbeelden per adapter

├── notifications.py
├── backup.py
├── migrate_v1_to_v2.py

├── services/
│   ├── vacancy_checker.py
│   ├── scheduler_service.py
│   └── notification_service.py

├── templates/
├── static/

├── data/

├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
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

* Sommige vacaturepagina's laden inhoud via JavaScript; dit soort
  pagina's kan een headless browser vereisen, wat VacatureWatcher niet
  ingebouwd heeft.
* Sommige websites blokkeren geautomatiseerde toegang (robots.txt) of
  verbieden scraping in hun voorwaarden -- controleer dit zelf per
  site voordat je een bron toevoegt.
* De `html_listing`-heuristiek van de Adapter Helper is een gok op
  basis van herhalende structuur; controleer altijd de preview
  voordat je opslaat.
* Geplande controles gebruiken vaste, opgeslagen selectors -- als een
  site van structuur verandert, moet je de bron opnieuw analyseren
  ("Hertest"/Analyseren), dit gebeurt niet automatisch.
* `cso_api` extraheert nog geen locatie/datum (de API levert dit wel,
  maar het exacte veldpad is nog niet geverifieerd -- zie de
  toelichting in `adapters/cso_api.py`).

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
* [ ] Browser automation voor JavaScript-zware pagina's
* [ ] Overstap naar Flask-Migrate/Alembic i.p.v. handmatige
      migratiescripts
* [ ] Meerdere gebruikers
* [ ] API voor externe integraties
* [ ] Docker image publiceren

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
