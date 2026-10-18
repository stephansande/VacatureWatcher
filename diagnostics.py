"""
diagnostics.py

De "laat zien wat er gebeurt"-laag: functies die een BESTAANDE,
opgeslagen bron testen/diagnosticeren -- een ander soort taak dan
analyse (die juist bepaalt WELKE adapter/instellingen bij een NIEUWE
bron passen, zie adapter_helper.analyze() en strategy_selector.py).

- diagnose_source() / test_source(): draaien de echte adapter van een
  bron, zonder iets op te slaan of te notificeren ("Bron testen",
  en de bulk-variant "Systeem -> Diagnose").
- raw_fetch_debug(): "Ruwe respons bekijken" -- een kale HTTP-fetch
  zonder adapter ertussen, specifiek om te kunnen vergelijken wat een
  script ziet t.o.v. wat een browser ziet (zie het Werk bij
  Dunea-scenario in de projectgeschiedenis).

Afkomstig uit adapter_helper.py, zie signal_detection.py voor de
volledige toelichting op de opsplitsing.
"""

import json
from types import SimpleNamespace

from bs4 import BeautifulSoup

from scraper import fetch_html

from adapters import registry
from adapters.base import load_settings, get_keyword_filters, apply_keyword_filter, AdapterError

from signal_detection import _suspect_js_rendering


TEST_PREVIEW_LIMIT = 5

LINK_LIST_LIMIT = 60
# Maximum aantal <a href>'s dat raw_fetch_debug() volledig oplijst
# (href + class + tekst). Boven dit aantal wordt alleen het totaal
# getoond -- zie result["links_truncated"].


def diagnose_source(source, limit=TEST_PREVIEW_LIMIT):
    """
    Zoals test_source(), maar met een categorisering van het resultaat
    erbovenop -- bedoeld voor de bulk-diagnosepagina (Systeem ->
    Bronnen diagnosticeren), zodat je in één keer een overzicht krijgt
    van AL je bronnen in plaats van er één voor één doorheen te moeten
    (zoals we net handmatig deden voor dierenbescherming.nl).

    category is een van: "ok", "geen_resultaten", "fout".
    hint is een korte, mens-leesbare duiding -- bij "geen_resultaten"
    een VERMOEDEN (nooit een zekerheid) of het om JavaScript-rendering
    kan gaan.
    """

    result = test_source(source, limit=limit)

    diagnosis = {
        "source_id": getattr(source, "id", None),
        "source_name": source.name,
        "adapter": source.adapter,
        "error": result["error"],
        "count": result["count"],
        "preview": result["preview"],
        "category": None,
        "hint": None,
    }

    if result["error"]:
        diagnosis["category"] = "fout"
        diagnosis["hint"] = _classify_error(result["error"])

    elif result["count"] == 0:
        diagnosis["category"] = "geen_resultaten"
        diagnosis["hint"] = _suspect_js_rendering_for_url(source.url)

    else:
        diagnosis["category"] = "ok"

    return diagnosis


def _suspect_js_rendering_for_url(url):
    """
    Wrapper om _suspect_js_rendering() te gebruiken vanuit
    diagnose_source(), waar de HTML nog niet is opgehaald (in
    tegenstelling tot analyze(), dat 'm al in huis heeft).
    """

    try:
        html = fetch_html(url)
    except Exception:
        return (
            "Geen vacatures gevonden, en de pagina kon niet nogmaals "
            "opgehaald worden om verder te duiden."
        )

    hint = _suspect_js_rendering(html)

    if hint:
        return hint

    return (
        "Geen vacatures gevonden, maar geen duidelijk signaal van "
        "JavaScript-rendering -- controleer de adapter-instellingen "
        "(selectors/mode) via Analyseren op de bewerkpagina."
    )


def _classify_error(error_message):

    lowered = error_message.lower()

    if "404" in lowered:
        return "Pagina niet gevonden (404) -- klopt de URL nog?"

    if "403" in lowered:
        return "Toegang geweigerd (403) -- de site blokkeert mogelijk geautomatiseerde toegang."

    if "timeout" in lowered or "timed out" in lowered:
        return "Time-out -- de site reageerde niet op tijd."

    if "onbekende adapter" in lowered:
        return "De ingestelde adapter bestaat niet (meer) -- controleer de bron-instellingen."

    if "json" in lowered:
        return "Het settings-veld van deze bron bevat geen geldige JSON."

    return "Zie de volledige foutmelding hiernaast."


