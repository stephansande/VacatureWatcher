"""
Tests voor adapters/discovered_api.py.

Geen echte HTTP-calls: parse() wordt getest tegen kant-en-klare
fixture-responses, net als bij de andere adapters (zie
test_greenhouse_adapter.py). fetch() zelf (de requests.get/post-
aanroep) wordt hier bewust niet getest -- dat hoort bij een latere
integratietest met een gemockte requests-sessie, net als bij de
andere API-adapters in dit project.
"""

import json

import pytest
from types import SimpleNamespace

from adapters.discovered_api import parse
from adapters.base import AdapterError


def _source(settings, url="https://voorbeeld.nl/vacatures"):
    return SimpleNamespace(
        name="Testbron",
        url=url,
        settings=json.dumps(settings),
        keywords=None,
    )


# Representatieve top-level-array-respons, zoals "Ontdekt netwerkverkeer"
# 'm zou tonen voor een site met eigen JSON-veldnamen.
SAMPLE_TOP_LEVEL = [
    {"functietitel": "Data engineer", "link": "/vacature/1", "plaats": "Den Haag", "geplaatst_op": "2026-07-01"},
    {"functietitel": "Projectleider", "link": "/vacature/2", "plaats": "Rotterdam"},
    {"functietitel": "", "link": "/vacature/3"},  # geen titel -- moet overgeslagen worden
]

SAMPLE_WRAPPED = {
    "results": [
        {"title": "Beleidsmedewerker", "url": "https://voorbeeld.nl/v/1"},
    ],
    "total": 1,
}


def test_parse_top_level_array_met_field_map():

    source = _source({
        "endpoint_url": "https://voorbeeld.nl/api/vacatures",
        "base_url": "https://voorbeeld.nl",
        "field_map": {"title": "functietitel", "url": "link", "location": "plaats", "date": "geplaatst_op"},
    })

    vacancies = parse(SAMPLE_TOP_LEVEL, source)

    assert len(vacancies) == 2  # het lege-titel-item is overgeslagen

    eerste = vacancies[0]
    assert eerste["title"] == "Data engineer"
    assert eerste["url"] == "https://voorbeeld.nl/vacature/1"
    assert eerste["location"] == "Den Haag"
    assert eerste["date"] == "2026-07-01"


def test_parse_relatieve_url_wordt_samengevoegd_met_base_url():

    source = _source({
        "endpoint_url": "https://voorbeeld.nl/api/vacatures",
        "base_url": "https://voorbeeld.nl",
        "field_map": {"title": "functietitel", "url": "link"},
    })

    vacancies = parse(SAMPLE_TOP_LEVEL, source)

    assert vacancies[1]["url"] == "https://voorbeeld.nl/vacature/2"


def test_parse_zonder_base_url_valt_terug_op_source_url():

    source = _source(
        {"endpoint_url": "https://voorbeeld.nl/api/vacatures", "field_map": {"title": "functietitel", "url": "link"}},
        url="https://voorbeeld.nl/vacatures/",
    )

    vacancies = parse(SAMPLE_TOP_LEVEL, source)

    assert vacancies[0]["url"] == "https://voorbeeld.nl/vacature/1"


def test_parse_items_path_navigeert_naar_wrapper_array():

    source = _source({
        "endpoint_url": "https://voorbeeld.nl/api",
        "items_path": "results",
        "field_map": {"title": "title", "url": "url"},
    })

    vacancies = parse(SAMPLE_WRAPPED, source)

    assert len(vacancies) == 1
    assert vacancies[0]["title"] == "Beleidsmedewerker"


def test_parse_content_valt_terug_op_titel_zonder_content_field():

    source = _source({
        "endpoint_url": "https://voorbeeld.nl/api",
        "field_map": {"title": "functietitel", "url": "link"},
    })

    vacancies = parse(SAMPLE_TOP_LEVEL, source)

    assert vacancies[0]["content"] == "Data engineer"


def test_parse_verkeerde_field_map_geeft_duidelijke_fout_bij_eerste_item():
    """
    Kernvereiste: een field_map die niet bij de respons past moet een
    duidelijke AdapterError geven -- niet stilzwijgend 0 resultaten,
    precies het soort verwarring dat we bij Werk bij Dunea met een
    verouderde CSS-selector tegenkwamen.
    """

    source = _source({
        "endpoint_url": "https://voorbeeld.nl/api",
        "field_map": {"title": "bestaat_niet", "url": "ook_niet"},
    })

    with pytest.raises(AdapterError, match="Verplicht veld ontbreekt"):
        parse(SAMPLE_TOP_LEVEL, source)


def test_parse_later_incompleet_item_wordt_stil_overgeslagen():
    """
    Alleen het EERSTE item wordt als configuratie-sanity-check
    behandeld (harde fout). Een toevallig incompleet item verderop in
    een verder prima array wordt gewoon overgeslagen, net als bij de
    andere adapters.
    """

    data = [
        {"title": "Goed", "url": "https://voorbeeld.nl/v/1"},
        {"title": None, "url": None},
        {"title": "Ook goed", "url": "https://voorbeeld.nl/v/3"},
    ]

    source = _source({
        "endpoint_url": "https://voorbeeld.nl/api",
        "field_map": {"title": "title", "url": "url"},
    })

    vacancies = parse(data, source)

    assert len(vacancies) == 2


def test_parse_ontbrekend_items_path_geeft_duidelijke_fout():

    source = _source({
        "endpoint_url": "https://voorbeeld.nl/api",
        "items_path": "bestaat_niet",
        "field_map": {"title": "title", "url": "url"},
    })

    with pytest.raises(AdapterError, match="items_path"):
        parse(SAMPLE_WRAPPED, source)


def test_parse_items_path_wijst_niet_naar_een_array():

    source = _source({
        "endpoint_url": "https://voorbeeld.nl/api",
        "items_path": "total",  # "total" is een getal, geen array
        "field_map": {"title": "title", "url": "url"},
    })

    with pytest.raises(AdapterError, match="array"):
        parse(SAMPLE_WRAPPED, source)


def test_parse_niet_dict_items_worden_overgeslagen():

    data = ["gewoon een string", {"title": "Geldig", "url": "https://voorbeeld.nl/v/1"}]

    source = _source({
        "endpoint_url": "https://voorbeeld.nl/api",
        "field_map": {"title": "title", "url": "url"},
    })

    vacancies = parse(data, source)

    assert len(vacancies) == 1
    assert vacancies[0]["title"] == "Geldig"


def test_parse_zonder_field_map_gebruikt_standaardveldnamen():
    """Zonder field_map vallen title/url terug op de letterlijke sleutels "title"/"url"."""

    data = [{"title": "Standaard", "url": "https://voorbeeld.nl/v/1"}]

    source = _source({"endpoint_url": "https://voorbeeld.nl/api"})

    vacancies = parse(data, source)

    assert len(vacancies) == 1
    assert vacancies[0]["title"] == "Standaard"
