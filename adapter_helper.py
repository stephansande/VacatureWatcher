"""
Adapter Helper.

Doel: iemand die een nieuwe vacaturesite wil toevoegen, hoeft niet
zelf CSS-selectors te gaan zoeken in devtools. Geef een URL op, en
deze module:

  1. haalt de pagina één keer op
  2. probeert, in volgorde van voorkeur:
       a. jsonld_listing      (schema.org JobPosting als JSON-LD -- stabielst)
       b. microdata_listing   (schema.org JobPosting als HTML-attributen)
       c. html_listing        (heuristiek: zoekt een herhalend blok rond
                                vacature-achtige links, met een fallback op
                                herhalende koppen zoals <h2>/<h3> als er
                                geen vacature-achtige linktekst te vinden is,
                                plus daarbinnen een locatie- en datumselector)
       d. generic_links       (de v1-aanpak, werkt altijd wel een beetje)
  3. detecteert daarnaast, los van de gekozen adapter, of de pagina
     paginering heeft en probeert daar een url_pattern uit af te leiden
  4. voert voor elke gevonden kandidaat de ECHTE parse-functie van die
     adapter uit tegen de zojuist opgehaalde pagina, en levert een
     preview van de eerste paar gevonden titels op.

Dit is dus geen slimme AI-gok: het is "probeer de bekende patronen en
laat zien wat elk patroon daadwerkelijk oplevert", zodat de gebruiker
zelf op basis van de preview kan beoordelen welke adapter/instellingen
het beste passen voordat hij ze opslaat.

Belangrijk ontwerpprincipe: deze detectie draait ALLEEN als de
gebruiker op "Analyseren" klikt. De geplande controles
(services/vacancy_checker.py) draaien op de vaste, opgeslagen
selectors uit Source.settings -- niet op een live herhaalde gok bij
elke controle. Dat houdt het gedrag van een bron voorspelbaar: als een
scan andere resultaten geeft, is dat een wijziging op de site, niet
een andere gok van de heuristiek.

Beperkingen (bewust, om niets te verzinnen):
- De html_listing-heuristiek gokt op basis van herhaalde structuur
  rond "vacature-achtige" links (of, als fallback, herhalende koppen).
  Bij ongebruikelijke paginastructuren kan dit mislukken of een te
  brede/smalle selector opleveren -- vandaar altijd de preview +
  total_matches tonen, nooit blind opslaan.
- Locatie/datum-detectie is een class-naam- en tekstpatroon-heuristiek
  (bv. "datum"/"date" in de class, of tekst die op een datum lijkt) --
  kan missen of misgokken bij ongebruikelijke markup. Vandaar altijd
  expliciet tonen wat gevonden is, nooit stilzwijgend aannemen.
- Paginering: als een pagina-2-link gevonden wordt met een herkenbaar
  patroon (?page=2 of /page/2/), wordt een url_pattern voorgesteld.
  Zonder herkenbaar patroon wordt alleen gemeld DAT paginering lijkt te
  bestaan, zonder een (mogelijk verkeerd) patroon te verzinnen.
- cso_api wordt hier niet gedetecteerd: dat vereist een account en is
  al bekend (alleen relevant voor CSO-platformsites).
"""

import re
import json
from types import SimpleNamespace
from urllib.parse import urljoin, urlparse, parse_qs, urlunparse
from collections import Counter

from bs4 import BeautifulSoup

from scraper import fetch_html

from adapters import registry
from adapters import generic_links
from adapters.jsonld_listing import extract_job_postings
from adapters.microdata_listing import extract_job_posting_elements, read_itemprop_text, read_itemprop_url
from adapters.base import load_settings, get_keyword_filters, apply_keyword_filter, AdapterError


MIN_MATCHES = 3
MAX_ANCESTOR_LEVELS = 4
PREVIEW_SIZE = 8
TEST_PREVIEW_LIMIT = 5

VACANCY_KEYWORDS = [
    "vacature",
    "functie",
    "baan",
    "job",
    "career",
    "werken bij",
]

HEADING_TAGS = ["h2", "h3", "h4"]

