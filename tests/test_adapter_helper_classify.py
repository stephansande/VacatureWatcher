"""
Tests voor adapter_helper._classify(), de detectiestap uit stap 3 van
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

from adapter_helper import _classify


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
