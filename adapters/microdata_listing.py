"""
Adapter: microdata_listing

Naast JSON-LD (zie jsonld_listing.py) bestaat er nog een tweede manier
waarop sites schema.org JobPosting-data aanbieden: microdata, direct
als HTML-attributen op de bestaande elementen:

    <div itemscope itemtype="https://schema.org/JobPosting">
        <h2 itemprop="title">Beleidsmedewerker Cultuur</h2>
        <div itemprop="description">...</div>
        <span itemprop="datePosted">2026-07-01</span>
        <div itemprop="jobLocation" itemscope itemtype="https://schema.org/Place">
            <span itemprop="address" itemscope itemtype="https://schema.org/PostalAddress">
                <span itemprop="addressLocality">Utrecht</span>
            </span>
        </div>
        <a itemprop="url" href="/vacature/123">Bekijk vacature</a>
    </div>

Zelfde twee modi als jsonld_listing.py (settings.mode):

  "listing" -- de listing/zoekpagina zelf bevat al itemscope-blokken.
  "detail"  -- de listingpagina bevat alleen links naar detailpagina's,
               die elk zelf een JobPosting-microdata-blok bevatten.

Voorbeeld Source.settings (mode "listing"):
{
    "start_url": "https://example-vacaturesite.nl/vacatures/",
    "mode": "listing",
    "pagination": {"url_pattern": "https://example-vacaturesite.nl/vacatures/page/{page}/", "max_pages": 3},
    "crawl_delay": 5
}

Net als bij JSON-LD is dit stabieler dan handmatige CSS-selectors: een
redesign van de pagina raakt meestal de zichtbare opmaak, niet de
onderliggende itemprop-attributen.
"""

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from adapters.base import (
    load_settings,
    fetch_listing_pages,
    fetch_detail_pages,
    remove_duplicate_vacancies,
    AdapterError,
)


JOB_POSTING_TYPES = (
    "https://schema.org/JobPosting",
    "http://schema.org/JobPosting",
    "schema.org/JobPosting",
)


CAPABILITIES = {
    "label": "Microdata (schema.org, HTML-attributen)",
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
        f"'{source.name}': onbekende microdata_listing mode '{mode}' "
        "(verwacht 'listing' of 'detail')"
    )


def parse(raw_pages, source):

    vacancies = []

    for page in raw_pages:

        for job_element in extract_job_posting_elements(page["html"]):

            title = _read_itemprop_text(job_element, "title") or _read_itemprop_text(job_element, "name")

            if not title:
                continue

            url = _read_itemprop_url(job_element, "url") or page["url"]
            description = _read_itemprop_text(job_element, "description")

            content_parts = [description or title]

            location = _read_location(job_element)
            if location:
                content_parts.append(location)

            date_posted = _read_itemprop_text(job_element, "datePosted")
            if date_posted:
                content_parts.append(date_posted)

            vacancies.append({
                "title": title,
                "url": urljoin(page["url"], url),
                "content": " | ".join(content_parts),
            })

    return remove_duplicate_vacancies(vacancies)


def extract_job_posting_elements(html):
    """
    Zoekt alle elementen met itemscope + itemtype die op
    schema.org/JobPosting wijzen. Publiek (geen underscore-prefix)
    zodat adapter_helper.py dit kan hergebruiken voor detectie.
    """

    soup = BeautifulSoup(html, "lxml")

    elements = []

    for element in soup.find_all(attrs={"itemscope": True}):

        item_type = element.get("itemtype", "")

        if any(item_type.rstrip("/") == job_type.rstrip("/") for job_type in JOB_POSTING_TYPES):
            elements.append(element)

    return elements


def read_itemprop_text(scope_element, prop_name):
    """Publieke wrapper rond _read_itemprop_text, voor hergebruik door adapter_helper.py."""
    return _read_itemprop_text(scope_element, prop_name)


def read_itemprop_url(scope_element, prop_name):
    """Publieke wrapper rond _read_itemprop_url, voor hergebruik door adapter_helper.py."""
    return _read_itemprop_url(scope_element, prop_name)


def _read_itemprop_text(scope_element, prop_name):
    """
    Leest de tekstwaarde van itemprop=prop_name BINNEN scope_element,
    maar NIET binnen een geneste itemscope (anders zou bv. de titel
    van een geneste jobLocation-Place per ongeluk meegepakt worden).
    """

    for element in scope_element.find_all(attrs={"itemprop": prop_name}):

        if _belongs_to_nested_scope(element, scope_element):
            continue

        content_attr = element.get("content")

        if content_attr:
            return content_attr.strip()

        text = element.get_text(" ", strip=True)

        if text:
            return text

    return None


def _read_itemprop_url(scope_element, prop_name):

    for element in scope_element.find_all(attrs={"itemprop": prop_name}):

        if _belongs_to_nested_scope(element, scope_element):
            continue

        href = element.get("href")

        if href:
            return href

        content_attr = element.get("content")

        if content_attr:
            return content_attr

    return None


def _read_location(job_element):

    for location_element in job_element.find_all(attrs={"itemprop": "jobLocation"}):

        if _belongs_to_nested_scope(location_element, job_element):
            continue

        locality = _read_itemprop_text(location_element, "addressLocality")

        if locality:
            return locality

        text = location_element.get_text(" ", strip=True)

        if text:
            return text

    return None


def _belongs_to_nested_scope(element, top_scope):
    """
    True als element zich binnen een ANDERE itemscope bevindt dan
    top_scope (dus een geneste Place/PostalAddress etc.) -- gebruikt
    om te voorkomen dat we itemprop's van geneste objecten verwarren
    met die van de JobPosting zelf.
    """

    parent = element.parent

    while parent is not None and parent is not top_scope:

        if parent.has_attr("itemscope"):
            return True

        parent = parent.parent

    return False
