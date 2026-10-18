"""
Tests voor strategy_selector._classify(), de detectiestap uit stap 3 van
de Website Detective-refactor.

Bewust GEEN HTTP-requests en GEEN BeautifulSoup hier: _classify() is
een pure functie (signals-dict in, beslissing-dict uit), dus deze
tests werken met kant-en-klare signals-fixtures. Het ophalen en
verzamelen van signalen (_gather_signals, die wél een echte pagina
nodig heeft) wordt hier bewust niet getest -- dat hoort bij een latere
integratie- of fixture-gebaseerde test met opgeslagen HTML-snapshots.

Draaien:
    pip install pytest --break-system-packages   # of via requirements-dev.txt
    pytest tests/
"""

import pytest

from strategy_selector import _classify


def _signals(**overrides):
    """
    Bouwt een minimale, geldige signals-dict (zoals _gather_signals()
    die zou opleveren), met alles op "niets gevonden" tenzij expliciet
    overschreven. Scheelt boilerplate in elke losse test hieronder.
    """

    base = {
        "url": "https://voorbeeld.nl/vacatures",
        "jsonld": None,
        "microdata": None,
        "html_listing": None,
        "generic_links": None,
        "pagination": None,
        "meta_generator": None,
        "script_domains": [],
        "js_rendering_hint": None,
        "discovered_requests": [],
        "embedded_json": None,
    }

    base.update(overrides)

    return base


def test_classify_prefers_jsonld_over_alle_andere_kandidaten():

    signals = _signals(
        jsonld={"count": 5, "preview": [], "suggested_settings": {}},
        microdata={"count": 3, "preview": [], "suggested_settings": {}},
        html_listing={"total_matches": 10, "preview": [], "suggested_settings": {}},
        generic_links={"count": 20, "preview": []},
    )

    result = _classify(signals)

    assert result["recommendation"] == "jsonld_listing"
    assert result["confidence"] == pytest.approx(0.95)
    assert result["js_rendering_hint"] is None


def test_classify_valt_terug_op_microdata_zonder_jsonld():

    signals = _signals(
        microdata={"count": 3, "preview": [], "suggested_settings": {}},
        html_listing={"total_matches": 10, "preview": [], "suggested_settings": {}},
        generic_links={"count": 20, "preview": []},
    )

    result = _classify(signals)

    assert result["recommendation"] == "microdata_listing"
    assert result["confidence"] == pytest.approx(0.9)


def test_classify_valt_terug_op_html_listing():

    signals = _signals(
        html_listing={"total_matches": 6, "preview": [], "suggested_settings": {}},
        generic_links={"count": 20, "preview": []},
    )

    result = _classify(signals)

    assert result["recommendation"] == "html_listing"
    assert result["confidence"] == pytest.approx(0.7)


def test_classify_valt_terug_op_generic_links_als_laatste_redmiddel():

    signals = _signals(
        generic_links={"count": 4, "preview": []},
    )

    result = _classify(signals)

    assert result["recommendation"] == "generic_links"
    assert result["confidence"] == pytest.approx(0.35)


def test_classify_geeft_geen_aanbeveling_als_niets_gevonden_is():

    signals = _signals(
        js_rendering_hint="Vermoedelijk JavaScript-rendering: ...",
    )

    result = _classify(signals)

    assert result["recommendation"] is None
    assert result["confidence"] is None
    assert result["js_rendering_hint"] == "Vermoedelijk JavaScript-rendering: ..."


def test_classify_verbergt_js_rendering_hint_zodra_er_wel_iets_gevonden_is():
    """
    Regressie: als er wél een kandidaat is (hier: generic_links, de
    zwakste), mag het js_rendering_hint-signaal niet doorgegeven
    worden, ook al staat het (informatief) in de signals -- anders zou
    de UI kunnen suggereren dat een pagina "waarschijnlijk
    JS-rendering" gebruikt terwijl er gewoon iets bruikbaars
    gevonden is.
    """

    signals = _signals(
        generic_links={"count": 4, "preview": []},
        js_rendering_hint="Vermoedelijk JavaScript-rendering: ...",
    )

    result = _classify(signals)

    assert result["recommendation"] == "generic_links"
    assert result["js_rendering_hint"] is None


