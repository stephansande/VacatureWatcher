"""
Adapter: discovered_api

Hergebruikt een JSON-endpoint dat tijdens "Analyseren" is gevonden via
het opgevangen netwerkverkeer (zie browser_analysis.py,
render_page_capturing_requests()/"Ontdekt netwerkverkeer tijdens het
laden" op de bronpagina). Doet een gewone HTTP-aanroep naar dat
endpoint -- geen browser nodig voor de geplande controles, dat is nu
juist het hele punt: een site-eigen JSON-API is meestal sneller en
stabieler dan HTML-scraping (een JSON-veldnaam verandert minder vaak
dan een CSS-class bij een visuele redesign).

BELANGRIJK: dit is GEEN officiële, gedocumenteerde API zoals cso_api.py
of greenhouse.py -- het is een intern endpoint dat de website zelf
gebruikt om zijn eigen pagina te vullen. Het kan zonder aankondiging
veranderen. Test na het instellen altijd met "Bron testen", en houd
er rekening mee dat dit vaker onderhoud kan vragen dan een officiële
API.

CONFIGURATIE (Source.settings, als JSON):
{
    "endpoint_url": "https://voorbeeld.nl/api/vacatures",
    "method": "GET",                 // optioneel, standaard "GET"
    "items_path": "results",         // optioneel: sleutel waarachter de array zit
                                      // in de JSON-respons (leeg/weglaten = de
                                      // respons is zelf al een top-level array)
    "base_url": "https://voorbeeld.nl",  // optioneel: voor relatieve vacature-URL's
    "field_map": {
        "title": "functietitel",     // verplicht: JSON-veldnaam voor de titel
        "url": "link",               // verplicht: JSON-veldnaam voor de vacature-URL
        "content": "omschrijving",   // optioneel, valt terug op de titel
        "location": "plaats",        // optioneel
        "date": "geplaatst_op"       // optioneel
    }
}

"items_path" en een startvoorstel voor "endpoint_url" worden
automatisch ingevuld door de "Gebruik deze API"-knop bij een ontdekte
netwerkverkeer-kandidaat op de bronpagina -- "field_map" blijft daarbij
LEEG: welke JSON-sleutel bij welk vacature-veld hoort, is per site
anders en wordt bewust niet geraden. Bekijk de body-preview van de
ontdekte respons (of "Ruwe respons bekijken") om de juiste veldnamen
te vinden.
"""

import requests
from urllib.parse import urljoin

from adapters.base import load_settings, require, AdapterError
from scraper import DEFAULT_HEADERS


TIMEOUT = 30


CAPABILITIES = {
    "label": "Ontdekte JSON-API (via Analyseren gevonden netwerkverkeer)",
    "supports_pagination": False,
    "supports_categories": False,
    "supports_detail_pages": False,
    "supports_dates": True,
    "supports_location": True,
    "requires_credentials": False,
    "live_validation": "always",
    # Gewone HTTP-fetch naar endpoint_url, geen browser/credentials
    # nodig -- veilig om automatisch te testen bij opslaan. Dit vangt
    # ook precies het meest voorkomende foutgeval: een leeg field_map
    # dat nog niet is ingevuld na "Gebruik deze API" (zie
    # settings_from_discovered_request() hieronder).
}


def validate_settings(settings, url):
    """
    Structurele check vóór opslaan: alleen endpoint_url is hard
    vereist. field_map bewust NIET hier gecontroleerd op
    aanwezige/niet-lege title/url -- een leeg field_map is geldige,
    op-zichzelf-consistente JSON (zie settings_from_discovered_request()
    hierboven), en de live-validatie (diagnostics.test_source(), zie
    app.py) geeft daar al een duidelijke, concrete foutmelding voor
    zodra 'm daadwerkelijk uitgevoerd wordt -- dat is preciezer dan
    hier al vooraf te gokken welke velden "leeg genoeg" zijn om af te
    keuren.
    """

    if not settings.get("endpoint_url"):
        return "settings.endpoint_url ontbreekt (verplicht voor deze adapter)."

    return None


