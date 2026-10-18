"""
Tests voor adapters/embedded_json.py.

Net als test_discovered_api.py: geen echte HTTP/Playwright-calls.
parse() wordt getest tegen kant-en-klare Next.js/Nuxt-achtige
HTML-fixtures (dezelfde soort fixtures als tests/test_embedded_json.py
voor signal_detection._detect_embedded_json() gebruikt) -- fetch()
zelf (de Playwright-aanroep) wordt hier bewust niet getest, dat hoort
bij een latere integratietest met een gemockte browser, net als bij
adapters/browser_listing.py.
"""

import json

import pytest
from types import SimpleNamespace

from adapters.embedded_json import parse, settings_from_embedded_json_candidate
from adapters.base import AdapterError


def _source(settings, url="https://voorbeeld.nl/vacatures"):
    return SimpleNamespace(
        name="Testbron",
        url=url,
        settings=json.dumps(settings),
        keywords=None,
    )


NEXT_HTML = """
<html><body>
<div id="__next">Laden...</div>
<script id="__NEXT_DATA__" type="application/json">
{"props": {"pageProps": {"vacatures": [
    {"titel": "Data engineer", "link": "/vacature/1", "plaats": "Den Haag"},
    {"titel": "Projectleider", "link": "/vacature/2", "plaats": "Rotterdam"},
    {"titel": "", "link": "/vacature/3"}
]}}, "page": "/vacatures"}
</script>
</body></html>
"""

NUXT_HTML = r"""
<html><body>
<script>window.__NUXT__={"data":{"vacatures":[
    {"functie": "Beleidsmedewerker", "url": "https://voorbeeld.nl/v/1"}
]}}};</script>
</body></html>
"""


def test_parse_next_js_met_field_map():

    source = _source({
        "items_path": ["props", "pageProps", "vacatures"],
        "field_map": {"title": "titel", "url": "link", "location": "plaats"},
    })

    vacancies = parse(NEXT_HTML, source)

    assert len(vacancies) == 2  # het lege-titel-item is overgeslagen

    eerste = vacancies[0]
    assert eerste["title"] == "Data engineer"
    assert eerste["url"] == "https://voorbeeld.nl/vacature/1"
    assert eerste["location"] == "Den Haag"


def test_parse_relatieve_url_wordt_samengevoegd_met_base_url():

    source = _source({
        "items_path": ["props", "pageProps", "vacatures"],
        "base_url": "https://voorbeeld.nl",
        "field_map": {"title": "titel", "url": "link"},
    })

    vacancies = parse(NEXT_HTML, source)

    assert vacancies[1]["url"] == "https://voorbeeld.nl/vacature/2"


def test_parse_nuxt_window_assignment():

    source = _source({
        "items_path": ["data", "vacatures"],
        "field_map": {"title": "functie", "url": "url"},
    })

    vacancies = parse(NUXT_HTML, source)

    assert len(vacancies) == 1
    assert vacancies[0]["title"] == "Beleidsmedewerker"


def test_parse_zonder_items_path_geeft_duidelijke_fout():

    source = _source({"field_map": {"title": "titel", "url": "link"}})

    with pytest.raises(AdapterError, match="items_path"):
        parse(NEXT_HTML, source)


def test_parse_items_path_als_string_geeft_duidelijke_fout():
    """
    items_path is bij deze adapter een LIJST van sleutels (in
    tegenstelling tot discovered_api, waar het één string is) -- een
    per ongeluk meegegeven string moet een duidelijke fout geven, geen
    verwarrende crash of stille 0 resultaten.
    """

    source = _source({
        "items_path": "props.pageProps.vacatures",
        "field_map": {"title": "titel", "url": "link"},
    })

    with pytest.raises(AdapterError, match="lijst van"):
        parse(NEXT_HTML, source)


def test_parse_items_path_wijst_niet_naar_geldig_pad():

    source = _source({
        "items_path": ["props", "bestaat_niet"],
        "field_map": {"title": "titel", "url": "link"},
    })

    with pytest.raises(AdapterError, match="items_path"):
        parse(NEXT_HTML, source)


def test_parse_items_path_wijst_niet_naar_een_array():

    source = _source({
        "items_path": ["page"],  # top-level "page" is een string, geen array
        "field_map": {"title": "titel", "url": "link"},
    })

    with pytest.raises(AdapterError, match="array"):
        parse(NEXT_HTML, source)


def test_parse_verkeerde_field_map_geeft_duidelijke_fout_bij_eerste_item():

    source = _source({
        "items_path": ["props", "pageProps", "vacatures"],
        "field_map": {"title": "bestaat_niet", "url": "ook_niet"},
    })

    with pytest.raises(AdapterError, match="Verplicht veld ontbreekt"):
        parse(NEXT_HTML, source)


def test_parse_leeg_field_map_faalt_bewust():
    """
    Net als bij discovered_api: settings_from_embedded_json_candidate()
    levert een LEGE field_map op ({"title": "", "url": ""}) -- vóór de
    gebruiker 'm invult, mag dit dus nooit stilzwijgend resultaten
    opleveren.
    """

    source = _source({
        "items_path": ["props", "pageProps", "vacatures"],
        "field_map": {"title": "", "url": ""},
    })

    with pytest.raises(AdapterError, match="Verplicht veld ontbreekt"):
        parse(NEXT_HTML, source)


def test_parse_geen_embedded_json_in_html_geeft_duidelijke_fout():

    source = _source({
        "items_path": ["props", "pageProps", "vacatures"],
        "field_map": {"title": "titel", "url": "link"},
    })

    with pytest.raises(AdapterError, match="Geen embedded JSON"):
        parse("<html><body><p>Gewone pagina.</p></body></html>", source)


def test_settings_from_embedded_json_candidate_bouwt_items_path_en_lege_field_map():

    candidate = {
        "framework": "Next.js (__NEXT_DATA__)",
        "path": ["props", "pageProps", "vacatures"],
        "count": 2,
        "preview": ["Data engineer", "Projectleider"],
        "looks_like_job_list": True,
    }

    settings = settings_from_embedded_json_candidate(candidate)

    assert settings == {
        "items_path": ["props", "pageProps", "vacatures"],
        "field_map": {"title": "", "url": ""},
    }
