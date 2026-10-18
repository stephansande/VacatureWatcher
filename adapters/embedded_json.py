"""
Adapter: embedded_json

Hergebruikt een JSON-hydration-payload die tijdens "Analyseren" al in
de INITIËLE HTML-bron zat (zie signal_detection._detect_embedded_json()
-- __NEXT_DATA__ voor Next.js, window.__NUXT__/__INITIAL_STATE__ voor
Nuxt/overig). Anders dan discovered_api.py (dat een los JSON-endpoint
opnieuw kan opvragen met een gewone requests.get) zit deze data VAST
in de gerenderde hoofdpagina -- er is dus geen los endpoint om aan te
roepen. fetch() rendert de pagina daarom opnieuw met Playwright (via
browser_analysis.fetch_rendered_html(), hetzelfde pad als "Analyseren"
gebruikt) en parse() haalt de payload er vervolgens weer uit, met
signal_detection.extract_embedded_json_candidates() -- dezelfde
extractie die de analysestap ook gebruikt, zodat een geplande controle
nooit een ander stuk JSON tegenkomt dan wat er bij "Analyseren" te
zien was.

BELANGRIJK: net als bij discovered_api.py is dit GEEN gedocumenteerde,
stabiele API -- het is een implementatiedetail van hoe de site zijn
eigen pagina rendert, en kan zonder aankondiging veranderen (een
andere sleutelnaam, een verschoven pad). Test na het instellen altijd
met "Bron testen".

CONFIGURATIE (Source.settings, als JSON):
{
    "items_path": ["props", "pageProps", "vacatures"],
    // verplicht: sleutelpad (LIJST, niet 1 string zoals bij
    // discovered_api.items_path) naar de vacature-array binnen de
    // gevonden JSON-payload. Een hydration-payload zit vrijwel altijd
    // dieper genest dan een kale API-respons -- vandaar een pad i.p.v.
    // een enkele sleutel, zie signal_detection._find_job_array_in_json().
    "base_url": "https://voorbeeld.nl",  // optioneel: voor relatieve vacature-URL's
    "field_map": {
        "title": "titel",        // verplicht: JSON-veldnaam voor de titel
        "url": "link",           // verplicht: JSON-veldnaam voor de vacature-URL
        "content": "omschrijving",  // optioneel, valt terug op de titel
        "location": "locatie",      // optioneel
        "date": "geplaatst_op"      // optioneel
    }
}

"items_path" wordt automatisch ingevuld door de "Gebruik deze
instellingen"-knop bij een gevonden embedded-JSON-kandidaat op de
bronpagina -- "field_map" blijft daarbij LEEG, exact dezelfde bewuste
keuze als bij discovered_api.py: welke JSON-sleutel bij welk
vacature-veld hoort is per site anders en wordt niet geraden. Bekijk
de preview op de bronpagina (of "Ruwe respons bekijken") om de juiste
veldnamen te vinden.

Waarom geen eigen "eenvoudigere" implementatie voor de veld-mapping
(title/url/content/location/date uit field_map halen)? Die logica is
functioneel identiek aan discovered_api.parse() -- bewust toch als
eigen kopie hier i.p.v. een gedeelde helper, in lijn met hoe de
overige adapters in dit bestand elk zelfstandig blijven (zie
adapters/base.py's moduledocstring): een toekomstige wijziging aan
"hoe embedded_json zijn velden mapt" hoeft zo niet uit te sluiten dat
die twee ooit toch uiteenlopen (bv. als embedded_json ooit geneste
veldpaden in field_map zou moeten ondersteunen, wat discovered_api
bewust niet doet).
"""

import browser_analysis
import signal_detection as sd

from urllib.parse import urljoin

from adapters.base import load_settings, require, AdapterError


CAPABILITIES = {
    "label": "Embedded JSON in de pagina-bron (hydration-payload, bv. Next.js/Nuxt)",
    "supports_pagination": False,
    "supports_categories": False,
    "supports_detail_pages": False,
    "supports_dates": True,
    "supports_location": True,
    "requires_credentials": False,
    "live_validation": "opt_in",
    # fetch() start een headless Chromium (zie hieronder) -- zelfde
    # afweging als browser_listing: te traag/onzeker voor een
    # automatische check bij elke opslag, de gebruiker vinkt het zelf
    # aan als ze dat willen (zie source_edit.html).
}


def validate_settings(settings, url):
    """
    Structurele check vóór opslaan: items_path moet aanwezig én een
    lijst van strings zijn (zie parse()'s eigen runtime-check
    hieronder, die dit nogmaals afdwingt voor het geval iemand settings
    buiten de UI om bewerkt). field_map wordt hier bewust NIET
    gecontroleerd -- zelfde redenering als discovered_api.py: een leeg
    field_map is geldige JSON, en de live-validatie geeft daar al een
    precieze foutmelding voor.
    """

    items_path = settings.get("items_path")

    if not items_path:
        return (
            "settings.items_path ontbreekt (verplicht voor deze adapter -- "
            "vul 'm via \"Analyseren\" -> \"Gebruik deze instellingen\" in, "
            "of handmatig als lijst van sleutels)."
        )

    if not isinstance(items_path, list) or not all(isinstance(key, str) for key in items_path):
        return (
            "settings.items_path moet een lijst van sleutels zijn (bv. "
            "[\"props\", \"pageProps\", \"vacatures\"]), niet "
            f"{type(items_path).__name__}."
        )

    return None