def settings_from_discovered_request(candidate):
    """
    Bouwt een settings-voorstel op basis van één entry uit
    analysis["discovered_requests"] (zie browser_analysis.py).
    "field_map" blijft BEWUST leeg -- zie de moduledocstring
    hierboven.

    Gedeeld door twee aanroepers, zodat ze exact dezelfde
    voorstel-vorm opleveren:
    - app.py's "Gebruik deze API"-knop (handmatige keuze door de
      gebruiker, elke kandidaat)
    - strategy_selector._classify()/adapter_helper.analyze() (automatische aanbeveling,
      alleen de sterkste kandidaat)
    """

    return {
        "endpoint_url": candidate.get("url", ""),
        "method": candidate.get("method") or "GET",
        "items_path": candidate.get("items_path_guess", ""),
        "field_map": {
            "title": "",
            "url": "",
        },
    }


def fetch(source):

    settings = load_settings(source)

    endpoint_url = require(settings, "endpoint_url", source.name)
    method = (settings.get("method") or "GET").upper()

    try:
        if method == "POST":
            response = requests.post(endpoint_url, headers=DEFAULT_HEADERS, timeout=TIMEOUT)
        else:
            response = requests.get(endpoint_url, headers=DEFAULT_HEADERS, timeout=TIMEOUT)
    except requests.RequestException as error:
        raise AdapterError(
            f"Kon '{source.name}' niet ophalen van {endpoint_url}: {error}"
        )

    _raise_for_http_error(response, source.name, endpoint_url)

    try:
        return response.json()
    except ValueError as error:
        raise AdapterError(
            f"Respons van {endpoint_url} ('{source.name}') is geen geldige "
            f"JSON: {error}"
        )


def parse(raw_data, source):

    settings = load_settings(source)

    items_path = settings.get("items_path") or ""
    field_map = settings.get("field_map") or {}
    base_url = settings.get("base_url") or source.url

    title_field = field_map.get("title", "title")
    url_field = field_map.get("url", "url")
    content_field = field_map.get("content")
    location_field = field_map.get("location")
    date_field = field_map.get("date")

    items = _extract_items(raw_data, items_path, source.name)

    vacancies = []

    for index, item in enumerate(items):

        if not isinstance(item, dict):
            continue

        title = item.get(title_field)
        raw_url = item.get(url_field)

        if not title or not raw_url:

            if index == 0:
                # Het EERSTE item mist al een verplicht veld -- dat
                # wijst vrijwel altijd op een verkeerde field_map,
                # niet op een toevallig incompleet los item. Duidelijke
                # fout in plaats van stilzwijgend 0 resultaten (precies
                # het soort verwarring dat we bij Werk bij Dunea
                # tegenkwamen met een verouderde CSS-selector).
                missing = []
                if not title:
                    missing.append(f"'{title_field}' (title)")
                if not raw_url:
                    missing.append(f"'{url_field}' (url)")

                raise AdapterError(
                    f"Verplicht veld ontbreekt in de respons van '{source.name}': "
                    f"{', '.join(missing)}. Aanwezige velden in dit item: "
                    f"{', '.join(str(k) for k in item.keys())}. Controleer "
                    f"settings.field_map aan de hand hiervan."
                )

            # Latere items die toevallig incompleet zijn: gewoon
            # overslaan, net als bij de andere adapters.
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


def _extract_items(data, items_path, source_name):
    """
    Navigeert naar de vacature-array in `data` aan de hand van
    `items_path` (een enkele sleutelnaam, bv. "results" -- geen diep
    geneste dot-paden in deze eerste versie). Lege `items_path`
    betekent: `data` is zelf al de array.
    """

    if not items_path:
        current = data
    else:
        if not isinstance(data, dict) or items_path not in data:
            raise AdapterError(
                f"settings.items_path '{items_path}' wijst niet naar een geldig "
                f"pad in de JSON-respons van '{source_name}'. Aanwezige "
                f"velden op het top-niveau: "
                f"{', '.join(str(k) for k in data.keys()) if isinstance(data, dict) else type(data).__name__}."
            )
        current = data[items_path]

    if not isinstance(current, list):
        raise AdapterError(
            f"settings.items_path{f' (\"{items_path}\")' if items_path else ''} "
            f"wijst niet naar een JSON-array in de respons van '{source_name}' "
            f"(kreeg een {type(current).__name__})."
        )

    return current


def _raise_for_http_error(response, source_name, endpoint_url):

    if response.status_code == 200:
        return

    raise AdapterError(
        f"'{source_name}': fout bij ophalen van {endpoint_url} "
        f"({response.status_code}): {response.text[:200]}"
    )