DATE_PATTERN = re.compile(
    r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b"
    r"|\b\d{1,2}\s+(januari|februari|maart|april|mei|juni|juli|"
    r"augustus|september|oktober|november|december)\b",
    re.IGNORECASE,
)

DATE_CLASS_HINTS = ["datum", "date", "geplaatst", "gepubliceerd", "posted"]
LOCATION_CLASS_HINTS = ["locat", "plaats", "stad", "regio", "location", "city"]

PAGINATION_TEXT_HINTS = ["volgende", "next", "verder", "meer laden"]
PAGINATION_QUERY_KEYS = ["page", "pagina", "p"]


def analyze(url):
    """
    Voert alle detecties uit voor één URL. Geeft altijd een dict terug
    (nooit een exception) zodat de aanroepende route dit veilig direct
    in een template kan tonen.
    """

    result = {
        "url": url,
        "fetch_error": None,
        "jsonld": None,
        "microdata": None,
        "html_listing": None,
        "generic_links": None,
        "pagination": None,
        "recommendation": None,
    }

    try:
        html = fetch_html(url)
    except Exception as error:
        result["fetch_error"] = str(error)
        return result

    soup = BeautifulSoup(html, "lxml")

    result["jsonld"] = _detect_jsonld(html, url)
    result["microdata"] = _detect_microdata(html, url)
    result["html_listing"] = _detect_html_listing(soup, url)
    result["generic_links"] = _detect_generic_links(html, url)
    result["pagination"] = _detect_pagination(soup, url)

    pagination_settings = None

    if result["pagination"] and result["pagination"].get("url_pattern"):
        pagination_settings = {
            "url_pattern": result["pagination"]["url_pattern"],
            "max_pages": result["pagination"]["max_pages"],
        }

    if pagination_settings:

        if result["jsonld"]:
            result["jsonld"]["suggested_settings"]["pagination"] = pagination_settings

        if result["microdata"]:
            result["microdata"]["suggested_settings"]["pagination"] = pagination_settings

        if result["html_listing"]:
            result["html_listing"]["suggested_settings"]["pagination"] = pagination_settings

    if result["jsonld"]:
        result["recommendation"] = "jsonld_listing"
    elif result["microdata"]:
        result["recommendation"] = "microdata_listing"
    elif result["html_listing"]:
        result["recommendation"] = "html_listing"
    elif result["generic_links"]:
        result["recommendation"] = "generic_links"

    return result


def _detect_microdata(html, base_url):

    job_elements = extract_job_posting_elements(html)

    if not job_elements:
        return None

    preview = []

    for element in job_elements:

        title = (
            read_itemprop_text(element, "title")
            or read_itemprop_text(element, "name")
        )

        if not title:
            continue

        job_url = read_itemprop_url(element, "url") or base_url

        preview.append({
            "title": title,
            "url": urljoin(base_url, job_url),
        })

    if not preview:
        return None

    return {
        "count": len(preview),
        "preview": preview[:PREVIEW_SIZE],
        "suggested_settings": {
            "start_url": base_url,
            "mode": "listing",
        },
    }


def _detect_jsonld(html, base_url):

    postings = extract_job_postings(html)

    if not postings:
        return None

    preview = []

    for job in postings:

        title = job.get("title")

        if not title:
            continue

        job_url = job.get("url") or base_url

        preview.append({
            "title": title,
            "url": urljoin(base_url, job_url),
        })

    if not preview:
        return None

    return {
        "count": len(preview),
        "preview": preview[:PREVIEW_SIZE],
        "suggested_settings": {
            "start_url": base_url,
            "mode": "listing",
        },
    }


def _detect_generic_links(html, base_url):

    fake_source = SimpleNamespace(url=base_url)

    items = generic_links.parse(html, fake_source)

    if not items:
        return None

    return {
        "count": len(items),
        "preview": items[:PREVIEW_SIZE],
    }


def _detect_html_listing(soup, base_url):

    result = _detect_via_vacancy_links(soup, base_url)

    if result:
        return result

    return _detect_via_headings(soup, base_url)


