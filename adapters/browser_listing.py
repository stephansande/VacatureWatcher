"""
Adapter: browser_listing

LET OP -- de onderliggende Playwright-aansturing (browser_analysis.py)
is inmiddels wel met mocks getest (zie tests/test_browser_analysis.py
en de manier waarop adapter_helper.analyze() 'm nu ook gebruikt), maar
een ECHTE headless-browserrun tegen een live JavaScript-site is in
mijn sandbox nog steeds niet mogelijk (geen browser-binary te
installeren zonder netwerktoegang tot npm/playwright's CDN). Test dit
dus altijd zelf grondig (bv. via "Bron testen") voordat je 'm op een
bron inschakelt die je vertrouwt.

Voor sites die vacaturedata pas via JavaScript inladen (zoals we bij
Werken bij Wassenaar tegenkwamen: geen enkele <a href> in de statische
HTML, alleen een <div onclick="..."> binnen een widget die pas na een
async aanroep gevuld wordt) is er geen andere structurele oplossing
dan de pagina daadwerkelijk laten renderen zoals een browser dat doet.
Deze adapter doet dat met Playwright (headless Chromium) via de
GEDEELDE infrastructuur in browser_analysis.py (dezelfde module die
ook adapter_helper.analyze() gebruikt voor "Analyseren" -- zo geeft
analyse altijd hetzelfde resultaat als de daadwerkelijke controle), en
hergebruikt vervolgens de BESTAANDE, al geteste parse-logica
(html_listing/jsonld_listing/microdata_listing) op de gerenderde HTML.

Playwright + Chromium zijn standaard onderdeel van de Docker-image
(zie requirements.txt en Dockerfile) -- geen aparte
requirements-browser.txt meer nodig sinds "Analyseren" zelf ook een
browser gebruikt.

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

import browser_analysis

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


def fetch(source):

    try:
        sync_playwright = browser_analysis.get_sync_playwright()
    except browser_analysis.BrowserUnavailableError as error:
        raise AdapterError(str(error)) from error

    settings = load_settings(source)

    start_url = settings.get("start_url") or source.url
    wait_selector = settings.get("wait_selector")
    wait_ms = settings.get("wait_ms", browser_analysis.DEFAULT_WAIT_MS)
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
            browser_page = browser.new_page(user_agent=browser_analysis.USER_AGENT)

            for index, url in enumerate(urls):

                html = browser_analysis.render_page(
                    browser_page,
                    url,
                    consent_selector=consent_selector,
                    wait_selector=wait_selector,
                    wait_ms=wait_ms,
                )

                pages.append({
                    "url": url,
                    "html": html,
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
