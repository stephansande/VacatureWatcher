"""
Adapter: browser_listing

LET OP -- deze adapter kon ik niet functioneel testen. Alle andere
adapters/heuristieken in dit project zijn met synthetische of echte
HTML getest; voor deze adapter ontbreekt in mijn sandbox netwerktoegang
om playwright + een browser-binary te installeren. De code is
zorgvuldig geschreven op basis van de Playwright sync-API, maar test
'm zelf grondig (bv. via "Bron testen") voordat je 'm op een bron
inschakelt die je vertrouwt.

Voor sites die vacaturedata pas via JavaScript inladen (zoals we bij
dierenbescherming.nl tegenkwamen: de statische HTML bevat alleen
filter-dropdowns en een "Geen resultaten gevonden"-placeholder) is er
geen andere structurele oplossing dan de pagina daadwerkelijk laten
renderen zoals een browser dat doet. Deze adapter doet dat met
Playwright (headless Chromium), en hergebruikt vervolgens de BESTAANDE,
al geteste parse-logica (html_listing/jsonld_listing/microdata_listing)
op de gerenderde HTML.

VEREISTEN (niet standaard geïnstalleerd -- zie requirements.txt en
Dockerfile):
    pip install playwright
    playwright install --with-deps chromium

Dit is een aanzienlijk zwaardere dependency dan de andere adapters
(een volledige browser-binary, honderden MB's extra in de
Docker-image). Gebruik deze adapter dus alleen voor bronnen waarvoor
de andere adapters aantoonbaar niets vinden (zie Systeem ->
Diagnose -- "vermoedelijk JavaScript-rendering").

CONFIGURATIE (Source.settings, als JSON):
{
    "start_url": "https://voorbeeld.nl/vacatures/",
    "parse_as": "html_listing",   // "html_listing" | "jsonld_listing" | "microdata_listing"
    "selectors": {                 // alleen nodig als parse_as == "html_listing"
        "item": ".vacature-item",
        "title": "a.titel"
    },
    "consent_selector": "#cookie-accept",  // optioneel: klikt een cookiebanner weg
    "wait_selector": ".vacature-item",   // optioneel: wacht tot dit element verschijnt
    "wait_ms": 3000,                      // optioneel: vaste wachttijd als fallback/aanvulling
    "pagination": {"url_pattern": "...?page={page}", "max_pages": 3},
    "crawl_delay": 5
}

Als "wait_selector" niet gevonden wordt binnen de timeout, gaat de
adapter gewoon door met wat er op dat moment geladen is (dan vindt
parse() vermoedelijk niets -- zichtbaar via "Bron testen").

"consent_selector" is een CSS-selector voor de "Accepteren"-knop van
een cookiebanner (bv. "#cookie-accept" of ".cc-accept"). Wordt vóór
wait_selector/wait_ms geklikt, want sommige sites laden hun
vacature-widget pas ná het accepteren van cookies. Wordt de knop niet
binnen 5 seconden gevonden (bv. omdat er geen banner is), dan gaat de
adapter gewoon door -- geen harde fout.
"""

from adapters import html_listing
from adapters import jsonld_listing
from adapters import microdata_listing
from adapters.base import load_settings, polite_sleep, AdapterError


CAPABILITIES = {
    "label": "Headless browser (Playwright) -- voor JavaScript-sites",
    "supports_pagination": True,
    "supports_categories": False,
    "supports_detail_pages": False,
    "supports_dates": True,
    "supports_location": True,
    "requires_credentials": False,
}

DEFAULT_WAIT_MS = 3000
NAVIGATION_TIMEOUT_MS = 30000
WAIT_SELECTOR_TIMEOUT_MS = 10000
CONSENT_CLICK_TIMEOUT_MS = 5000
CONSENT_SETTLE_MS = 1000

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 "
    "VacatureWatcher/2.0"
)


def fetch(source):

    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
    except ImportError:
        raise AdapterError(
            "De 'playwright'-package is niet geïnstalleerd. Draai "
            "'pip install playwright && playwright install --with-deps "
            "chromium' (zie de docstring van adapters/browser_listing.py "
            "en README.md) om deze adapter te kunnen gebruiken."
        )

    settings = load_settings(source)

    start_url = settings.get("start_url") or source.url
    wait_selector = settings.get("wait_selector")
    wait_ms = settings.get("wait_ms", DEFAULT_WAIT_MS)
    pagination = settings.get("pagination")
    crawl_delay = settings.get("crawl_delay", 0)
    consent_selector = settings.get("consent_selector")

    if pagination:
        url_pattern = pagination["url_pattern"]
        max_pages = pagination.get("max_pages", 1)
        urls = [url_pattern.format(page=n) for n in range(1, max_pages + 1)]
    else:
        urls = [start_url]

    pages = []

    with sync_playwright() as playwright:

        browser = playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox"],
        )

        try:
            browser_page = browser.new_page(user_agent=USER_AGENT)

            for index, url in enumerate(urls):

                browser_page.goto(url, wait_until="networkidle", timeout=NAVIGATION_TIMEOUT_MS)

                if consent_selector:
                    try:
                        browser_page.click(consent_selector, timeout=CONSENT_CLICK_TIMEOUT_MS)
                        # na het klikken kan de site opnieuw content laden
                        # (bv. de vacature-widget die pas ná toestemming
                        # start) -- geef dat een moment de tijd
                        browser_page.wait_for_timeout(CONSENT_SETTLE_MS)
                    except PlaywrightTimeoutError:
                        # banner niet gevonden (staat er soms al niet, of
                        # een andere structuur) -- gewoon doorgaan
                        pass

                if wait_selector:
                    try:
                        browser_page.wait_for_selector(
                            wait_selector, timeout=WAIT_SELECTOR_TIMEOUT_MS
                        )
                    except PlaywrightTimeoutError:
                        # ga door met wat er nu staat -- parse() vindt dan
                        # vermoedelijk niets, wat zichtbaar wordt via
                        # "Bron testen" i.p.v. de hele check te laten falen
                        pass
                else:
                    browser_page.wait_for_timeout(wait_ms)

                pages.append({
                    "url": url,
                    "html": browser_page.content(),
                })

                if index < len(urls) - 1:
                    polite_sleep(crawl_delay)

        finally:
            browser.close()

    return pages


def parse(raw_pages, source):

    settings = load_settings(source)

    parse_as = settings.get("parse_as", "html_listing")

    if parse_as == "html_listing":
        html_only_pages = [page["html"] for page in raw_pages]
        return html_listing.parse(html_only_pages, source)

    if parse_as == "jsonld_listing":
        return jsonld_listing.parse(raw_pages, source)

    if parse_as == "microdata_listing":
        return microdata_listing.parse(raw_pages, source)

    raise AdapterError(
        f"'{source.name}': onbekende browser_listing parse_as '{parse_as}' "
        "(verwacht 'html_listing', 'jsonld_listing' of 'microdata_listing')"
    )