def test_classify_is_onverschillig_voor_onbekende_extra_signalen():
    """
    meta_generator/script_domains worden nu wel verzameld door
    _gather_signals, maar _classify() mag daar niet op struikelen of
    op leunen -- die signalen zijn (nog) puur informatief, bedoeld
    voor toekomstige platform-adapters (stap 4).
    """

    signals = _signals(
        jsonld={"count": 1, "preview": [], "suggested_settings": {}},
        meta_generator="WordPress 6.4",
        script_domains=["cdn.example.com"],
    )

    result = _classify(signals)

    assert result["recommendation"] == "jsonld_listing"


def test_classify_herkent_greenhouse_via_scriptbron_voor_alles_anders():
    """
    Een embed-widget-scenario: een werkgever toont Greenhouse-
    vacatures op zijn EIGEN domein, maar laadt een script van
    greenhouse.io. Dit is een harde fingerprint-match en moet
    voorrang krijgen boven jsonld/microdata/html_listing, ook als
    die toevallig ook iets vinden (bv. omdat de rest van de pagina wel
    JSON-LD voor iets anders bevat).
    """

    signals = _signals(
        url="https://werkenbij.acme.nl/vacatures",
        script_domains=["boards.greenhouse.io", "cdn.example.com"],
        jsonld={"count": 1, "preview": [], "suggested_settings": {}},
    )

    result = _classify(signals)

    assert result["recommendation"] == "greenhouse"
    assert result["confidence"] == pytest.approx(0.98)
    assert result["js_rendering_hint"] is None


def test_classify_herkent_greenhouse_via_eigen_board_url():
    """Rechtstreeks een boards.greenhouse.io-URL, geen embed nodig."""

    signals = _signals(
        url="https://boards.greenhouse.io/acme/jobs/12345",
        script_domains=[],
    )

    result = _classify(signals)

    assert result["recommendation"] == "greenhouse"


def test_classify_negeert_greenhouse_als_geen_van_beide_signalen_matcht():

    signals = _signals(
        url="https://werkenbij.acme.nl/vacatures",
        script_domains=["cdn.example.com"],
        html_listing={"total_matches": 6, "preview": [], "suggested_settings": {}},
    )

    result = _classify(signals)

    assert result["recommendation"] == "html_listing"


def _job_list_request(url="https://voorbeeld.nl/api/vacatures"):
    return {
        "url": url,
        "method": "GET",
        "status": 200,
        "content_type": "application/json",
        "is_json": True,
        "looks_like_job_list": True,
        "summary": "Array van 2 object(en), velden: title, url",
        "body_preview": '[{"title": "Data engineer"}]',
        "items_path_guess": "",
    }


def test_classify_beveelt_discovered_api_aan_bij_een_job_list_kandidaat():

    signals = _signals(discovered_requests=[_job_list_request()])

    result = _classify(signals)

    assert result["recommendation"] == "discovered_api"
    assert result["confidence"] == pytest.approx(0.8)
    assert result["js_rendering_hint"] is None


def test_classify_discovered_api_wint_van_html_listing_en_generic_links():

    signals = _signals(
        discovered_requests=[_job_list_request()],
        html_listing={"total_matches": 6, "preview": [], "suggested_settings": {}},
        generic_links={"count": 20, "preview": []},
    )

    result = _classify(signals)

    assert result["recommendation"] == "discovered_api"


