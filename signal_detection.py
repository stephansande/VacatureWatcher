"""
signal_detection.py

De "waarnemingslaag" van de Website Detective: pure detectiefuncties
die op een AL OPGEHAALDE pagina (HTML-string + BeautifulSoup-object)
zoeken naar signalen -- JSON-LD, microdata, embedded JSON
(hydration-payloads zoals Next.js' __NEXT_DATA__), een herhalend
HTML-blok rond vacature-achtige links/koppen, generieke links,
paginering, en een JavaScript-rendering-vermoeden.

Bewust GEEN beslissingslogica hier ("welke wint?") -- dat is
strategy_selector.py. Dit bestand beantwoordt alleen "wat is er te
zien", nooit "wat betekent dat". Die scheiding is precies waarom
_classify() in strategy_selector.py onafhankelijk van een echte
pagina getest kan worden (zie tests/test_strategy_selector.py).

Afkomstig uit adapter_helper.py (tot 1347 regels gegroeid, 30
functies door elkaar) -- opgesplitst nadat een architectuurreview dit
terecht als grootste onderhoudsrisico aanwees. Zie ook
strategy_selector.py en diagnostics.py voor de andere twee delen.
"""

import re
import json
from urllib.parse import urljoin, urlparse, parse_qs, urlunparse
from collections import Counter
from types import SimpleNamespace

from bs4 import BeautifulSoup

from adapters import generic_links
from adapters.jsonld_listing import extract_job_postings
from adapters.microdata_listing import extract_job_posting_elements, read_itemprop_text, read_itemprop_url


MIN_MATCHES = 3
MIN_MATCHES_FALLBACK = 2
MAX_ANCESTOR_LEVELS = 4
PREVIEW_SIZE = 8

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


# ---------------------------------------------------------------------------
# Embedded JSON (hydration-payloads in de initiële HTML-bron)
#
# Onderscheid met browser_analysis.py's "discovered_requests": dat vangt
# JSON op die via een APARTE netwerkaanroep (XHR/fetch) NA het laden
# binnenkomt. Hier gaat het om JSON die het framework al in de EERSTE,
# rechtstreeks opgehaalde HTML-pagina meestuurt (server-side rendering/
# hydration) -- geen los verzoek nodig om erbij te komen, het zit al in
# `html` dat deze functie meekrijgt.
#
# Twee vormen, bewust verschillend aangepakt:
# - Next.js: een nette <script id="__NEXT_DATA__" type="application/json">
#   -- gewoon geldige JSON in een herkenbaar script-blok, makkelijk en
#   betrouwbaar te vinden/parsen.
# - Nuxt/overig: een JS-toewijzing zoals `window.__NUXT__={...}` binnen
#   een kaal <script>-blok, GEEN apart json-type -- moet het
#   object-literal met accolades-balancering uit de ruwe tekst plukken
#   (_extract_json_after_assignment), en kan soms toch geen strikt
#   geldige JSON zijn (bv. "undefined" als waarde, functie-referenties)
#   -- dan wordt die kandidaat overgeslagen, niet de hele detectie laten
#   crashen.
# ---------------------------------------------------------------------------

EMBEDDED_JSON_ASSIGNMENT_MARKERS = (
    ("window.__NUXT__=", "Nuxt"),
    ("window.__NUXT__ =", "Nuxt"),
    ("window.__INITIAL_STATE__=", "Generiek (Vue/overig, __INITIAL_STATE__)"),
    ("window.__INITIAL_STATE__ =", "Generiek (Vue/overig, __INITIAL_STATE__)"),
)

EMBEDDED_JSON_KEY_HINTS = (
    "title", "vacature", "vacancy", "job", "functie",
    "position", "titel", "naam",
)

EMBEDDED_JSON_MAX_DEPTH = 3
# hydration-payloads zitten vaak dieper genest dan een kale
# API-respons (bv. Next.js' props.pageProps.vacatures) -- vandaar een
# iets diepere zoekgrens dan browser_analysis._find_job_array()
# (die met opzet maar 1 niveau zoekt voor XHR-responses).


def extract_embedded_json_candidates(html):
    """
    Zoekt in `html` naar rauwe JSON-hydration-blobs (__NEXT_DATA__-tag
    of een window.__NUXT__/__INITIAL_STATE__-toekenning) en geeft ze
    terug als [(framework_label, data), ...] -- GEEN oordeel of het
    vacaturedata is, dat doet `_find_job_array_in_json()`.

    Losgetrokken uit `_detect_embedded_json()` (die deze functie nu
    zelf ook gebruikt) zodat `adapters/embedded_json.py` bij een
    geplande controle dezelfde extractie kan hergebruiken op een
    opnieuw opgehaalde pagina, zonder de detectie-heuristiek
    (job-array-zoektocht, preview-opbouw) te dupliceren. Puur
    mechanisch: geen gedragswijziging t.o.v. de oude inline versie.
    """

    candidates = []

    soup = BeautifulSoup(html, "lxml")
    next_data_tag = soup.find("script", id="__NEXT_DATA__")

    if next_data_tag:

        raw_text = next_data_tag.string or next_data_tag.get_text()

        if raw_text and raw_text.strip():
            try:
                data = json.loads(raw_text)
            except (ValueError, TypeError):
                data = None

            if data is not None:
                candidates.append(("Next.js (__NEXT_DATA__)", data))

    for marker, framework_label in EMBEDDED_JSON_ASSIGNMENT_MARKERS:

        raw_object_text = _extract_json_after_assignment(html, marker)

        if not raw_object_text:
            continue

        try:
            data = json.loads(raw_object_text)
        except (ValueError, TypeError):
            # geen strikt geldige JSON (bv. "undefined" als waarde) --
            # deze kandidaat overslaan, niet crashen
            continue

        candidates.append((framework_label, data))
        break  # eerste geldige match is genoeg

    return candidates