def _detect_via_vacancy_links(soup, base_url):
    """
    Primaire strategie: zoekt links waarvan de tekst/href op een
    vacature wijst (bv. "Bekijk deze vacature"), en kijkt op welk
    voorouder-niveau die het vaakst een eigen container delen.
    """

    candidates = []

    for link in soup.find_all("a", href=True):

        text = link.get_text(" ", strip=True)

        if not text:
            continue

        if _looks_like_vacancy_link(text, link["href"]):
            candidates.append(link)

    if len(candidates) < MIN_MATCHES:
        return None

    best = _find_best_ancestor_signature(candidates)

    if not best:
        return None

    anchor_classes = best["anchor_element"].get("class") or []

    title_selector = (
        "a." + ".".join(anchor_classes) if anchor_classes else "a"
    )

    return _build_html_listing_result(
        soup, base_url, best["item_element"], best["anchor_element"],
        title_selector, link_selector=title_selector,
        url_from="title_element",
    )


def _detect_via_headings(soup, base_url):
    """
    Fallback-strategie: als er geen vacature-achtige linktekst te
    vinden is (bv. omdat de titel in een kop staat en de link zelf
    "Lees meer"/"Solliciteer" heet), probeer dan herhalende koppen
    (h2/h3/h4) als titel, met de eerste link in hetzelfde blok als URL.
    """

    candidates = []

    for tag_name in HEADING_TAGS:
        for heading in soup.find_all(tag_name):
            if heading.get_text(strip=True):
                candidates.append(heading)

    if len(candidates) < MIN_MATCHES:
        return None

    best = _find_best_ancestor_signature(candidates)

    if not best:
        return None

    heading_element = best["anchor_element"]
    heading_classes = heading_element.get("class") or []

    title_selector = (
        heading_element.name + "." + ".".join(heading_classes)
        if heading_classes else heading_element.name
    )

    return _build_html_listing_result(
        soup, base_url, best["item_element"], heading_element,
        title_selector, link_selector="a",
        url_from="first_link_in_item",
    )


def _build_html_listing_result(soup, base_url, item_element, title_source_element,
                                title_selector, link_selector, url_from):
    """
    Gedeelde postprocessing voor beide strategieën hierboven: bepaalt
    item_selector, detecteert locatie/datum, bouwt de preview op en
    het uiteindelijke resultaat-dict. url_from bepaalt of de URL van
    het titel-element zelf komt (vacancy-links-strategie) of van de
    eerste link binnen het item (headings-strategie, want een kop
    heeft zelf geen href).
    """

    item_selector = _css_selector_for(item_element)

    location_selector, date_selector = _detect_location_and_date_selectors(
        item_element, title_source_element
    )

    items = soup.select(item_selector)

    preview = []

    for item in items:

        title_el = item.select_one(title_selector)

        if not title_el:
            continue

        if url_from == "title_element":
            href = title_el.get("href")
        else:
            link_el = item.find("a", href=True)
            href = link_el.get("href") if link_el else None

        if not href:
            continue

        preview_item = {
            "title": title_el.get_text(" ", strip=True),
            "url": urljoin(base_url, href),
        }

        if location_selector:
            location_el = item.select_one(location_selector)
            if location_el:
                preview_item["location"] = location_el.get_text(" ", strip=True)

        if date_selector:
            date_el = item.select_one(date_selector)
            if date_el:
                preview_item["date"] = date_el.get_text(" ", strip=True)

        preview.append(preview_item)

    if len(preview) < MIN_MATCHES:
        return None

    selectors = {
        "item": item_selector,
        "title": title_selector,
        "link": link_selector,
    }

    if location_selector:
        selectors["location"] = location_selector

    if date_selector:
        selectors["date"] = date_selector

    return {
        "item_selector": item_selector,
        "title_selector": title_selector,
        "location_selector": location_selector,
        "date_selector": date_selector,
        "total_matches": len(items),
        "preview": preview[:PREVIEW_SIZE],
        "suggested_settings": {
            "start_url": base_url,
            "selectors": selectors,
        },
    }


