"""
Tests voor adapter_helper.raw_fetch_debug() -- de "Ruwe respons
bekijken"-functie, toegevoegd na het Werk bij Dunea-scenario: zowel de
Adapter Helper als een handmatige adapter-configuratie vonden daar 0
vacatures, wat erop wees dat het probleem bij het OPHALEN zat (een
te herkenbare User-Agent, zie scraper.py), niet bij de selectors.

Gebruikt monkeypatch om adapter_helper.fetch_html te vervangen -- geen
echte netwerkcall nodig, net als de rest van deze testsuite.
"""

from types import SimpleNamespace

import adapter_helper


def _source(url="https://example.nl/vacatures", settings=None):
    return SimpleNamespace(url=url, settings=settings)


def test_raw_fetch_debug_normale_pagina(monkeypatch):

    monkeypatch.setattr(
        adapter_helper,
        "fetch_html",
        lambda url: "<html><body>" + "vacature " * 500 + "</body></html>",
    )

    result = adapter_helper.raw_fetch_debug(_source())

    assert result["error"] is None
    assert result["length"] > 1000
    assert result["looks_blocked"] is False
    assert result["preview"].startswith("<html>")


def test_raw_fetch_debug_herkent_bot_detectiepagina(monkeypatch):

    monkeypatch.setattr(
        adapter_helper,
        "fetch_html",
        lambda url: "<html><body>Just a moment... Checking your browser</body></html>",
    )

    result = adapter_helper.raw_fetch_debug(_source())

    assert result["error"] is None
    assert result["looks_blocked"] is True


def test_raw_fetch_debug_korte_respons_geldt_als_verdacht(monkeypatch):
    """
    Ook zonder een herkende bot-detectietekst geldt een ongebruikelijk
    korte respons (< 1000 tekens) als verdacht -- veel blokkeer-/
    foutpagina's zijn kort, ook als ze geen van de bekende teksten
    bevatten.
    """

    monkeypatch.setattr(
        adapter_helper,
        "fetch_html",
        lambda url: "<html><body>Sorry, geen toegang.</body></html>",
    )

    result = adapter_helper.raw_fetch_debug(_source())

    assert result["looks_blocked"] is True


def test_raw_fetch_debug_geeft_foutmelding_door_zonder_crash(monkeypatch):

    def raise_error(url):
        raise Exception("403 Client Error: Forbidden")

    monkeypatch.setattr(adapter_helper, "fetch_html", raise_error)

    result = adapter_helper.raw_fetch_debug(_source())

    assert "403" in result["error"]
    assert result["length"] is None
    assert result["looks_blocked"] is None


def test_raw_fetch_debug_gebruikt_start_url_uit_settings_indien_aanwezig():

    calls = []

    def fake_fetch(url):
        calls.append(url)
        return "<html></html>"

    import json

    source = _source(
        url="https://example.nl/basis-pagina",
        settings=json.dumps({"start_url": "https://example.nl/gefilterd?x=1"}),
    )

    orig = adapter_helper.fetch_html
    adapter_helper.fetch_html = fake_fetch
    try:
        result = adapter_helper.raw_fetch_debug(source)
    finally:
        adapter_helper.fetch_html = orig

    assert result["url"] == "https://example.nl/gefilterd?x=1"
    assert calls == ["https://example.nl/gefilterd?x=1"]


def test_raw_fetch_debug_test_item_selector_tegen_verse_respons(monkeypatch):
    """
    Kernscenario Werk bij Dunea: de respons komt prima binnen, maar de
    geconfigureerde selector matcht niets meer (bv. omdat de live site
    een andere class-naam gebruikt dan een eerder geanalyseerde
    snapshot). Dit moet zichtbaar zijn als item_selector_matches == 0,
    niet verstopt in een losse "0 vacatures"-melding elders.
    """

    html = """
    <ul>
      <li><a class="vacature-link" href="/v/1">Een</a></li>
      <li><a class="vacature-link" href="/v/2">Twee</a></li>
    </ul>
    """

    monkeypatch.setattr(adapter_helper, "fetch_html", lambda url: html)

    import json

    source = _source(
        settings=json.dumps({"selectors": {"item": "a.cssSelectorColor"}})
    )

    result = adapter_helper.raw_fetch_debug(source)

    assert result["item_selector"] == "a.cssSelectorColor"
    assert result["item_selector_matches"] == 0  # class bestaat niet (meer) in deze respons
    assert result["link_count"] == 2  # er zitten wel degelijk <a href>'s in de pagina


def test_raw_fetch_debug_zonder_selectors_in_settings_laat_matchveld_leeg(monkeypatch):

    monkeypatch.setattr(adapter_helper, "fetch_html", lambda url: "<html></html>")

    result = adapter_helper.raw_fetch_debug(_source(settings=None))

    assert result["item_selector"] is None
    assert result["item_selector_matches"] is None


def test_raw_fetch_debug_ongeldige_selector_crasht_niet(monkeypatch):

    monkeypatch.setattr(adapter_helper, "fetch_html", lambda url: "<html><body></body></html>")

    import json

    source = _source(settings=json.dumps({"selectors": {"item": ":::geen geldige css:::"}}))

    result = adapter_helper.raw_fetch_debug(source)

    assert result["item_selector_matches"] is not None
    assert "FOUT" in result["item_selector_matches"]
