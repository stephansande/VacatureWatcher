"""
Adapter: generic_links

Dit is exact de bestaande v1-aanpak (voorheen vacancy_parser.py):
pak alle <a>-tags op een pagina en houd alleen de links over waarvan
de tekst of URL op een vacature lijkt (bevat "vacature", "job", etc.).

Geschikt voor: eenvoudige "werken bij"-pagina's van individuele
werkgevers, waarbij je geen zin hebt om per werkgever selectors
te configureren.

NIET geschikt voor: grote vacaturesites met veel niet-vacature links
op dezelfde pagina (menu's, footers, gerelateerde content) -- daar
geeft het teveel ruis. Gebruik daarvoor de html_listing-adapter.
"""

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper import fetch_html


DEFAULT_KEYWORDS = [
    "vacature",
    "functie",
    "werken",
    "job",
    "career",
]


CAPABILITIES = {
    "label": "Generieke links",
    "supports_pagination": False,
    "supports_categories": False,
    "supports_detail_pages": False,
    "supports_dates": False,
    "supports_location": False,
    "requires_credentials": False,
}


def fetch(source):
    return fetch_html(source.url)


def parse(raw_content, source):

    soup = BeautifulSoup(raw_content, "lxml")

    vacancies = []

    for link in soup.find_all("a", href=True):

        title = link.get_text(" ", strip=True)
        url = link["href"]

        if not title:
            continue

        combined = (title + " " + url).lower()

        if not any(word in combined for word in DEFAULT_KEYWORDS):
            continue

        vacancies.append({
            "title": title,
            "url": urljoin(source.url, url),
            "content": title,
        })

    return _remove_duplicates(vacancies)


def _remove_duplicates(vacancies):

    seen = set()
    result = []

    for vacancy in vacancies:

        key = vacancy["url"] or vacancy["title"]

        if key not in seen:
            seen.add(key)
            result.append(vacancy)

    return result
