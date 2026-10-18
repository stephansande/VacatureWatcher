"""
Tests voor signal_detection._detect_embedded_json() en de twee
hulpfuncties eronder (_extract_json_after_assignment,
_find_job_array_in_json).

Kant-en-klare Next.js/Nuxt-achtige HTML-fixtures, geen echte sites
nodig -- consistent met de rest van deze testsuite.
"""

import signal_detection as sd


# ---------------------------------------------------------------------------
# _detect_embedded_json -- Next.js
# ---------------------------------------------------------------------------

NEXT_HTML = """
<html><body>
<div id="__next">Laden...</div>
<script id="__NEXT_DATA__" type="application/json">
{"props": {"pageProps": {"vacatures": [
    {"titel": "Data engineer", "locatie": "Den Haag"},
    {"titel": "Projectleider", "locatie": "Rotterdam"}
]}}, "page": "/vacatures"}
</script>
</body></html>
"""


def test_detect_embedded_json_next_js():

    result = sd._detect_embedded_json(NEXT_HTML, "https://voorbeeld.nl/vacatures")

    assert result is not None
    assert result["framework"] == "Next.js (__NEXT_DATA__)"
    assert result["path"] == ["props", "pageProps", "vacatures"]
    assert result["count"] == 2
    assert result["preview"] == ["Data engineer", "Projectleider"]
    assert result["looks_like_job_list"] is True


def test_detect_embedded_json_next_js_zonder_job_data():
    """__NEXT_DATA__ is soms aanwezig maar bevat gewoon geen vacaturelijst."""

    html = """
    <script id="__NEXT_DATA__" type="application/json">
    {"props": {"pageProps": {"title": "Contactpagina"}}}
    </script>
    """

    assert sd._detect_embedded_json(html, "https://voorbeeld.nl/") is None


def test_detect_embedded_json_next_js_ongeldige_json_crasht_niet():

    html = '<script id="__NEXT_DATA__" type="application/json">{niet geldig,,,}</script>'

    assert sd._detect_embedded_json(html, "https://voorbeeld.nl/") is None


# ---------------------------------------------------------------------------
# _detect_embedded_json -- Nuxt
# ---------------------------------------------------------------------------

NUXT_HTML = r"""
<html><body>
<script>window.__NUXT__={"data":{"vacatures":[
    {"functie": "Beleidsmedewerker", "stad": "Utrecht"}
]}, "other": "iets met } een accolade erin"};</script>
</body></html>
"""


def test_detect_embedded_json_nuxt():

    result = sd._detect_embedded_json(NUXT_HTML, "https://voorbeeld.nl/")

    assert result is not None
    assert result["framework"] == "Nuxt"
    assert result["path"] == ["data", "vacatures"]
    assert result["count"] == 1
    assert result["preview"] == ["Beleidsmedewerker"]


def test_detect_embedded_json_nuxt_met_escaped_quotes_en_accolades_in_strings():
    """
    Regressie: een string-waarde die zelf een accolade of escaped
    aanhalingsteken bevat mag de accolade-balancering niet in de war
    brengen (zie _extract_json_after_assignment).
    """

    html = (
        '<script>window.__NUXT__={"data":{"vacatures":['
        r'{"functie": "Beleidsmedewerker \"communicatie {test}\"", "stad": "Utrecht"}'
        ']}, "other": "iets met } een accolade erin"};</script>'
    )

    result = sd._detect_embedded_json(html, "https://voorbeeld.nl/")

    assert result is not None
    assert result["count"] == 1
    assert 'communicatie {test}' in result["preview"][0]


def test_detect_embedded_json_nuxt_ongeldige_js_geeft_none_geen_crash():
    """
    Sommige Nuxt-payloads zijn geen strikt geldige JSON (bv.
    "undefined" als waarde) -- moet netjes None geven, niet crashen.
    """

    html = '<script>window.__NUXT__={"x": undefined};</script>'

    assert sd._detect_embedded_json(html, "https://voorbeeld.nl/") is None


# ---------------------------------------------------------------------------
# _detect_embedded_json -- geen van beide aanwezig
# ---------------------------------------------------------------------------

def test_detect_embedded_json_gewone_pagina_geeft_none():

    html = "<html><body><p>Gewone statische pagina, geen framework.</p></body></html>"

    assert sd._detect_embedded_json(html, "https://voorbeeld.nl/") is None


# ---------------------------------------------------------------------------
# _extract_json_after_assignment (losse unit-tests op de hulpfunctie)
# ---------------------------------------------------------------------------

def test_extract_json_after_assignment_geeft_none_zonder_marker():

    assert sd._extract_json_after_assignment("<html></html>", "window.__NUXT__=") is None


def test_extract_json_after_assignment_geeft_none_bij_afgekapte_accolades():

    text = 'window.__NUXT__={"a": {"b": 1}'  # nooit gesloten

    assert sd._extract_json_after_assignment(text, "window.__NUXT__=") is None


def test_extract_json_after_assignment_negeert_geneste_accolades_in_strings():

    text = 'window.__NUXT__={"tekst": "een } accolade in een string"};'

    raw = sd._extract_json_after_assignment(text, "window.__NUXT__=")

    assert raw == '{"tekst": "een } accolade in een string"}'


# ---------------------------------------------------------------------------
# _find_job_array_in_json (losse unit-tests op de hulpfunctie)
# ---------------------------------------------------------------------------

def test_find_job_array_in_json_top_level_lijst():

    data = [{"title": "A"}, {"title": "B"}]

    path, found = sd._find_job_array_in_json(data)

    assert path == []
    assert found == data


def test_find_job_array_in_json_geneste_wrapper():

    data = {"props": {"pageProps": {"vacatures": [{"title": "A"}]}}}

    path, found = sd._find_job_array_in_json(data)

    assert path == ["props", "pageProps", "vacatures"]
    assert found == [{"title": "A"}]


def test_find_job_array_in_json_respecteert_max_depth():
    """Een array dieper dan max_depth wordt bewust NIET gevonden."""

    data = {"a": {"b": {"c": {"d": [{"title": "te diep"}]}}}}

    path, found = sd._find_job_array_in_json(data, max_depth=2)

    assert found is None


def test_find_job_array_in_json_geen_match_geeft_none_none():

    data = {"foo": "bar", "items": [{"unrelated": "veld"}]}

    path, found = sd._find_job_array_in_json(data)

    assert path is None
    assert found is None


def test_find_job_array_in_json_ondiepe_match_wint_van_diepere():
    """Breedte-eerst: een match op niveau 1 wint van een toevallige match op niveau 3."""

    data = {
        "vacatures": [{"title": "Op niveau 1"}],
        "nested": {"deeper": {"vacatures": [{"title": "Op niveau 3"}]}},
    }

    path, found = sd._find_job_array_in_json(data)

    assert path == ["vacatures"]
    assert found[0]["title"] == "Op niveau 1"
