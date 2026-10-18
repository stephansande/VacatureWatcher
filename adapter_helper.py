"""
Adapter Helper -- de orchestrator van de Website Detective.

Doel: iemand die een nieuwe vacaturesite wil toevoegen, hoeft niet
zelf CSS-selectors te gaan zoeken in devtools. Geef een URL op, en
analyze():

  1. checkt eerst site_fingerprint.py voor een eerder, vers
     geanalyseerd resultaat van hetzelfde domein (cache)
  2. rendert de pagina anders met een echte browser
     (browser_analysis.py) en vangt tegelijk XHR/fetch-netwerkverkeer op
  3. laat signal_detection.py de HTML/het verkeer onderzoeken op
     JSON-LD, microdata, een herhalend HTML-blok, generieke links,
     paginering en ontdekte JSON-endpoints
  4. laat strategy_selector.py beslissen welke adapter wint
  5. bouwt op basis daarvan een kant-en-klaar settings-voorstel

Dit bestand zelf bevat sinds de opsplitsing (zie signal_detection.py's
docstring voor de aanleiding: 1347 regels, 30 functies door elkaar)
alleen nog analyze() -- de daadwerkelijke detectie-/beslissingslogica
staat in:
  - signal_detection.py  -- "wat is er te zien" (pure waarneming)
  - strategy_selector.py -- "wat betekent dat" (welke adapter wint)
  - diagnostics.py        -- "Bron testen"/"Ruwe respons bekijken"/
                              "Systeem -> Diagnose" (een bestaande
                              bron testen, andere taak dan analyse)

Dit is dus geen slimme AI-gok: het is "probeer de bekende patronen en
laat zien wat elk patroon daadwerkelijk oplevert", zodat de gebruiker
zelf op basis van de preview kan beoordelen welke adapter/instellingen
het beste passen voordat hij ze opslaat.

Belangrijk ontwerpprincipe: deze detectie draait ALLEEN als de
gebruiker op "Analyseren" klikt. De geplande controles
(services/vacancy_checker.py) draaien op de vaste, opgeslagen
selectors uit Source.settings -- niet op een live herhaalde gok bij
elke controle. Dat houdt het gedrag van een bron voorspelbaar: als een
scan andere resultaten geeft, is dat een wijziging op de site, niet
een andere gok van de heuristiek.
"""

import json

from bs4 import BeautifulSoup

import site_fingerprint
import browser_analysis
from adapters import greenhouse
from adapters import discovered_api
from adapters import embedded_json

from strategy_selector import _gather_signals, _classify


def analyze(url, force_refresh=False):
    """
    Voert alle detecties uit voor één URL. Geeft altijd een dict terug
    (nooit een exception) zodat de aanroepende route dit veilig direct
    in een template kan tonen.
    """

    result = {
        "url": url,
        "fetch_error": None,
        "jsonld": None,
        "microdata": None,
        "html_listing": None,
        "generic_links": None,
        "pagination": None,
        "meta_generator": None,
        "script_domains": [],
        "js_rendering_hint": None,
        "recommendation": None,
        "from_cache": False,
        "cache_confidence": None,
        "cached_settings": None,
        "recommended_settings": None,
        "discovered_requests": [],
        "embedded_json": None,
    }

    cached = None if force_refresh else site_fingerprint.lookup(url)

    if cached and site_fingerprint.is_fresh(cached):
        result["recommendation"] = cached.adapter
        result["from_cache"] = True
        result["cache_confidence"] = cached.confidence
        result["cached_settings"] = json.loads(cached.settings) if cached.settings else None
        result["recommended_settings"] = result["cached_settings"]
        return result

    try:
        html, discovered_requests = browser_analysis.fetch_rendered_html_with_requests(url)
    except browser_analysis.BrowserUnavailableError as error:
        result["fetch_error"] = str(error)
        return result
    except Exception as error:
        result["fetch_error"] = str(error)
        return result

    result["discovered_requests"] = discovered_requests

    soup = BeautifulSoup(html, "lxml")

    signals = _gather_signals(html, url, soup=soup, discovered_requests=discovered_requests)
    classification = _classify(signals)

    pagination_settings = None

    if signals["pagination"] and signals["pagination"].get("url_pattern"):
        pagination_settings = {
            "url_pattern": signals["pagination"]["url_pattern"],
            "max_pages": signals["pagination"]["max_pages"],
        }

    if pagination_settings:
        for key in ("jsonld", "microdata", "html_listing"):
            if signals[key]:
                signals[key]["suggested_settings"]["pagination"] = pagination_settings

    result.update({
        "jsonld": signals["jsonld"],
        "microdata": signals["microdata"],
        "html_listing": signals["html_listing"],
        "generic_links": signals["generic_links"],
        "pagination": signals["pagination"],
        "meta_generator": signals["meta_generator"],
        "script_domains": signals["script_domains"],
        "embedded_json": signals["embedded_json"],
        "js_rendering_hint": classification["js_rendering_hint"],
        "recommendation": classification["recommendation"],
    })

    if result["recommendation"]:

        candidate_by_recommendation = {
            "jsonld_listing": result["jsonld"],
            "microdata_listing": result["microdata"],
            "html_listing": result["html_listing"],
            "generic_links": None,
            "greenhouse": None,
            "discovered_api": None,
            "embedded_json": None,
        }

        candidate = candidate_by_recommendation.get(result["recommendation"])
        suggested_settings = candidate.get("suggested_settings") if candidate else None

        if result["recommendation"] == "greenhouse":
            board_token = greenhouse.derive_board_token(url)
            # None als dit een embed op een eigen domein is (geen
            # greenhouse.io-URL) -- dan moet board_token straks
            # handmatig ingevuld worden, zie adapters/greenhouse.py
            suggested_settings = {"board_token": board_token} if board_token else None

        elif result["recommendation"] == "discovered_api":
            # discovered_requests is al gesorteerd (job-list-achtige
            # kandidaten eerst, zie browser_analysis.py) -- index 0 is
            # dus dezelfde kandidaat die _has_discovered_job_list()
            # beoordeelde. Zelfde opbouw als de "Gebruik deze API"-knop
            # (app.py._apply_discovered_api), bewust gedeeld via
            # discovered_api.settings_from_discovered_request() zodat
            # beide nooit uit de pas kunnen lopen.
            winning_request = signals["discovered_requests"][0]
            suggested_settings = discovered_api.settings_from_discovered_request(winning_request)

        elif result["recommendation"] == "embedded_json":
            # signals["embedded_json"] heeft geen eigen
            # "suggested_settings"-sleutel zoals jsonld/microdata/
            # html_listing (die vult signal_detection.py al -- dat zou
            # daar adapter-kennis in een pure-observatielaag brengen).
            # Zelfde opbouw als de embedded-JSON-sectie's eigen
            # "Gebruik deze instellingen"-knop op de bronpagina,
            # bewust gedeeld via
            # embedded_json.settings_from_embedded_json_candidate()
            # zodat beide nooit uit de pas kunnen lopen.
            suggested_settings = embedded_json.settings_from_embedded_json_candidate(
                signals["embedded_json"]
            )

        result["recommended_settings"] = suggested_settings

        site_fingerprint.save(
            url,
            adapter=result["recommendation"],
            settings_dict=suggested_settings,
            confidence=classification["confidence"],
        )

    return result