def _detect_location_and_date_selectors(item_element, anchor_element):
    """
    Zoekt binnen één vacature-blok naar een locatie- en datumveld,
    op basis van class-naam-hints en (voor datum) een tekstpatroon.
    Slaat de titel-link zelf en zijn eventuele omhullende elementen
    over, zodat we niet twee keer dezelfde titeltekst als "locatie"
    aanmerken.
    """

    location_selector = None
    date_selector = None

    anchor_ancestors = set(id(node) for node in anchor_element.parents)
    anchor_ancestors.add(id(anchor_element))

    for descendant in item_element.find_all(True):

        if id(descendant) in anchor_ancestors:
            continue

        if descendant.find(True) and descendant.find(True) is not None and len(descendant.find_all(True)) > 3:
            # te groot/samengesteld om een los locatie-/datumveld te zijn
            continue

        text = descendant.get_text(" ", strip=True)

        if not text or len(text) > 60:
            continue

        classes = descendant.get("class") or []
        class_str = " ".join(classes).lower()

        if not date_selector and (
            DATE_PATTERN.search(text) or any(hint in class_str for hint in DATE_CLASS_HINTS)
        ):
            date_selector = _css_selector_for(descendant)
            continue

        if not location_selector and any(hint in class_str for hint in LOCATION_CLASS_HINTS):
            location_selector = _css_selector_for(descendant)

        if location_selector and date_selector:
            break

    return location_selector, date_selector


def _detect_pagination(soup, base_url):
    """
    Zoekt naar een paginanummer-link (bv. "2") of een "volgende"-link,
    en probeert daaruit een url_pattern met {page} af te leiden.
    Geeft None als geen enkele aanwijzing voor paginering gevonden is.
    """

    page_two_url = None
    pagination_detected = False

    for link in soup.find_all("a", href=True):

        text = link.get_text(strip=True).lower()

        if text == "2":
            page_two_url = urljoin(base_url, link["href"])
            pagination_detected = True
            break

        if any(hint in text for hint in PAGINATION_TEXT_HINTS):
            pagination_detected = True

    if not pagination_detected:
        return None

    if not page_two_url:
        return {
            "detected": True,
            "url_pattern": None,
            "max_pages": None,
            "note": (
                "Er lijkt paginering te bestaan, maar er kon geen "
                "betrouwbaar url-patroon worden afgeleid. Vul "
                "settings.pagination.url_pattern handmatig in."
            ),
        }

    pattern = _derive_page_pattern(page_two_url)

    if not pattern:
        return {
            "detected": True,
            "url_pattern": None,
            "max_pages": None,
            "note": (
                "Paginering gevonden (link naar pagina 2), maar het "
                "url-patroon kon niet automatisch herkend worden. "
                f"Voorbeeld-URL van pagina 2: {page_two_url}"
            ),
        }

    return {
        "detected": True,
        "url_pattern": pattern,
        "max_pages": 3,
        "note": None,
    }


def _derive_page_pattern(page_two_url):

    parsed = urlparse(page_two_url)
    query = parse_qs(parsed.query)

    for key in PAGINATION_QUERY_KEYS:

        if key in query:

            new_query_parts = []

            for existing_key, values in query.items():
                value = "{page}" if existing_key == key else values[0]
                new_query_parts.append(f"{existing_key}={value}")

            new_query = "&".join(new_query_parts)

            return urlunparse(parsed._replace(query=new_query))

    match = re.search(r"/(page|pagina)/(\d+)/?", page_two_url)

    if match:
        return page_two_url[:match.start(2)] + "{page}" + page_two_url[match.end(2):]

    return None