def test_source(source, limit=TEST_PREVIEW_LIMIT):
    """
    Voert de daadwerkelijke adapter van een bestaande Source uit
    ("Bron testen"-knop), maar dan licht: paginering/detail-fetches
    worden tijdelijk beperkt zodat een test geen volledige scrape
    van de doelsite triggert. Doet GEEN database-writes en verstuurt
    GEEN notificaties -- puur lezen en tonen.

    Hergebruikt exact dezelfde adapter + settings + keyword-filter-
    pijplijn als de echte geplande controle (services/vacancy_checker.py),
    zodat "Bron testen" representatief is voor wat een scan zou vinden.
    """

    result = {
        "error": None,
        "count": 0,
        "preview": [],
    }

    try:
        adapter = registry.get(source.adapter)
    except AdapterError as error:
        result["error"] = str(error)
        return result

    test_settings_json = _cap_settings_for_test(source.settings, limit)

    test_source_obj = SimpleNamespace(
        id=getattr(source, "id", None),
        name=source.name,
        url=source.url,
        adapter=source.adapter,
        settings=test_settings_json,
        keywords=source.keywords,
    )

    try:
        raw_content = adapter.fetch(test_source_obj)
        vacancies = adapter.parse(raw_content, test_source_obj)

        settings = load_settings(test_source_obj)
        include_keywords, exclude_keywords = get_keyword_filters(test_source_obj, settings)

        vacancies = apply_keyword_filter(
            vacancies,
            include_keywords=include_keywords,
            exclude_keywords=exclude_keywords,
        )

        result["count"] = len(vacancies)
        result["preview"] = vacancies[:limit]

    except AdapterError as error:
        result["error"] = str(error)
    except Exception as error:
        result["error"] = f"Onverwachte fout: {error}"

    return result


def raw_fetch_debug(source):
    """
    Haalt de bron-URL rechtstreeks op met dezelfde fetch_html() die
    alle adapters gebruiken, en geeft de RUWE respons terug -- lengte,
    een voorbeeld van de eerste tekens, een voorzichtige hint of de
    respons op een blokkade lijkt, ÉN (als er een "selectors.item" in
    de instellingen staat) hoeveel elementen die selector in DEZE
    verse respons matcht. Dat laatste is toegevoegd na het Werk bij
    Dunea-scenario: nadat bleek dat de respons zelf prima binnenkwam
    (geen blokkade, normale lengte), was de volgende, voor de hand
    liggende vraag "matcht mijn selector hier dan wel iets in?" --
    zonder dat je 2000 tekens HTML handmatig hoeft door te zoeken.

    "looks_blocked" is een HINT, geen zekerheid -- gebaseerd op een
    ongebruikelijk korte respons of een paar veelvoorkomende
    bot-detectie-teksten. Beoordeel de preview altijd zelf; dit
    voorkomt alleen dat je die met de hand hoeft te doorzoeken.
    """

    result = {
        "url": None,
        "error": None,
        "length": None,
        "preview": None,
        "looks_blocked": None,
        "link_count": None,
        "links": None,
        "links_truncated": None,
        "item_selector": None,
        "item_selector_matches": None,
    }

    settings = load_settings(source)
    url = settings.get("start_url") or source.url
    result["url"] = url

    try:
        html = fetch_html(url)
    except Exception as error:
        result["error"] = str(error)
        return result

    result["length"] = len(html)
    result["preview"] = html[:2000]

    lowered = html.lower()
    blocked_hints = [
        "captcha",
        "access denied",
        "are you a robot",
        "just a moment",
        "attention required",
        "checking your browser",
    ]
    result["looks_blocked"] = (
        len(html) < 1000
        or any(hint in lowered for hint in blocked_hints)
    )

    soup = BeautifulSoup(html, "lxml")
    all_links = soup.find_all("a", href=True)
    result["link_count"] = len(all_links)

    # Bij een klein aantal links (zoals bij Werk bij Dunea: 24) is een
    # volledige lijst met href + class veel bruikbaarder dan een
    # afgekapte HTML-preview van de eerste 2000 tekens -- die preview
    # bevat bij een lange pagina vaak alleen de <head>, terwijl de
    # vacatures verderop staan. Bewust een limiet (LINK_LIST_LIMIT)
    # om deze pagina bij honderden links niet onbruikbaar traag/lang
    # te maken.
    result["links"] = [
        {
            "href": a.get("href"),
            "class": " ".join(a.get("class") or []) or None,
            "text": a.get_text(" ", strip=True)[:60],
        }
        for a in all_links[:LINK_LIST_LIMIT]
    ]
    result["links_truncated"] = len(all_links) > LINK_LIST_LIMIT

    item_selector = (settings.get("selectors") or {}).get("item")
    result["item_selector"] = item_selector

    if item_selector:
        try:
            result["item_selector_matches"] = len(soup.select(item_selector))
        except Exception as error:
            # een ongeldige/onverwachte CSS-selector mag deze
            # diagnosepagina niet laten crashen -- toon de fout in
            # plaats van een aantal
            result["item_selector_matches"] = f"FOUT bij toepassen selector: {error}"

    return result


def _cap_settings_for_test(settings_json, limit):
    """
    Beperkt pagination.max_pages, max_items en max_rows (indien
    aanwezig) tot maximaal `limit`, zodat een test-run geen zware
    meerdere-pagina's-scrape of tientallen detail-page-requests
    veroorzaakt. Laat settings ongewijzigd als er niets te beperken
    valt of als de JSON ongeldig is (dan merkt de echte adapter dat
    zelf op).
    """

    if not settings_json:
        return settings_json

    try:
        data = json.loads(settings_json)
    except (ValueError, TypeError):
        return settings_json

    if not isinstance(data, dict):
        return settings_json

    if isinstance(data.get("pagination"), dict):
        data["pagination"] = dict(data["pagination"])
        current_max = data["pagination"].get("max_pages", limit)
        data["pagination"]["max_pages"] = min(current_max, limit)

    for key in ("max_items", "max_rows"):
        if key in data:
            data[key] = min(data[key], limit)

    return json.dumps(data)
