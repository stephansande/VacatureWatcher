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

import site_fingerprint
from adapters import greenhouse


MIN_MATCHES = 3
MIN_MATCHES_FALLBACK = 2
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

COMMON_ITEM_HINTS = [
    ".vacature",
    ".vacature-item",
    ".vacancy",
    ".job",
    ".job-item",
    ".job-listing",
    "article",
]
# Extra KANDIDATEN voor _detect_via_common_classes, geen garanties --
# elke hint moet nog steeds >= MIN_MATCHES elementen opleveren mét een
# vindbare titel/link erin, anders wordt de volgende hint geprobeerd
# (of uiteindelijk niets gevonden). Bewust kort gehouden: te veel/te
# generieke hints (bv. ".card", ".item") verhogen het risico op een
# fout-positieve match met niet-vacature-content.

MAX_TITLE_LENGTH = 120
# zelfde grens en zelfde reden als adapters/generic_links.py: een hele
# alinea marketingtekst als linktekst mag nooit als vacaturetitel
# doorgaan, ook al matcht een keyword toevallig in de URL.

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

UTILITY_CLASS_PATTERN = re.compile(
    r"^(mb|mt|ml|mr|mx|my|p|pb|pt|pl|pr|px|py|w|h|max-w|max-h|min-w|min-h|"
    r"border|text|bg|flex|grid|justify|items|content|self|gap|rounded|shadow|"
    r"font|leading|tracking|opacity|z|order|col|row|divide|space)"
    r"(-|$)"
)
# herkent Tailwind-achtige utility-classnamen (bv. "mb-3", "border-b",
# "justify-between") -- gebruikt om zulke containers als laatste
# redmiddel te behandelen in _find_best_ancestor_signature, zie daar.


JS_RENDERING_MARKERS = [
    'id="root"',
    'id="app"',
    'id="__next"',
    "data-reactroot",
    "ng-version",
]

MIN_VISIBLE_TEXT_FOR_STATIC_PAGE = 200


def diagnose_source(source, limit=TEST_PREVIEW_LIMIT):
    """
    Zoals test_source(), maar met een categorisering van het resultaat
    erbovenop -- bedoeld voor de bulk-diagnosepagina (Systeem ->
    Bronnen diagnosticeren), zodat je in één keer een overzicht krijgt
    van AL je bronnen in plaats van er één voor één doorheen te moeten
    (zoals we net handmatig deden voor dierenbescherming.nl).

    category is een van: "ok", "geen_resultaten", "fout".
    hint is een korte, mens-leesbare duiding -- bij "geen_resultaten"
    een VERMOEDEN (nooit een zekerheid) of het om JavaScript-rendering
    kan gaan.
    """

    result = test_source(source, limit=limit)

    diagnosis = {
        "source_id": getattr(source, "id", None),
        "source_name": source.name,
        "adapter": source.adapter,
        "error": result["error"],
        "count": result["count"],
        "preview": result["preview"],
        "category": None,
        "hint": None,
    }

    if result["error"]:
        diagnosis["category"] = "fout"
        diagnosis["hint"] = _classify_error(result["error"])

    elif result["count"] == 0:
        diagnosis["category"] = "geen_resultaten"
        diagnosis["hint"] = _suspect_js_rendering_for_url(source.url)

    else:
        diagnosis["category"] = "ok"

    return diagnosis


def _suspect_js_rendering_for_url(url):
    """
    Wrapper om _suspect_js_rendering() te gebruiken vanuit
    diagnose_source(), waar de HTML nog niet is opgehaald (in
    tegenstelling tot analyze(), dat 'm al in huis heeft).
    """

    try:
        html = fetch_html(url)
    except Exception:
        return (
            "Geen vacatures gevonden, en de pagina kon niet nogmaals "
            "opgehaald worden om verder te duiden."
        )

    hint = _suspect_js_rendering(html)

    if hint:
        return hint

    return (
        "Geen vacatures gevonden, maar geen duidelijk signaal van "
        "JavaScript-rendering -- controleer de adapter-instellingen "
        "(selectors/mode) via Analyseren op de bewerkpagina."
    )


