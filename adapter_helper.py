"""
Adapter Helper.

Doel: iemand die een nieuwe vacaturesite wil toevoegen, hoeft niet
zelf CSS-selectors te gaan zoeken in devtools. Geef een URL op, en
deze module:

  1. haalt de pagina één keer op
  2. probeert, in volgorde van voorkeur, alle drie de adapters:
       a. jsonld_listing  (schema.org JobPosting -- stabielst)
       b. html_listing    (heuristiek: zoekt een herhalend blok
                            rond vacature-achtige links)
       c. generic_links   (de v1-aanpak, werkt altijd wel een beetje)
  3. voert voor elke gevonden kandidaat de ECHTE parse-functie van die
     adapter uit tegen de zojuist opgehaalde pagina, en levert een
     preview van de eerste paar gevonden titels op.

Dit is dus geen slimme AI-gok: het is "probeer de bekende patronen en
laat zien wat elk patroon daadwerkelijk oplevert", zodat de gebruiker
zelf op basis van de preview kan beoordelen welke adapter/instellingen
het beste passen voordat hij ze opslaat.

Beperkingen (bewust, om niets te verzinnen):
- De html_listing-heuristiek gokt op basis van herhaalde structuur
  rond "vacature-achtige" links. Bij ongebruikelijke paginastructuren
  kan dit mislukken of een te brede/smalle selector opleveren -- vandaar
  altijd de preview + total_matches tonen, nooit blind opslaan.
- cso_api wordt hier niet gedetecteerd: dat vereist een account en is
  al bekend (alleen relevant voor CSO-platformsites).
- Paginering wordt niet automatisch gedetecteerd; dat blijft
  handmatig instellen in settings.pagination.
"""

from types import SimpleNamespace
from urllib.parse import urljoin
from collections import Counter

from bs4 import BeautifulSoup

from scraper import fetch_html

from adapters import generic_links
from adapters.jsonld_listing import extract_job_postings


MIN_MATCHES = 3
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
        "html_listing": None,
        "generic_links": None,
        "recommendation": None,
    }

    try:
        html = fetch_html(url)
    except Exception as error:
        result["fetch_error"] = str(error)
        return result

    result["jsonld"] = _detect_jsonld(html, url)
    result["html_listing"] = _detect_html_listing(html, url)
    result["generic_links"] = _detect_generic_links(html, url)

    if result["jsonld"]:
        result["recommendation"] = "jsonld_listing"
    elif result["html_listing"]:
        result["recommendation"] = "html_listing"
    elif result["generic_links"]:
        result["recommendation"] = "generic_links"

    return result


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


def _detect_html_listing(html, base_url):

    soup = BeautifulSoup(html, "lxml")

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

    item_selector = _css_selector_for(best["item_element"])

    anchor_classes = best["anchor_element"].get("class") or []

    title_selector = (
        "a." + ".".join(anchor_classes) if anchor_classes else "a"
    )

    items = soup.select(item_selector)

    preview = []

    for item in items:

        title_el = item.select_one(title_selector)

        if not title_el:
            continue

        href = title_el.get("href")

        if not href:
            continue

        preview.append({
            "title": title_el.get_text(" ", strip=True),
            "url": urljoin(base_url, href),
        })

    if len(preview) < MIN_MATCHES:
        return None

    return {
        "item_selector": item_selector,
        "title_selector": title_selector,
        "total_matches": len(items),
        "preview": preview[:PREVIEW_SIZE],
        "suggested_settings": {
            "start_url": base_url,
            "selectors": {
                "item": item_selector,
                "title": title_selector,
                "link": title_selector,
            },
        },
    }


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