def _find_best_ancestor_signature(candidates):
    """
    Zoekt het niveau (1-4 ouders omhoog) waarop de vacature-achtige
    links het vaakst een GEDEELDE, maar onderling VERSCHILLENDE
    ouder-container hebben -- dat is typisch het "vacature-blok".

    Geeft bij het eerste geldige niveau (kleinste = meest precieze
    container) een voorbeeld-element terug, of None als niets
    overtuigend genoeg is.
    """

    for level in range(1, MAX_ANCESTOR_LEVELS + 1):

        signature_counts = Counter()
        signature_examples = {}
        signature_ancestor_ids = {}

        for link in candidates:

            ancestor = link
            reached = True

            for _ in range(level):

                if ancestor.parent is None:
                    reached = False
                    break

                ancestor = ancestor.parent

            if not reached or ancestor is None:
                continue

            if ancestor.name in ("html", "body", "[document]"):
                continue

            signature = _element_signature(ancestor)

            signature_counts[signature] += 1
            signature_ancestor_ids.setdefault(signature, set()).add(id(ancestor))
            signature_examples.setdefault(signature, (link, ancestor))

        for signature, count in signature_counts.items():

            distinct_ancestors = len(signature_ancestor_ids[signature])

            if count >= MIN_MATCHES and distinct_ancestors >= MIN_MATCHES:

                anchor_element, item_element = signature_examples[signature]

                return {
                    "level": level,
                    "count": count,
                    "distinct_ancestors": distinct_ancestors,
                    "anchor_element": anchor_element,
                    "item_element": item_element,
                }

    return None


def test_source(source, limit=TEST_PREVIEW_LIMIT):
    """
    Voert de daadwerkelijke adapter van een bestaande Source uit
    ("Bron testen"-knop), maar dan licht: paginering/detail-fetches
    worden tijdelijk beperkt zodat een test geen volledige scrape
    van de doelsite triggert. Doet GEEN database-writes en verstuurt
    GEEN notificaties -- puur lezen en tonen.

    Hergebruikt exact dezelfde adapter + settings + keyword-filter-
    pijplijn als de echte geplande controle (services/vacancy_checker.py),
    zodat "Bron testen" representatief is voor wat een scan zou vinden.
    """

    result = {
        "error": None,
        "count": 0,
        "preview": [],
    }

    try:
        adapter = registry.get(source.adapter)
    except AdapterError as error:
        result["error"] = str(error)
        return result

    test_settings_json = _cap_settings_for_test(source.settings, limit)

    test_source_obj = SimpleNamespace(
        id=getattr(source, "id", None),
        name=source.name,
        url=source.url,
        adapter=source.adapter,
        settings=test_settings_json,
        keywords=source.keywords,
    )

    try:
        raw_content = adapter.fetch(test_source_obj)
        vacancies = adapter.parse(raw_content, test_source_obj)

        settings = load_settings(test_source_obj)
        include_keywords, exclude_keywords = get_keyword_filters(test_source_obj, settings)

        vacancies = apply_keyword_filter(
            vacancies,
            include_keywords=include_keywords,
            exclude_keywords=exclude_keywords,
        )

        result["count"] = len(vacancies)
        result["preview"] = vacancies[:limit]

    except AdapterError as error:
        result["error"] = str(error)
    except Exception as error:
        result["error"] = f"Onverwachte fout: {error}"

    return result


def _cap_settings_for_test(settings_json, limit):
    """
    Beperkt pagination.max_pages, max_items en max_rows (indien
    aanwezig) tot maximaal `limit`, zodat een test-run geen zware
    meerdere-pagina's-scrape of tientallen detail-page-requests
    veroorzaakt. Laat settings ongewijzigd als er niets te beperken
    valt of als de JSON ongeldig is (dan merkt de echte adapter dat
    zelf op).
    """

    if not settings_json:
        return settings_json

    try:
        data = json.loads(settings_json)
    except (ValueError, TypeError):
        return settings_json

    if not isinstance(data, dict):
        return settings_json

    if isinstance(data.get("pagination"), dict):
        data["pagination"] = dict(data["pagination"])
        current_max = data["pagination"].get("max_pages", limit)
        data["pagination"]["max_pages"] = min(current_max, limit)

    for key in ("max_items", "max_rows"):
        if key in data:
            data[key] = min(data[key], limit)

    return json.dumps(data)


def _looks_like_vacancy_link(text, href):

    haystack = (text + " " + href).lower()

    return any(keyword in haystack for keyword in VACANCY_KEYWORDS)


def _element_signature(element):

    classes = element.get("class") or []

    if classes:
        return element.name + "." + ".".join(sorted(classes))

    return element.name


def _css_selector_for(element):

    classes = element.get("class") or []

    if classes:
        return "." + ".".join(classes)

    return element.name