def _classify_error(error_message):

    lowered = error_message.lower()

    if "404" in lowered:
        return "Pagina niet gevonden (404) -- klopt de URL nog?"

    if "403" in lowered:
        return "Toegang geweigerd (403) -- de site blokkeert mogelijk geautomatiseerde toegang."

    if "timeout" in lowered or "timed out" in lowered:
        return "Time-out -- de site reageerde niet op tijd."

    if "onbekende adapter" in lowered:
        return "De ingestelde adapter bestaat niet (meer) -- controleer de bron-instellingen."

    if "json" in lowered:
        return "Het settings-veld van deze bron bevat geen geldige JSON."

    return "Zie de volledige foutmelding hiernaast."


def _suspect_js_rendering(html):
    """
    Heuristiek, GEEN zekerheid: kijkt of de (al opgehaalde) HTML
    kenmerken van een JavaScript-applicatie vertoont (weinig zichtbare
    tekst t.o.v. veel <script>-tags, of bekende SPA-markers zoals
    id="root"). Dit is dezelfde soort signaal die we bij
    dierenbescherming.nl en werkbijdunea.nl handmatig herkenden
    ("Geen resultaten gevonden"-placeholder / onuitgevoerde
    template-placeholders zoals "{{ ItemsCount }}", zonder
    daadwerkelijke vacaturedata in de HTML).

    Gebruikt door zowel diagnose_source() (bulk-diagnose) als
    analyze() (Adapter Helper) -- op dezelfde, al opgehaalde HTML, dus
    geen dubbele request naar de doelsite.
    """

    soup = BeautifulSoup(html, "lxml")

    body = soup.find("body")
    visible_text_length = len(body.get_text(strip=True)) if body else 0
    script_count = len(soup.find_all("script"))

    markers_found = [marker for marker in JS_RENDERING_MARKERS if marker in html]

    if markers_found or (visible_text_length < MIN_VISIBLE_TEXT_FOR_STATIC_PAGE and script_count > 5):
        return (
            "Vermoedelijk JavaScript-rendering: deze pagina bevat weinig "
            "zichtbare tekst en/of kenmerken van een JS-applicatie -- de "
            "vacaturedata wordt waarschijnlijk pas door de browser "
            "ingevuld en staat niet in de opgehaalde HTML. Zie "
            "'Beperkingen' in de README."
        )

    return None


def _detect_meta_generator(soup):
    """Leest <meta name="generator">, indien aanwezig. Puur signaal."""

    tag = soup.find("meta", attrs={"name": "generator"})

    if tag and tag.get("content"):
        return tag["content"].strip()

    return None


def _detect_script_domains(soup, base_url):
    """Unieke externe scriptbron-hostnamen. Puur signaal."""

    own_domain = urlparse(base_url).netloc.lower()
    domains = set()

    for script in soup.find_all("script", src=True):

        parsed = urlparse(urljoin(base_url, script["src"]))
        domain = parsed.netloc.lower()

        if domain and domain != own_domain:
            domains.add(domain)

    return sorted(domains)


def _gather_signals(html, url, soup=None):
    """Verzamelt ruwe features, zonder al een aanbeveling te maken."""

    if soup is None:
        soup = BeautifulSoup(html, "lxml")

    return {
        "url": url,
        "jsonld": _detect_jsonld(html, url),
        "microdata": _detect_microdata(html, url),
        "html_listing": _detect_html_listing(soup, url),
        "generic_links": _detect_generic_links(html, url),
        "pagination": _detect_pagination(soup, url),
        "meta_generator": _detect_meta_generator(soup),
        "script_domains": _detect_script_domains(soup, url),
        "js_rendering_hint": _suspect_js_rendering(html),
    }


