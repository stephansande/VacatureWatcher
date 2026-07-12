"""
Adapter: html_listing

Generieke, CONFIGUREERBARE scraper voor vacaturesites die een
lijstpagina met herhalende "vacature-blokken" tonen (bv. Culturele
Vacatures, Werken voor Cultuur, OneWorld vacaturebank, Werken bij
Gemeenten, Nationale Vacaturebank).

In tegenstelling tot generic_links.py hoef je hier per site GEEN
Python te schrijven: je geeft CSS-selectors op via Source.settings
(JSON), en deze ene adapter dekt alle sites met dezelfde soort
lijstpagina.

Voorbeeld Source.settings:
{
    "start_url": "https://www.oneworld.nl/vacaturebank/vacatureoverzicht/",
    "selectors": {
        "item": ".vacature-item",
        "title": ".vacature-titel a",
        "link": ".vacature-titel a",
        "location": ".vacature-locatie",
        "date": ".vacature-datum"
    },
    "categories": ["betaalde-functie"],
    "pagination": {
        "url_pattern": "https://www.oneworld.nl/vacaturebank/vacatureoverzicht/page/{page}/",
        "max_pages": 3
    },
    "crawl_delay": 5,
    "include_keywords": ["cultuur", "erfgoed"],
    "exclude_keywords": ["stage", "vrijwilliger"]
}

Alleen "selectors.item" en "selectors.title" zijn verplicht.
"selectors.link" mag weggelaten worden -- dan wordt de title-selector
zelf gebruikt om een href te zoeken.

"categories" wordt momenteel niet automatisch verwerkt (elke site
geeft categorieën op een andere manier door, meestal als onderdeel
van start_url zelf, bv. .../category/betaalde-functie/) -- het staat
hier vooral als plek om dit later per site uit te breiden zonder
opnieuw een databasekolom nodig te hebben.
"""

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper import fetch_html

from adapters.base import load_settings, require, polite_sleep, AdapterError


def fetch(source):

    settings = load_settings(source)

    start_url = settings.get("start_url") or source.url

    pagination = settings.get("pagination")
    crawl_delay = settings.get("crawl_delay", 0)

    if not pagination:
        return [fetch_html(start_url)]

    url_pattern = require(pagination, "url_pattern", source.name)
    max_pages = pagination.get("max_pages", 1)

    pages = []

    for page_number in range(1, max_pages + 1):

        page_url = url_pattern.format(page=page_number)

        pages.append(fetch_html(page_url))

        if page_number < max_pages:
            polite_sleep(crawl_delay)

    return pages


def parse(raw_pages, source):

    settings = load_settings(source)

    selectors = settings.get("selectors", {})

    item_selector = selectors.get("item")
    title_selector = selectors.get("title")

    if not item_selector or not title_selector:
        raise AdapterError(
            f"'{source.name}': html_listing vereist minstens "
            "settings.selectors.item en settings.selectors.title"
        )

    link_selector = selectors.get("link", title_selector)
    location_selector = selectors.get("location")
    date_selector = selectors.get("date")

    base_url = settings.get("start_url") or source.url

    vacancies = []

    for raw_html in raw_pages:

        soup = BeautifulSoup(raw_html, "lxml")

        for item in soup.select(item_selector):

            title_el = item.select_one(title_selector)

            if not title_el:
                continue

            title = title_el.get_text(" ", strip=True)

            link_el = item.select_one(link_selector)
            href = link_el.get("href") if link_el else None

            if not href:
                continue

            content_parts = [title]

            if location_selector:
                location_el = item.select_one(location_selector)
                if location_el:
                    content_parts.append(location_el.get_text(" ", strip=True))

            if date_selector:
                date_el = item.select_one(date_selector)
                if date_el:
                    content_parts.append(date_el.get_text(" ", strip=True))

            vacancies.append({
                "title": title,
                "url": urljoin(base_url, href),
                "content": " | ".join(content_parts),
            })

    return _remove_duplicates(vacancies)


def _remove_duplicates(vacancies):

    seen = set()
    result = []

    for vacancy in vacancies:

        key = vacancy["url"]

        if key not in seen:
            seen.add(key)
            result.append(vacancy)

    return result
