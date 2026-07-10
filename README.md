# VacatureWatcher

Een eenvoudige self-hosted applicatie om vacaturepagina's van verschillende werkgevers automatisch te controleren en wijzigingen te detecteren.

VacatureWatcher is bedoeld voor tijdelijk of langdurig gebruik wanneer je meerdere werkgevers wilt volgen zonder handmatig alle vacaturepagina's te moeten controleren.

De applicatie draait volledig lokaal via Docker en bewaart alle gegevens in een lokale SQLite database.

---

## Functies

### Werkgevers beheren

* Meerdere werkgevers toevoegen
* Eigen vacature-URL per werkgever instellen
* Werkgevers wijzigen of verwijderen
* Handmatige controle starten

### Vacaturecontrole

* Automatisch controleren van vacaturepagina's
* Dagelijkse controle
* Wekelijkse controle
* Nieuwe vacatures detecteren
* Verwijderde vacatures detecteren
* Historie van wijzigingen bewaren

### Zoekwoordenfilter

Per werkgever kunnen zoekwoorden worden ingesteld.

Voorbeeld:

```
ict, netwerk, beheer, asset, data
```

Alleen vacatures waarin één van deze woorden voorkomt worden als relevant beschouwd.

### Meldingen

Ondersteuning voor:

* Consolemeldingen
* E-mailmeldingen
* Telegrammeldingen

Meldingen worden verstuurd bij:

* Nieuwe vacatures
* Verdwenen vacatures

### Back-up

* Automatische database back-ups
* Handmatig back-up maken vanuit de webinterface
* SQLite database blijft behouden bij Docker updates

---

# Installatie met Docker

## Vereisten

* Docker
* Docker Compose

Getest met:

* Docker Engine
* Docker Compose v2
* Linux / OpenMediaVault

---

## Installatie

Clone de repository:

```bash
git clone https://github.com/<gebruikersnaam>/vacaturewatcher.git

cd vacaturewatcher
```

Maak een configuratiebestand:

```bash
cp .env.example .env
```

Pas eventueel de instellingen aan:

```bash
nano .env
```

Start de applicatie:

```bash
docker compose up -d --build
```

Controleer de status:

```bash
docker ps
```

Bekijk logs:

```bash
docker logs -f vacaturewatcher
```

---

# Gebruik

Open de webinterface:

```
http://<server-ip>:1276
```

Voorbeeld:

```
http://192.168.1.100:1276
```

---

# Eerste werkgever toevoegen

Ga naar:

```
Werkgever toevoegen
```

Vul in:

| Veld        | Voorbeeld                        |
| ----------- | -------------------------------- |
| Naam        | Gemeente Rotterdam               |
| URL         | https://www.website.nl/vacatures |
| Zoekwoorden | ict, netwerk, beheer             |
| Controle    | Dagelijks                        |

Opslaan.

De eerste controle kan handmatig gestart worden.

---

# Configuratie

De configuratie staat in:

```
.env
```

Voorbeeld:

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
```

---

# E-mail notificaties

Voorbeeld:

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

---

# Telegram notificaties

Maak een Telegram bot via:

https://core.telegram.org/bots

Vul daarna in:

```env
TELEGRAM_ENABLED=true

TELEGRAM_TOKEN=<bot-token>

TELEGRAM_CHAT_ID=<chat-id>
```

---

# Data opslag

Alle gegevens worden opgeslagen in:

```
data/
```

Structuur:

```
data/

├── vacaturewatcher.db
└── backups/
    ├── vacaturewatcher_20260710.db
    └── ...
```

De map `data` wordt als Docker volume behouden.

---

# Back-up maken

Via de webinterface:

```
Instellingen
→ Backup maken
```

Of handmatig:

```bash
cp data/vacaturewatcher.db backup.db
```

---

# Update

Nieuwe versie ophalen:

```bash
git pull
```

Container opnieuw bouwen:

```bash
docker compose down

docker compose up -d --build
```

De database blijft behouden.

---

# Verwijderen

Stop de container:

```bash
docker compose down
```

Volledig verwijderen:

```bash
rm -rf vacaturewatcher
```

Inclusief database:

```bash
rm -rf data
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
├── vacancy_parser.py
├── comparer.py

├── notifications.py
├── backup.py

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

Gebruikte technologie:

* Python 3.12
* Flask
* SQLite
* SQLAlchemy
* APScheduler
* BeautifulSoup
* Docker

---

# Beperkingen

VacatureWatcher gebruikt eenvoudige web scraping.

Let op:

* Sommige vacaturepagina's laden inhoud via JavaScript.
* Sommige websites blokkeren automatische verzoeken.
* Complexe vacatureportalen kunnen een specifieke parser nodig hebben.

Gebruik de applicatie volgens de voorwaarden van de betreffende websites.

---

# Roadmap

Mogelijke toekomstige uitbreidingen:

* [ ] Login beveiliging
* [ ] Docker image publiceren
* [ ] Grafieken met vacaturehistorie
* [ ] RSS ondersteuning
* [ ] Browser automation voor JavaScript pagina's
* [ ] Meerdere gebruikers
* [ ] API

---

# Licentie

Dit project wordt beschikbaar gesteld onder de MIT-licentie.

Je mag:

* de software gebruiken;
* aanpassen;
* uitbreiden;
* verspreiden.

---

# Bijdragen

Pull requests en verbeteringen zijn welkom.

Bijdragen graag voorzien van:

* duidelijke beschrijving;
* testinformatie;
* eventuele screenshots.

---

# Disclaimer

VacatureWatcher is een hulpmiddel om openbare vacaturepagina's te monitoren.

Controleer altijd de gebruiksvoorwaarden van de websites die je monitort.