def _classify(signals):
    """Beslist, puur op basis van signalen, welke adapter wint."""

    if greenhouse.matches_fingerprint(signals.get("url"), signals.get("script_domains")):
        return {
            "recommendation": "greenhouse",
            "confidence": site_fingerprint.confidence_for("greenhouse"),
            "js_rendering_hint": None,
        }

    if signals.get("jsonld"):
        recommendation = "jsonld_listing"
    elif signals.get("microdata"):
        recommendation = "microdata_listing"
    elif signals.get("html_listing"):
        recommendation = "html_listing"
    elif signals.get("generic_links"):
        recommendation = "generic_links"
    else:
        recommendation = None

    confidence = (
        site_fingerprint.confidence_for(recommendation)
        if recommendation else None
    )

    return {
        "recommendation": recommendation,
        "confidence": confidence,
        "js_rendering_hint": signals.get("js_rendering_hint") if recommendation is None else None,
    }


def analyze(url, force_refresh=False):
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
        "meta_generator": None,
        "script_domains": [],
        "js_rendering_hint": None,
        "recommendation": None,
        "from_cache": False,
        "cache_confidence": None,
        "cached_settings": None,
        "recommended_settings": None,
    }

    cached = None if force_refresh else site_fingerprint.lookup(url)

    if cached and site_fingerprint.is_fresh(cached):
        result["recommendation"] = cached.adapter
        result["from_cache"] = True
        result["cache_confidence"] = cached.confidence
        result["cached_settings"] = json.loads(cached.settings) if cached.settings else None
        result["recommended_settings"] = result["cached_settings"]
        return result

    try:
        html = fetch_html(url)
    except Exception as error:
        result["fetch_error"] = str(error)
        return result

    soup = BeautifulSoup(html, "lxml")

    signals = _gather_signals(html, url, soup=soup)
    classification = _classify(signals)

    pagination_settings = None

    if signals["pagination"] and signals["pagination"].get("url_pattern"):
        pagination_settings = {
            "url_pattern": signals["pagination"]["url_pattern"],
            "max_pages": signals["pagination"]["max_pages"],
        }

    if pagination_settings:
        for key in ("jsonld", "microdata", "html_listing"):
            if signals[key]:
                signals[key]["suggested_settings"]["pagination"] = pagination_settings

    result.update({
        "jsonld": signals["jsonld"],
        "microdata": signals["microdata"],
        "html_listing": signals["html_listing"],
        "generic_links": signals["generic_links"],
        "pagination": signals["pagination"],
        "meta_generator": signals["meta_generator"],
        "script_domains": signals["script_domains"],
        "js_rendering_hint": classification["js_rendering_hint"],
        "recommendation": classification["recommendation"],
    })

    if result["recommendation"]:

        candidate_by_recommendation = {
            "jsonld_listing": result["jsonld"],
            "microdata_listing": result["microdata"],
            "html_listing": result["html_listing"],
            "generic_links": None,
            "greenhouse": None,
        }

        candidate = candidate_by_recommendation.get(result["recommendation"])
        suggested_settings = candidate.get("suggested_settings") if candidate else None

        if result["recommendation"] == "greenhouse":
            board_token = greenhouse.derive_board_token(url)
            # None als dit een embed op een eigen domein is (geen
            # greenhouse.io-URL) -- dan moet board_token straks
            # handmatig ingevuld worden, zie adapters/greenhouse.py
            suggested_settings = {"board_token": board_token} if board_token else None

        result["recommended_settings"] = suggested_settings

        site_fingerprint.save(
            url,
            adapter=result["recommendation"],
            settings_dict=suggested_settings,
            confidence=classification["confidence"],
        )

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

    result = _detect_via_headings(soup, base_url)

    if result:
        return result

    return _detect_via_common_classes(soup, base_url)


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


TITLE_CLASS_HINTS = ["title", "titel", "naam", "name", "functie", "vacature-titel"]


def _find_title_like_element(item_element):
    """
    Zoekt binnen item_element naar een element waarvan de class-naam
    op een titel/naam-veld wijst (bv. class="title" of "vacature-titel"),
    als tussenstap tussen "geen heading gevonden" en "dan maar de link
    zelf als titel gebruiken" -- dat laatste levert vaak een linktekst
    als "Bekijk"/"Lees meer" op i.p.v. de echte titel.
    """

    for element in item_element.find_all(True):

        classes = element.get("class") or []
        class_str = " ".join(classes).lower()

        if any(hint in class_str for hint in TITLE_CLASS_HINTS):

            text = element.get_text(" ", strip=True)

            if text and len(text) <= MAX_TITLE_LENGTH:
                return element

    return None