def test_classify_jsonld_wint_van_discovered_api():
    """
    Kernbeslissing uit stap 4: jsonld/microdata zijn zero-config en
    schema.org-gestandaardiseerd, dus die winnen van een
    discovered_api-kandidaat die sowieso een handmatige field_map-stap
    vergt.
    """

    signals = _signals(
        discovered_requests=[_job_list_request()],
        jsonld={"count": 1, "preview": [], "suggested_settings": {}},
    )

    result = _classify(signals)

    assert result["recommendation"] == "jsonld_listing"


def test_classify_greenhouse_wint_van_discovered_api():
    """
    Kernbeslissing uit stap 4: een Greenhouse-embed roept intern zelf
    een JSON-API aan die een discovered_api-kandidaat zou kunnen
    triggeren -- de kant-en-klare greenhouse-adapter (geen handmatige
    field_map nodig) moet dan winnen, niet de generieke ontdekking.
    """

    signals = _signals(
        url="https://werkenbij.acme.nl/vacatures",
        script_domains=["boards.greenhouse.io"],
        discovered_requests=[_job_list_request("https://boards-api.greenhouse.io/v1/boards/acme/jobs")],
    )

    result = _classify(signals)

    assert result["recommendation"] == "greenhouse"


def test_classify_negeert_discovered_requests_zonder_job_list_signaal():

    non_job_request = _job_list_request()
    non_job_request["looks_like_job_list"] = False

    signals = _signals(
        discovered_requests=[non_job_request],
        html_listing={"total_matches": 6, "preview": [], "suggested_settings": {}},
    )

    result = _classify(signals)

    assert result["recommendation"] == "html_listing"


def test_classify_alleen_de_eerste_discovered_request_telt():
    """
    discovered_requests is al gesorteerd (job-list-achtige kandidaten
    eerst, zie browser_analysis.py) -- _classify() hoeft dus niet de
    hele lijst te doorzoeken. Een job-list-match verderop in de lijst
    (die door een fout in de sortering per ongeluk niet vooraan staat)
    telt bewust NIET mee.
    """

    non_job_request = _job_list_request()
    non_job_request["looks_like_job_list"] = False

    signals = _signals(
        discovered_requests=[non_job_request, _job_list_request()],
        html_listing={"total_matches": 6, "preview": [], "suggested_settings": {}},
    )

    result = _classify(signals)

    assert result["recommendation"] == "html_listing"


def _embedded_json_signal():
    return {
        "framework": "Next.js (__NEXT_DATA__)",
        "path": ["props", "pageProps", "vacatures"],
        "count": 2,
        "preview": ["Data engineer", "Projectleider"],
        "looks_like_job_list": True,
    }


def test_classify_beveelt_embedded_json_aan_als_adapter():
    """
    Sinds adapters/embedded_json.py bestaat, mag een gevonden
    hydration-payload wél de winnende classificatie zijn als er verder
    niets kant-en-klaarders (jsonld/microdata) gevonden is.
    """

    signals = _signals(embedded_json=_embedded_json_signal())

    result = _classify(signals)

    assert result["recommendation"] == "embedded_json"
    assert result["confidence"] == pytest.approx(0.82)


def test_classify_embedded_json_wint_van_discovered_api():
    """
    embedded_json staat vóór discovered_api in de precedentie (zie de
    toelichting in _classify()): een hydration-payload zit
    gegarandeerd al in de eerste pagina-aanvraag.
    """

    signals = _signals(
        embedded_json=_embedded_json_signal(),
        discovered_requests=[_job_list_request()],
    )

    result = _classify(signals)

    assert result["recommendation"] == "embedded_json"


def test_classify_embedded_json_blokkeert_andere_kandidaten_niet():
    """
    Een aanwezig embedded_json-signaal mag de normale precedentie voor
    de WEL bestaande adapters niet in de weg zitten -- jsonld wint hier
    gewoon, embedded_json is puur informatief ernaast.
    """

    signals = _signals(
        embedded_json=_embedded_json_signal(),
        jsonld={"count": 1, "preview": [], "suggested_settings": {}},
    )

    result = _classify(signals)

    assert result["recommendation"] == "jsonld_listing"
