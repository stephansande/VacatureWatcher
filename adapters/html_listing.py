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
        "link_attr": "href",
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

Alleen "selectors.item" is verplicht, plus minstens één van
"selectors.title"/"selectors.link" (de ander valt dan terug op
hetzelfde element -- handig voor simpele lijsten zoals
{"item": "ul > li", "link": "a"} zonder aparte titel-markup).

"selectors.link_attr" is optioneel, standaard "href" (het normale
geval: een echte <a href="...">). Zet 'm op "onclick" voor sites die
in plaats daarvan een klikbaar element bouwen met
onclick="location.href='...'" -- geen <a>, geen href, alleen JS. Zo'n
patroon kwamen we tegen bij een Vue-widget op Werken voor Wassenaar:
<div class="card" onclick="location.href='vacature.html?id=894537';">.

"selectors.link" (en ook "selectors.title") mag de speciale waarde
"self" zijn: dan is het ITEM-element zelf het bedoelde element (bv.
wanneer de onclick op dezelfde <div> staat als "selectors.item", of
wanneer het item-element zelf al de titeltekst bevat). Dit werkt NIET
met een normale CSS-selector die naar zichzelf verwijst
(item.select_one() zoekt alleen in afstammelingen, nooit het element
zelf), vandaar deze aparte sentinel-waarde:
{
    "item": "div.customCard[onclick]",
    "title": ".card-title",
    "link": "self",
    "link_attr": "onclick"
}

"categories" wordt momenteel niet automatisch verwerkt (elke site
geeft categorieën op een andere manier door, meestal als onderdeel
van start_url zelf, bv. .../category/betaalde-functie/) -- het staat
hier vooral als plek om dit later per site uit te breiden zonder
opnieuw een databasekolom nodig te hebben.
"""

from urllib.parse import urljoin

import re

from bs4 import BeautifulSoup

from scraper import fetch_html

from adapters.base import load_settings, require, polite_sleep, AdapterError


_ONCLICK_URL_RE = re.compile(r"""location\.href\s*=\s*['"]([^'"]+)['"]""")


def _extract_url(element, attr):
    """
    Haalt de vacature-URL op uit `element` via het attribuut `attr`
    (standaard "href", het normale geval). Bij attr == "onclick" wordt
    in plaats daarvan een veelvoorkomend JS-patroon herkend:
    onclick="location.href='...'" -- gebruikt door sites die
    vacaturekaarten bouwen met een <div onclick="..."> in plaats van
    een echte <a href> (aangetroffen bij een Vue-widget op Werken voor
    Wassenaar: geen enkele <a href> op de pagina, wel
    <div class="card" onclick="location.href='vacature.html?id=...'">).
    Voor elk ander attr-veld wordt gewoon die attribuutwaarde gelezen.
    """

    if attr == "onclick":

        raw = element.get("onclick", "") or ""
        match = _ONCLICK_URL_RE.search(raw)

        return match.group(1) if match else None

    return element.get(attr)


CAPABILITIES = {
    "label": "HTML-lijstpagina (CSS-selectors)",
    "supports_pagination": True,
    "supports_categories": True,
    "supports_detail_pages": False,
    "supports_dates": True,
    "supports_location": True,
    "requires_credentials": False,
}


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

    if not item_selector:
        raise AdapterError(
            f"'{source.name}': html_listing vereist minstens "
            "settings.selectors.item"
        )

    title_selector = selectors.get("title")
    link_selector = selectors.get("link")

    if not title_selector and not link_selector:
        raise AdapterError(
            f"'{source.name}': html_listing vereist settings.selectors.title "
            "en/of settings.selectors.link (minstens één van de twee -- "
            "de ander wordt dan hetzelfde element gebruikt)"
        )

    # auto-fallback: title en link mogen naar hetzelfde element wijzen.
    # Bijvoorbeeld {"item": "ul > li", "link": "a"} zonder aparte
    # "title" is een veelvoorkomend, geldig patroon (zie Amare/HNT).
    title_selector = title_selector or link_selector
    link_selector = link_selector or title_selector

    location_selector = selectors.get("location")
    date_selector = selectors.get("date")

    link_attr = selectors.get("link_attr", "href")
    # "href" (standaard) of "onclick" -- zie _extract_url() hierboven.
    # Nodig voor sites zonder echte <a href>, bv. widgets die met
    # <div onclick="location.href='...'"> werken.

    base_url = settings.get("start_url") or source.url

    vacancies = []

    for raw_html in raw_pages:

        soup = BeautifulSoup(raw_html, "lxml")

        for item in soup.select(item_selector):

            title_el = item if title_selector == "self" else item.select_one(title_selector)

            if not title_el:
                continue

            title = title_el.get_text(" ", strip=True)

            link_el = item if link_selector == "self" else item.select_one(link_selector)
            href = _extract_url(link_el, link_attr) if link_el else None

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
