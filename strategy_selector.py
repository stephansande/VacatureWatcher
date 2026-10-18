"""
strategy_selector.py

De "beslissingslaag" van de Website Detective: neemt de signalen die
signal_detection.py verzameld heeft en beslist welke adapter wint.
Puur signals-dict in, beslissing-dict uit -- geen HTML, geen
requests, geen BeautifulSoup hier. Dat is precies wat _classify()
onafhankelijk van een echte pagina testbaar maakt (zie
tests/test_strategy_selector.py, dat met kant-en-klare
signals-fixtures werkt).

Afkomstig uit adapter_helper.py, zie signal_detection.py voor de
volledige toelichting op de opsplitsing.
"""

import site_fingerprint
from adapters import greenhouse

from bs4 import BeautifulSoup

from signal_detection import (
    _detect_jsonld,
    _detect_microdata,
    _detect_html_listing,
    _detect_generic_links,
    _detect_pagination,
    _detect_meta_generator,
    _detect_script_domains,
    _detect_embedded_json,
    _suspect_js_rendering,
)


def _gather_signals(html, url, soup=None, discovered_requests=None):
    """Verzamelt ruwe features, zonder al een aanbeveling te maken."""

    if soup is None:
        soup = BeautifulSoup(html, "lxml")

    return {
        "url": url,
        "jsonld": _detect_jsonld(html, url),
        "microdata": _detect_microdata(html, url),
        "html_listing": _detect_html_listing(soup, url),
        "generic_links": _detect_generic_links(html, url),
        "pagination": _detect_pagination(soup, url),
        "meta_generator": _detect_meta_generator(soup),
        "script_domains": _detect_script_domains(soup, url),
        "js_rendering_hint": _suspect_js_rendering(html),
        "discovered_requests": discovered_requests or [],
        "embedded_json": _detect_embedded_json(html, url),
    }


def _classify(signals):
    """
    Beslist, puur op basis van signalen, welke adapter wint.

    Volgorde: greenhouse (harde fingerprint-match) > jsonld > microdata
    > embedded_json > discovered_api > html_listing > generic_links.
    discovered_api staat bewust NA de zero-config, kant-en-klare
    methodes (een Greenhouse-embed roept intern ook een JSON-API aan
    die als discovered_api-kandidaat zou kunnen matchen -- dan geeft de
    kant-en-klare greenhouse-adapter een beter resultaat dan een
    discovered_api-voorstel met een leeg field_map), maar wel VÓÓR de
    twee HTML-heuristieken: een echte JSON-API is architecturaal
    robuuster dan op CSS-structuur gokken, ook al vraagt discovered_api
    altijd nog een handmatige field_map-stap.

    embedded_json staat tussen microdata en discovered_api: een
    hydration-payload zit gegarandeerd al in de eerste pagina-aanvraag
    (geen op-tijd-binnen-het-render-venster-race zoals bij een XHR-
    aanroep die browser_analysis.py moet onderscheppen), dus iets
    deterministischer aanwezig dan een discovered_api-kandidaat, al is
    de sleutelnaam-heuristiek zelf even onzeker (zie
    CONFIDENCE_EMBEDDED_JSON in site_fingerprint.py). Sinds
    adapters/embedded_json.py bestaat (die zo'n gevonden payload kan
    hergebruiken voor de geplande controles, door de pagina bij elke
    controle opnieuw te renderen) hoeft dit niet langer puur
    informatief te blijven zoals voorheen.
    """

    if greenhouse.matches_fingerprint(signals.get("url"), signals.get("script_domains")):
        return {
            "recommendation": "greenhouse",
            "confidence": site_fingerprint.confidence_for("greenhouse"),
            "js_rendering_hint": None,
        }

    if signals.get("jsonld"):
        recommendation = "jsonld_listing"
    elif signals.get("microdata"):
        recommendation = "microdata_listing"
    elif signals.get("embedded_json"):
        recommendation = "embedded_json"
    elif _has_discovered_job_list(signals):
        recommendation = "discovered_api"
    elif signals.get("html_listing"):
        recommendation = "html_listing"
    elif signals.get("generic_links"):
        recommendation = "generic_links"
    else:
        recommendation = None

    confidence = (
        site_fingerprint.confidence_for(recommendation)
        if recommendation else None
    )

    return {
        "recommendation": recommendation,
        "confidence": confidence,
        "js_rendering_hint": signals.get("js_rendering_hint") if recommendation is None else None,
    }


def _has_discovered_job_list(signals):
    """
    True als de sterkste kandidaat in signals["discovered_requests"]
    op een vacaturelijst lijkt. De lijst is al gesorteerd door
    browser_analysis.render_page_capturing_requests() (job-list-achtige
    kandidaten eerst), dus alleen index 0 hoeft gecontroleerd te
    worden.
    """

    discovered_requests = signals.get("discovered_requests") or []

    return bool(discovered_requests and discovered_requests[0].get("looks_like_job_list"))