def _detect_via_common_classes(soup, base_url):
    """
    Derde en laatste fallback: probeert een klein aantal veelgebruikte
    class-/tag-namen voor vacature-blokken (".vacancy", ".job",
    ".vacature", "article") als KANDIDAAT-containers.

    Belangrijk verschil met een blinde gok: dit wordt nooit direct
    opgeslagen. Zodra een hint genoeg elementen oplevert (>= MIN_MATCHES),
    wordt er nog steeds een titel/link binnen elk element gezocht en een
    preview opgebouwd -- exact dezelfde verificatie-stap als de andere
    twee strategieën. Levert de hint geen bruikbare titel/link op, dan
    wordt de volgende hint geprobeerd; levert niets iets op, dan geeft
    de Adapter Helper eerlijk "niets gevonden" terug in plaats van iets
    te verzinnen.
    """

    for hint_selector in COMMON_ITEM_HINTS:

        items = soup.select(hint_selector)

        if len(items) < MIN_MATCHES:
            continue

        sample_item = items[0]

        title_element = None

        for tag_name in HEADING_TAGS:
            title_element = sample_item.find(tag_name)
            if title_element:
                break

        if title_element is None:
            title_element = _find_title_like_element(sample_item)

        if title_element is None:
            title_element = sample_item.find("a")

        if title_element is None:
            continue

        title_classes = title_element.get("class") or []

        title_selector = (
            title_element.name + "." + ".".join(title_classes)
            if title_classes else title_element.name
        )

        url_from = "title_element" if title_element.name == "a" else "first_link_in_item"

        result = _build_html_listing_result(
            soup, base_url, sample_item, title_element,
            title_selector, link_selector=("a" if url_from == "first_link_in_item" else title_selector),
            url_from=url_from,
            item_selector_override=hint_selector,
        )

        if result:
            return result

    return None


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
                                title_selector, link_selector, url_from,
                                item_selector_override=None):
    """
    Gedeelde postprocessing voor alle drie strategieën hierboven: bepaalt
    item_selector, detecteert locatie/datum, bouwt de preview op en
    het uiteindelijke resultaat-dict. url_from bepaalt of de URL van
    het titel-element zelf komt (vacancy-links-strategie) of van de
    eerste link binnen het item (headings/common-classes-strategie,
    voor een kop of een generieke container die zelf geen href heeft).

    item_selector_override: gebruikt door _detect_via_common_classes,
    omdat daar de LOSSE hint (bv. ".vacature") de juiste selector is --
    _css_selector_for(item_element) zou anders de volledige, mogelijk
    item-specifieke classlist van precies dat ene voorbeeld-element
    pakken (bv. ".vacature.featured" als toevallig het eerste
    voorbeeld een extra statusklasse heeft), wat de andere items zou
    missen.
    """

    item_selector = item_selector_override or _css_selector_for(item_element)

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

    if len(preview) < MIN_MATCHES_FALLBACK:
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

    Drie voorkeursniveaus, in deze volgorde:
      1. Een "schone" (niet util-class-zware) signature met >= MIN_MATCHES
         treffers -- de normale, meest betrouwbare uitkomst.
      2. Een util-class-zware (Tailwind-achtige, bv. "mb-3 border-b
         border-gray-400") signature met >= MIN_MATCHES treffers --
         zulke klassen komen vaak voor op generieke navigatie-/
         categorie-links (die toevallig ook een vacature-keyword in
         hun URL hebben), dus alleen als niets beters bestaat.
      3. Een schone signature met slechts >= MIN_MATCHES_FALLBACK (2)
         treffers -- voor het heel normale geval van een sterk
         gefilterd zoekresultaat met weinig vacatures. NOOIT
         util-class-zwaar op dit lage aantal: bij een zwak signaal
         (maar 2 matches) is extra zekerheid over "dit lijkt op een
         echt vacature-blok, niet op generieke opmaak" belangrijker.

    Ontdekt via een echt gemeentebanen.nl-scenario: 7 regio-
    navigatielinks (util-class-zwaar) versus 2 echte, gefilterde
    vacatures (schoon, maar te weinig voor de normale drempel) --
    zonder deze volgorde koos de heuristiek de verkeerde, talrijkere
    groep.
    """

    utility_fallback = None
    low_confidence_clean_fallback = None

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

        clean_candidates = []

        for signature, count in signature_counts.items():

            distinct_ancestors = len(signature_ancestor_ids[signature])

            if count < MIN_MATCHES_FALLBACK or distinct_ancestors < MIN_MATCHES_FALLBACK:
                continue

            anchor_element, item_element = signature_examples[signature]

            is_utility = _is_utility_heavy(item_element.get("class") or [])

            meets_primary_threshold = (
                count >= MIN_MATCHES and distinct_ancestors >= MIN_MATCHES
            )

            candidate_result = {
                "level": level,
                "count": count,
                "distinct_ancestors": distinct_ancestors,
                "anchor_element": anchor_element,
                "item_element": item_element,
            }

            if meets_primary_threshold and not is_utility:
                clean_candidates.append(candidate_result)

            elif meets_primary_threshold and is_utility:
                if utility_fallback is None:
                    utility_fallback = candidate_result

            elif not is_utility:
                if low_confidence_clean_fallback is None:
                    low_confidence_clean_fallback = candidate_result

        if clean_candidates:
            return max(clean_candidates, key=lambda c: c["distinct_ancestors"])

    return low_confidence_clean_fallback or utility_fallback


def _is_utility_heavy(classes):
    """
    True als een classlist er meer als Tailwind-achtige utility-soep
    uitziet (bv. "mb-3 border-b border-gray-400 flex justify-between")
    dan als een betekenisvolle component-naam (bv. "vacature-item").
    Twee of meer utility-achtige klassen is de drempel -- één losse
    "flex" naast een echte naam ("vacature-card flex") mag nog steeds
    als schoon gelden.
    """

    if not classes:
        return False

    utility_count = sum(1 for cls in classes if UTILITY_CLASS_PATTERN.match(cls))

    return utility_count >= 2


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


def raw_fetch_debug(source):
    """
    Haalt de bron-URL rechtstreeks op met dezelfde fetch_html() die
    alle adapters gebruiken, en geeft de RUWE respons terug -- lengte,
    een voorbeeld van de eerste tekens, en een voorzichtige hint of de
    respons op een blokkade lijkt. Geen enkele adapter- of
    selector-logica hiertussen.

    Bedoeld voor precies het scenario waar we tegenaan liepen bij Werk
    bij Dunea: zowel de Adapter Helper als een handmatig ingestelde
    adapter vonden 0 vacatures. Als BEIDE onafhankelijke paden niets
    vinden, zit het probleem waarschijnlijk niet bij een selector maar
    bij wat er al binnenkomt vóórdat er ook maar naar HTML gekeken
    wordt (blokkade, omleiding, cookie-muur, JavaScript-afhankelijke
    inhoud). Dit maakt dat verschil zichtbaar zonder dat je een shell
    in de container hoeft te openen.

    "looks_blocked" is een HINT, geen zekerheid -- gebaseerd op een
    ongebruikelijk korte respons of een paar veelvoorkomende
    bot-detectie-teksten. Beoordeel de preview altijd zelf; dit
    voorkomt alleen dat je die met de hand hoeft te doorzoeken.
    """

    result = {
        "url": None,
        "error": None,
        "length": None,
        "preview": None,
        "looks_blocked": None,
    }

    settings = load_settings(source)
    url = settings.get("start_url") or source.url
    result["url"] = url

    try:
        html = fetch_html(url)
    except Exception as error:
        result["error"] = str(error)
        return result

    result["length"] = len(html)
    result["preview"] = html[:2000]

    lowered = html.lower()
    blocked_hints = [
        "captcha",
        "access denied",
        "are you a robot",
        "just a moment",
        "attention required",
        "checking your browser",
    ]
    result["looks_blocked"] = (
        len(html) < 1000
        or any(hint in lowered for hint in blocked_hints)
    )

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

    if len(text) > MAX_TITLE_LENGTH:
        return False

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