def _detect_embedded_json(html, base_url):
    """
    Zoekt naar JSON-hydration-payloads in de initiële HTML-bron (zie
    de sectie-uitleg hierboven). Voorzichtige heuristiek zoals de rest
    van dit bestand: het feit dát er JSON gevonden is, betekent nog
    niet dat het VACATUREDATA is -- dat beoordeelt
    `_find_job_array_in_json()` hieronder, met dezelfde soort
    sleutelnaam-heuristiek als browser_analysis._looks_like_job_list()
    gebruikt voor ontdekt netwerkverkeer (bewust dezelfde soort check,
    niet hetzelfde codepad -- deze zoekt dieper genest, zie
    EMBEDDED_JSON_MAX_DEPTH).

    Geeft None terug als er niets gevonden is, anders een dict:
    {
        "framework": str,          -- bv. "Next.js (__NEXT_DATA__)"
        "path": [str, ...],        -- sleutelpad naar de vacature-array
        "count": int,
        "preview": [...],          -- eerste PREVIEW_SIZE titels
        "looks_like_job_list": bool,
    }
    """

    candidates = extract_embedded_json_candidates(html)

    for framework_label, data in candidates:

        path, job_array = _find_job_array_in_json(data)

        if not job_array:
            continue

        preview = []

        for item in job_array[:PREVIEW_SIZE]:

            if not isinstance(item, dict):
                continue

            title = None

            for key, value in item.items():
                if isinstance(value, str) and any(hint in key.lower() for hint in EMBEDDED_JSON_KEY_HINTS):
                    title = value
                    break

            if title:
                preview.append(title)

        return {
            "framework": framework_label,
            "path": path,
            "count": len(job_array),
            "preview": preview,
            "looks_like_job_list": True,
        }

    return None


def _extract_json_after_assignment(text, marker):
    """
    Zoekt `marker` (bv. "window.__NUXT__=") in `text`, en extraheert
    het daaropvolgende JS-object-literal door de accolades in balans
    te houden -- met inachtneming van string-literals, zodat een `{`
    of `}` BINNEN een string niet meetelt. Geeft de ruwe tekst van het
    object terug (nog niet geparsed als JSON), of None als de marker
    niet gevonden is, er geen openende accolade op volgt, of de
    accolades nooit in balans komen (afgekapte/kapotte HTML).
    """

    index = text.find(marker)

    if index == -1:
        return None

    start = text.find("{", index)

    if start == -1:
        return None

    depth = 0
    in_string = None
    escape = False

    for i in range(start, len(text)):

        char = text[i]

        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == in_string:
                in_string = None
            continue

        if char in ("'", '"'):
            in_string = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]

    return None


def _find_job_array_in_json(data, max_depth=EMBEDDED_JSON_MAX_DEPTH):
    """
    Zoekt, tot `max_depth` niveaus diep, naar de meest waarschijnlijke
    vacature-array in `data`: een lijst van dicts waarvan de sleutels
    herkenbare namen bevatten (zie EMBEDDED_JSON_KEY_HINTS). Zoekt
    breedte-eerst per niveau (alle directe lijst-waarden op het
    huidige niveau vóór er dieper gerecursereerd wordt), zodat een
    ondiepe match altijd voorrang krijgt op een toevallige diepere.

    Geeft (pad_als_lijst_van_sleutels, lijst) terug, of (None, None)
    als niets gevonden is.
    """

    def _looks_job_like(candidate_list):

        if not candidate_list or not isinstance(candidate_list[0], dict):
            return False

        keys_lower = " ".join(str(key).lower() for key in candidate_list[0].keys())

        return any(hint in keys_lower for hint in EMBEDDED_JSON_KEY_HINTS)

    def _search(node, path, depth):

        if depth > max_depth:
            return None, None

        if isinstance(node, list) and _looks_job_like(node):
            return path, node

        if isinstance(node, dict):

            for key, value in node.items():
                if isinstance(value, list) and _looks_job_like(value):
                    return path + [key], value

            for key, value in node.items():
                if isinstance(value, (dict, list)):
                    found_path, found_list = _search(value, path + [key], depth + 1)
                    if found_list:
                        return found_path, found_list

        return None, None

    return _search(data, [], 0)
