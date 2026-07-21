"""
Tests voor adapters/greenhouse.py.

parse() wordt getest tegen een kant-en-klare voorbeeld-JSON-respons
(zoals de echte Greenhouse Job Board API die teruggeeft), dus zonder
een echte HTTP-call te doen -- fetch() zelf (de requests.get-aanroep)
wordt hier bewust niet getest, dat hoort bij een latere
integratietest met een gemockte requests-sessie.
"""

from types import SimpleNamespace

from adapters.greenhouse import parse, derive_board_token, matches_fingerprint


# Verkorte, maar structureel representatieve voorbeeld-respons van
# GET https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true
SAMPLE_JOBS = [
    {
        "id": 4123456,
        "title": "Data engineer",
        "updated_at": "2026-07-10T09:15:00-05:00",
        "location": {"name": "Amsterdam, Nederland"},
        "absolute_url": "https://boards.greenhouse.io/acme/jobs/4123456",
        "content": "<p>Wij zoeken een <strong>data engineer</strong> voor ons platformteam.</p>",
    },
    {
        "id": 4123457,
        "title": "Stagiair marketing",
        "updated_at": "2026-07-08T14:00:00-05:00",
        "location": {"name": "Utrecht, Nederland"},
        "absolute_url": "https://boards.greenhouse.io/acme/jobs/4123457",
        "content": "<p>Stage van 5-6 maanden binnen het marketingteam.</p>",
    },
    {
        # Zonder titel: hoort overgeslagen te worden, net als bij de
        # andere adapters (zie bv. jsonld_listing.parse()).
        "id": 4123458,
        "title": "",
        "location": {"name": "Rotterdam, Nederland"},
        "absolute_url": "https://boards.greenhouse.io/acme/jobs/4123458",
        "content": "<p>Deze mag niet meetellen.</p>",
    },
    {
        # Zonder absolute_url: ook overslaan, een vacature zonder URL
        # is niet bruikbaar voor de rest van de applicatie.
        "id": 4123459,
        "title": "Vacature zonder URL",
        "location": {"name": "Den Haag, Nederland"},
        "content": "<p>Deze ontbreekt een absolute_url.</p>",
    },
]


def _fake_source():
    return SimpleNamespace(
        id=1,
        name="Acme (Greenhouse)",
        url="https://boards.greenhouse.io/acme",
        adapter="greenhouse",
        settings=None,
        keywords=None,
    )


def test_parse_haalt_titel_url_locatie_en_datum_op():

    vacancies = parse(SAMPLE_JOBS, _fake_source())

    assert len(vacancies) == 2  # de twee zonder titel/url zijn overgeslagen

    eerste = vacancies[0]

    assert eerste["title"] == "Data engineer"
    assert eerste["url"] == "https://boards.greenhouse.io/acme/jobs/4123456"
    assert eerste["location"] == "Amsterdam, Nederland"
    assert eerste["date"] == "2026-07-10T09:15:00-05:00"


def test_parse_strip_html_uit_de_content():

    vacancies = parse(SAMPLE_JOBS, _fake_source())

    eerste = vacancies[0]

    assert "<p>" not in eerste["content"]
    assert "<strong>" not in eerste["content"]
    assert "data engineer" in eerste["content"].lower()


def test_parse_slaat_jobs_zonder_titel_of_url_over():

    vacancies = parse(SAMPLE_JOBS, _fake_source())

    titles = [v["title"] for v in vacancies]

    assert "Vacature zonder URL" not in titles
    assert "" not in titles


def test_derive_board_token_uit_boards_url():

    assert derive_board_token("https://boards.greenhouse.io/acme/jobs/4123456") == "acme"
    assert derive_board_token("https://boards.greenhouse.io/acme") == "acme"


def test_derive_board_token_geeft_none_voor_ander_domein():

    assert derive_board_token("https://werkenbij.acme.nl/vacatures") is None


def test_matches_fingerprint_via_eigen_url():

    assert matches_fingerprint("https://boards.greenhouse.io/acme", []) is True


def test_matches_fingerprint_via_scriptbron_embed():

    assert matches_fingerprint(
        "https://werkenbij.acme.nl/vacatures",
        ["cdn.example.com", "boards.greenhouse.io"],
    ) is True


def test_matches_fingerprint_negatief_zonder_signaal():

    assert matches_fingerprint("https://werkenbij.acme.nl/vacatures", ["cdn.example.com"]) is False
