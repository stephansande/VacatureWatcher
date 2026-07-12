"""
Adapter: jsonld_listing

Veel moderne vacaturesites en ATS'en embedden vacaturedata als
schema.org JobPosting JSON-LD (een <script type="application/ld+json">
blok). Dat is vaak stabieler dan CSS-selectors -- een redesign van de
pagina verandert meestal niets aan de gestructureerde data eronder --
en scheelt je het handmatig zoeken naar de juiste CSS-classes.

Twee manieren waarop sites dit aanbieden (settings.mode):

  "listing" -- de listing/zoekpagina zelf bevat al JobPosting-blokken
               (bv. als array, of onder "@graph"). Eén of enkele
               requests volstaan.

  "detail"  -- de listingpagina bevat alleen links naar aparte
               detailpagina's, en PAS die detailpagina's bevatten elk
               één JobPosting-blok. Dit vereist een request per
               vacature, dus wees zuinig met max_items en crawl_delay.

Voorbeeld Source.settings (mode "listing"):
{
    "start_url": "https://example-atsvacatures.nl/vacatures/",
    "mode": "listing",
    "pagination": {"url_pattern": "https://example-atsvacatures.nl/vacatures/page/{page}/", "max_pages": 3},
    "crawl_delay": 5
}

Voorbeeld Source.settings (mode "detail"):
{
    "start_url": "https://example-vacaturesite.nl/vacatures/",
    "mode": "detail",
    "link_selector": ".vacature-item a",
    "max_items": 40,
    "crawl_delay": 5
}
"""

from urllib.parse import urljoin
import json

from bs4 import BeautifulSoup

from scraper import fetch_html

from adapters.base import load_settings, require, polite_sleep, AdapterError


DEFAULT_MAX_ITEMS = 50


def fetch(source):

    settings = load_settings(source)

    mode = settings.get("mode", "listing")
    start_url = settings.get("start_url") or source.url
    crawl_delay = settings.get("crawl_delay", 0)

    listing_pages = _fetch_listing_pages(start_url, settings, crawl_delay)

    if mode == "listing":
        return listing_pages

    if mode == "detail":
        return _fetch_detail_pages(listing_pages, start_url, settings, crawl_delay)

    raise AdapterError(
        f"'{source.name}': onbekende jsonld_listing mode '{mode}' "
        "(verwacht 'listing' of 'detail')"
    )


def parse(raw_pages, source):

    vacancies = []

    for page in raw_pages:

        job_postings = _extract_job_postings(page["html"])

        for job in job_postings:

            title = job.get("title")

            if not title:
                continue

            url = job.get("url") or page["url"]
            description = _strip_html(job.get("description", ""))

            vacancies.append({
                "title": title,
                "url": urljoin(page["url"], url),
                "content": description or title,
            })

    return _remove_duplicates(vacancies)


def _fetch_listing_pages(start_url, settings, crawl_delay):

    pagination = settings.get("pagination")

    if not pagination:
        return [{"url": start_url, "html": fetch_html(start_url)}]

    url_pattern = pagination["url_pattern"]
    max_pages = pagination.get("max_pages", 1)

    pages = []

    for page_number in range(1, max_pages + 1):

        page_url = url_pattern.format(page=page_number)
        pages.append({"url": page_url, "html": fetch_html(page_url)})

        if page_number < max_pages:
            polite_sleep(crawl_delay)

    return pages


def _fetch_detail_pages(listing_pages, start_url, settings, crawl_delay):

    link_selector = require(settings, "link_selector", "jsonld_listing (mode=detail)")
    max_items = settings.get("max_items", DEFAULT_MAX_ITEMS)

    detail_urls = []
    seen = set()

    for page in listing_pages:

        soup = BeautifulSoup(page["html"], "lxml")

        for link in soup.select(link_selector):

            href = link.get("href")

            if not href:
                continue

            absolute_url = urljoin(page["url"], href)

            if absolute_url not in seen:
                seen.add(absolute_url)
                detail_urls.append(absolute_url)

    detail_urls = detail_urls[:max_items]

    detail_pages = []

    for index, detail_url in enumerate(detail_urls):

        detail_pages.append({
            "url": detail_url,
            "html": fetch_html(detail_url),
        })

        if index < len(detail_urls) - 1:
            polite_sleep(crawl_delay)

    return detail_pages


def extract_job_postings(html):
    """Publieke wrapper rond _extract_job_postings, voor hergebruik door adapter_helper.py."""
    return _extract_job_postings(html)


def strip_html(text):
    """Publieke wrapper rond _strip_html, voor hergebruik door adapter_helper.py."""
    return _strip_html(text)


def _extract_job_postings(html):

    soup = BeautifulSoup(html, "lxml")

    postings = []

    for script in soup.find_all("script", type="application/ld+json"):

        raw_text = script.string or script.get_text()

        if not raw_text or not raw_text.strip():
            continue

        try:
            data = json.loads(raw_text)
        except (ValueError, TypeError):
            continue

        postings.extend(_find_job_postings(data))

    return postings


def _find_job_postings(node):
    """Doorzoekt een (geneste) JSON-LD structuur op JobPosting-objecten."""

    found = []

    if isinstance(node, dict):

        node_type = node.get("@type")

        is_job_posting = node_type == "JobPosting" or (
            isinstance(node_type, list) and "JobPosting" in node_type
        )

        if is_job_posting:
            found.append(node)

        for value in node.values():
            found.extend(_find_job_postings(value))

    elif isinstance(node, list):

        for item in node:
            found.extend(_find_job_postings(item))

    return found


def _strip_html(text):

    if not text:
        return ""

    return BeautifulSoup(text, "lxml").get_text(" ", strip=True)


def _remove_duplicates(vacancies):

    seen = set()
    result = []

    for vacancy in vacancies:

        key = vacancy["url"]

        if key not in seen:
            seen.add(key)
            result.append(vacancy)

    return result