def settings_from_embedded_json_candidate(candidate):
    """
    Bouwt een settings-voorstel op basis van
    analysis["embedded_json"] (zie signal_detection._detect_embedded_json()).
    "field_map" blijft BEWUST leeg -- zie de moduledocstring hierboven.

    Gedeeld door twee aanroepers, zodat ze exact dezelfde
    voorstel-vorm opleveren (zelfde opzet als
    discovered_api.settings_from_discovered_request()):
    - app.py's "Gebruik deze instellingen"-knop bij de embedded-JSON-
      sectie (via de generieke apply:-knop-infrastructuur)
    - strategy_selector._classify()/adapter_helper.analyze() (automatische
      aanbeveling, als embedded_json wint)
    """

    return {
        "items_path": list(candidate.get("path") or []),
        "field_map": {
            "title": "",
            "url": "",
        },
    }


def fetch(source):
    """
    Rendert source.url opnieuw met Playwright -- de hydration-payload
    zit alleen in de gerenderde/initiële pagina, niet los op te vragen
    zoals bij discovered_api.py. Geeft de ruwe HTML terug (nog niet de
    JSON zelf, dat gebeurt in parse(), naar het patroon van de andere
    adapters -- zie adapters/base.py's moduledocstring).
    """

    try:
        return browser_analysis.fetch_rendered_html(source.url)
    except browser_analysis.BrowserUnavailableError as error:
        raise AdapterError(
            f"Kon '{source.name}' niet renderen: {error}"
        ) from error


def parse(html, source):

    settings = load_settings(source)

    items_path = require(settings, "items_path", source.name)

    if not isinstance(items_path, list) or not all(isinstance(key, str) for key in items_path):
        raise AdapterError(
            f"settings.items_path van '{source.name}' moet een lijst van "
            f"sleutels zijn (bv. [\"props\", \"pageProps\", \"vacatures\"]), "
            f"niet {type(items_path).__name__} -- dit is anders dan "
            f"discovered_api.items_path (daar is het één string)."
        )

    field_map = settings.get("field_map") or {}
    base_url = settings.get("base_url") or source.url

    candidates = sd.extract_embedded_json_candidates(html)

    if not candidates:
        raise AdapterError(
            f"Geen embedded JSON (__NEXT_DATA__/__NUXT__/__INITIAL_STATE__) "
            f"gevonden in de pagina-bron van '{source.name}' -- de site-"
            f"structuur is mogelijk veranderd sinds deze bron werd "
            f"ingesteld. Analyseer de bron opnieuw."
        )

    last_error = None

    for framework_label, data in candidates:

        try:
            items = _extract_items(data, items_path, source.name)
        except AdapterError as error:
            # Kan de "verkeerde" kandidaat zijn als een pagina toevallig
            # meerdere hydration-blobs bevat -- probeer de volgende
            # kandidaat vóór we de fout van de eerste teruggeven.
            last_error = error
            continue

        return _items_to_vacancies(items, field_map, base_url, source.name)

    raise last_error


def _extract_items(data, items_path, source_name):
    """
    Navigeert stap voor stap door `items_path` (een LIJST van
    sleutels, in tegenstelling tot discovered_api._extract_items() dat
    één enkele sleutel kent) naar de vacature-array binnen `data`.
    """

    current = data
    walked = []

    for key in items_path:

        walked.append(key)

        if not isinstance(current, dict) or key not in current:
            raise AdapterError(
                f"settings.items_path {items_path} van '{source_name}' wijst "
                f"niet naar een geldig pad in de embedded JSON (vastgelopen "
                f"bij '{'.'.join(str(part) for part in walked)}'). Aanwezige "
                f"velden op dit niveau: "
                f"{', '.join(str(k) for k in current.keys()) if isinstance(current, dict) else type(current).__name__}."
            )

        current = current[key]

    if not isinstance(current, list):
        raise AdapterError(
            f"settings.items_path {items_path} van '{source_name}' wijst "
            f"niet naar een JSON-array in de embedded JSON (kreeg een "
            f"{type(current).__name__})."
        )

    return current


def _items_to_vacancies(items, field_map, base_url, source_name):
    """
    Zet de gevonden vacature-array om naar vacancy-dicts aan de hand
    van field_map -- zelfde title/url-verplicht,
    content/location/date-optioneel-opzet als discovered_api.parse().
    """

    title_field = field_map.get("title", "title")
    url_field = field_map.get("url", "url")
    content_field = field_map.get("content")
    location_field = field_map.get("location")
    date_field = field_map.get("date")

    vacancies = []

    for index, item in enumerate(items):

        if not isinstance(item, dict):
            continue

        title = item.get(title_field)
        raw_url = item.get(url_field)

        if not title or not raw_url:

            if index == 0:
                # Het EERSTE item mist al een verplicht veld -- wijst
                # vrijwel altijd op een verkeerde field_map, niet op
                # een toevallig incompleet los item. Zelfde redenering
                # als discovered_api.parse().
                missing = []
                if not title:
                    missing.append(f"'{title_field}' (title)")
                if not raw_url:
                    missing.append(f"'{url_field}' (url)")

                raise AdapterError(
                    f"Verplicht veld ontbreekt in de embedded JSON van "
                    f"'{source_name}': {', '.join(missing)}. Aanwezige "
                    f"velden in dit item: "
                    f"{', '.join(str(k) for k in item.keys())}. Controleer "
                    f"settings.field_map aan de hand hiervan."
                )

            continue

        url = urljoin(base_url, str(raw_url))

        content_value = item.get(content_field) if content_field else None
        location_value = item.get(location_field) if location_field else None
        date_value = item.get(date_field) if date_field else None

        vacancy = {
            "title": str(title),
            "url": url,
            "content": str(content_value) if content_value else str(title),
        }

        if location_value:
            vacancy["location"] = str(location_value)

        if date_value:
            vacancy["date"] = date_value

        vacancies.append(vacancy)

    return vacancies
