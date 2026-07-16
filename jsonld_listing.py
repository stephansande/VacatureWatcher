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

from adapters.base import (
    load_settings,
    fetch_listing_pages,
    fetch_detail_pages,
    remove_duplicate_vacancies,
    AdapterError,
)


CAPABILITIES = {
    "label": "JSON-LD (schema.org JobPosting)",
    "supports_pagination": True,
    "supports_categories": False,
    "supports_detail_pages": True,
    "supports_dates": True,
    "supports_location": True,
    "requires_credentials": False,
}


def fetch(source):

    settings = load_settings(source)

    mode = settings.get("mode", "listing")
    start_url = settings.get("start_url") or source.url
    crawl_delay = settings.get("crawl_delay", 0)

    listing_pages = fetch_listing_pages(start_url, settings, crawl_delay)

    if mode == "listing":
        return listing_pages

    if mode == "detail":
        return fetch_detail_pages(listing_pages, settings, crawl_delay, source.name)

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

            content_parts = [description or title]

            location = _extract_location(job.get("jobLocation"))
            if location:
                content_parts.append(location)

            date_posted = job.get("datePosted")
            if date_posted:
                content_parts.append(str(date_posted))

            vacancies.append({
                "title": title,
                "url": urljoin(page["url"], url),
                "content": " | ".join(content_parts),
            })

    return remove_duplicate_vacancies(vacancies)


def _extract_location(job_location):
    """
    schema.org JobLocation is meestal een Place-object met een
    "address" (PostalAddress), maar kan ook een lijst van Places zijn
    (meerdere vestigingen). We pakken de plaatsnaam (addressLocality)
    van de eerste bruikbare entry.
    """

    if not job_location:
        return None

    if isinstance(job_location, list):
        for entry in job_location:
            location = _extract_location(entry)
            if location:
                return location
        return None

    if not isinstance(job_location, dict):
        return None

    address = job_location.get("address")

    if isinstance(address, dict):
        locality = address.get("addressLocality")
        if locality:
            return str(locality)

    if isinstance(address, str):
        return address

    return None


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
