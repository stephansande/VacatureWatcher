"""
browser_analysis.py

Gedeelde Playwright-infrastructuur voor alles wat een pagina met een
ECHTE (headless) browser moet laten renderen -- gebruikt door zowel
adapter_helper.analyze() (het "Analyseren"-knopje bij een bron) als
adapters/browser_listing.py (de geplande controles voor bronnen die
JavaScript-rendering nodig hebben, zoals Werken bij Wassenaar).

Waarom dit een los, gedeeld bestand is in plaats van dat elke
aanroeper zijn eigen Playwright-code schrijft: User-Agent, timeouts,
en cookiebanner-afhandeling moeten voor "Analyseren" en de
daadwerkelijke controle exact hetzelfde gedrag vertonen. Zou dat niet
zo zijn, dan zou een bron bij "Analyseren" iets anders te zien kunnen
krijgen dan bij de geplande controle -- precies het soort
inconsistentie die tot verwarrende, moeilijk te reproduceren
problemen leidt (zie: het Werk bij Dunea-scenario, waar een verschil
tussen "wat de analyse zag" en "wat de geplande controle ophaalde" tot
veel heen-en-weer leidde).

Dit bestand doet zelf GEEN detectie/parsing van vacature-HTML -- dat
blijft bij adapter_helper.py (analyse) en de losse adapters
(parse-logica). Wel bevat dit bestand een voorzichtige HINT-heuristiek
voor ONTDEKT NETWERKVERKEER (_looks_like_job_list) -- zie de sectie
verderop.
"""

import json
from urllib.parse import urlparse


DEFAULT_WAIT_MS = 3000
NAVIGATION_TIMEOUT_MS = 30000
WAIT_SELECTOR_TIMEOUT_MS = 10000
CONSENT_CLICK_TIMEOUT_MS = 5000
CONSENT_SETTLE_MS = 1000

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
# Zelfde reden als in scraper.py: een UA die zichzelf verraadt als
# script/tool laat sommige sites de aanvraag blokkeren of een
# afwijkende pagina teruggeven, zonder dat er een foutmelding ontstaat.


class BrowserUnavailableError(Exception):
    """Playwright/Chromium is niet geïnstalleerd of kon niet starten."""


def _import_playwright():
    """
    Centrale plek voor de playwright-import, zodat de foutmelding bij
    een ontbrekende installatie overal hetzelfde is. Los geïmporteerd
    (niet bovenaan dit bestand) zodat dit bestand ook inleesbaar/
    testbaar blijft in een omgeving zonder playwright geïnstalleerd --
    de import-fout treedt pas op zodra er ECHT een browser nodig is.
    """

    try:
        from playwright.sync_api import (
            sync_playwright,
            TimeoutError as PlaywrightTimeoutError,
        )
    except ImportError as error:
        raise BrowserUnavailableError(
            "De 'playwright'-package of Chromium-browser is niet "
            "beschikbaar. Dit hoort standaard aanwezig te zijn in de "
            "Docker-image (zie Dockerfile/requirements.txt) -- lokaal "
            "buiten Docker: 'pip install playwright && playwright "
            "install --with-deps chromium'."
        ) from error

    return sync_playwright, PlaywrightTimeoutError


def get_sync_playwright():
    """
    Geeft de sync_playwright-contextmanager-factory terug (of gooit
    BrowserUnavailableError). Voor aanroepers die zelf de
    browser-levenscyclus beheren over MEERDERE pagina's binnen één
    sessie (zie adapters/browser_listing.py, met paginering) -- voor
    eenmalig gebruik van één pagina, gebruik fetch_rendered_html()
    hieronder in plaats van dit rechtstreeks aan te roepen.
    """

    sync_playwright, _ = _import_playwright()
    return sync_playwright


def render_page(
    browser_page,
    url,
    *,
    consent_selector=None,
    wait_selector=None,
    wait_ms=DEFAULT_WAIT_MS,
):
    """
    Navigeert een AL GEOPENDE Playwright-paginaobject naar `url`,
    wacht eventueel een cookiebanner weg te klikken, wacht op
    `wait_selector` (of anders gewoon `wait_ms`), en geeft de
    gerenderde HTML terug (`browser_page.content()`).

    Gooit GEEN fout als de cookiebanner of wait_selector niet
    gevonden wordt binnen de timeout -- gaat dan door met wat er op
    dat moment geladen is. Dat wordt zichtbaar als "0 resultaten" bij
    de aanroepende functie (analyze()/test_source()/parse()), niet als
    een harde crash die de hele controle laat mislukken.
    """

    _navigate_and_wait(
        browser_page,
        url,
        consent_selector=consent_selector,
        wait_selector=wait_selector,
        wait_ms=wait_ms,
    )

    return browser_page.content()


def _navigate_and_wait(browser_page, url, *, consent_selector, wait_selector, wait_ms):
    """
    De kern van render_page(), zonder de content op te halen -- apart
    getrokken zodat render_page_capturing_requests() hieronder dezelfde
    navigatie-/wachtlogica kan hergebruiken terwijl er ondertussen een
    response-listener actief is.
    """

    _, PlaywrightTimeoutError = _import_playwright()

    browser_page.goto(url, wait_until="networkidle", timeout=NAVIGATION_TIMEOUT_MS)

    if consent_selector:
        try:
            browser_page.click(consent_selector, timeout=CONSENT_CLICK_TIMEOUT_MS)
            # na het klikken kan de site opnieuw content laden (bv. de
            # vacature-widget die pas ná toestemming start) -- geef
            # dat een moment de tijd
            browser_page.wait_for_timeout(CONSENT_SETTLE_MS)
        except PlaywrightTimeoutError:
            # banner niet gevonden (staat er soms al niet, of een
            # andere structuur) -- gewoon doorgaan
            pass

    if wait_selector:
        try:
            browser_page.wait_for_selector(wait_selector, timeout=WAIT_SELECTOR_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            pass
    else:
        browser_page.wait_for_timeout(wait_ms)


def fetch_rendered_html(url, **render_kwargs):
    """
    Opent een headless browser, rendert ÉÉN pagina via render_page(),
    en sluit de browser weer -- voor eenmalig gebruik, zoals de
    Adapter Helper (adapter_helper.analyze()).

    Voor meerdere pagina's/paginering binnen dezelfde browsersessie
    (adapters/browser_listing.py): gebruik render_page() rechtstreeks
    met een zelf beheerde browser/pagina -- elke nieuwe browser-launch
    kost tijd, dat wil je niet per paginanummer herhalen.

    Accepteert dezelfde keyword-argumenten als render_page()
    (consent_selector, wait_selector, wait_ms).
    """

    sync_playwright, _ = _import_playwright()

    with sync_playwright() as playwright:

        browser = playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox"],
        )

        try:
            browser_page = browser.new_page(user_agent=USER_AGENT)
            return render_page(browser_page, url, **render_kwargs)
        finally:
            browser.close()


# ---------------------------------------------------------------------------
# Netwerkverkeer vastleggen tijdens analyse
#
# Doel: een site kan een eigen JSON-API hebben die de vacaturedata
# levert (bv. een interne "/api/vacatures"-aanroep), ook als daar
# nergens publiek over gedocumenteerd is. Als de analysestap dat
# verkeer meekijkt, kan een latere stap zo'n endpoint herkennen als
# snellere/robuustere methode dan HTML-scraping (een JSON-API breekt
# minder snel bij een visuele redesign dan een CSS-selector).
#
# Bewuste keuzes:
# - Alleen resource_type "xhr"/"fetch" -- sluit afbeeldingen, fonts,
#   CSS, scripts, en de hoofd-pagina zelf structureel uit, nog vóór er
#   naar de URL gekeken wordt.
# - Bekende analytics/advertentiedomeinen worden ook binnen xhr/fetch
#   weggefilterd (Google Analytics/Tag Manager e.d. versturen hun
#   "beacons" vaak ALS fetch/xhr, dus resource_type alleen is niet
#   genoeg).
# - GEEN cookies, GEEN request-/response-headers (buiten content-type)
#   worden opgeslagen -- dit resultaat kan uiteindelijk in een
#   database en op een webpagina belanden, en auth-tokens/sessie-
#   cookies horen daar onder geen beding in terecht te komen.
# - Een harde limiet op het aantal opgevangen responses én op de
#   grootte van een individuele JSON-body, zodat één pagina met
#   honderden API-aanroepen (of één enorme respons) de analyse niet
#   onnodig vertraagt of laat vastlopen.
# ---------------------------------------------------------------------------

MAX_CAPTURED_REQUESTS = 20
MAX_BODY_CHARS = 200_000
# Responses groter dan dit worden nog wel GETELD/getoond (url, status,
# content-type), maar de body wordt niet geparsed/bewaard -- puur een
# snelheids-/geheugenvangnet, geen inhoudelijke beoordeling.

NOISE_RESOURCE_TYPES_ALLOWED = ("xhr", "fetch")

NOISE_DOMAIN_HINTS = (
    "google-analytics.com",
    "googletagmanager.com",
    "doubleclick.net",
    "facebook.com",
    "facebook.net",
    "hotjar.com",
    "clarity.ms",
    "cloudflareinsights.com",
    "sentry.io",
    "segment.io",
    "segment.com",
    "amplitude.com",
    "mixpanel.com",
    "newrelic.com",
    "nr-data.net",
    "googlesyndication.com",
    "adsystem.com",
    "criteo.com",
    "cookiebot.com",
    "usercentrics.eu",
)

JOB_LIST_KEY_HINTS = (
    "title", "vacature", "vacancy", "job", "functie",
    "position", "titel", "naam",
)


def render_page_capturing_requests(
    browser_page,
    url,
    *,
    consent_selector=None,
    wait_selector=None,
    wait_ms=DEFAULT_WAIT_MS,
    max_requests=MAX_CAPTURED_REQUESTS,
):
    """
    Zoals render_page(), maar vangt ONDERTUSSEN ook XHR/fetch-
    netwerkverkeer op (zie de module-docstring hierboven voor de
    filterkeuzes). Geeft (html, discovered_requests) terug in plaats
    van alleen html.

    discovered_requests is een lijst met dicts:
    {
        "url": str, "method": str, "status": int,
        "content_type": str, "is_json": bool,
        "looks_like_job_list": bool, "summary": str,
        "body_preview": str | None,
    }
    Gesorteerd met de kandidaten die op een vacaturelijst LIJKEN
    eerst -- puur om de meest kansrijke kandidaat als eerste te tonen,
    geen garantie.
    """

    captured = []

    def _on_response(response):
        if len(captured) >= max_requests:
            return
        entry = _maybe_capture_response(response)
        if entry:
            captured.append(entry)

    browser_page.on("response", _on_response)

    try:
        _navigate_and_wait(
            browser_page,
            url,
            consent_selector=consent_selector,
            wait_selector=wait_selector,
            wait_ms=wait_ms,
        )
        html = browser_page.content()
    finally:
        browser_page.remove_listener("response", _on_response)

    captured.sort(key=lambda entry: not entry["looks_like_job_list"])

    return html, captured


def fetch_rendered_html_with_requests(url, max_requests=MAX_CAPTURED_REQUESTS, **render_kwargs):
    """
    Zoals fetch_rendered_html(), maar met netwerkverkeer erbij (zie
    render_page_capturing_requests()). Gebruikt door
    adapter_helper.analyze() -- adapters/browser_listing.py heeft dit
    niet nodig voor de geplande controles, dat blijft bij de
    goedkopere render_page().
    """

    sync_playwright, _ = _import_playwright()

    with sync_playwright() as playwright:

        browser = playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox"],
        )

        try:
            browser_page = browser.new_page(user_agent=USER_AGENT)
            return render_page_capturing_requests(
                browser_page, url, max_requests=max_requests, **render_kwargs
            )
        finally:
            browser.close()


def _maybe_capture_response(response):
    """
    Beoordeelt één Playwright-response-object. Geeft None terug als
    'ie geen kandidaat is (verkeerd resource_type, ruis-domein), anders
    een dict zoals hierboven beschreven bij
    render_page_capturing_requests().
    """

    try:
        request = response.request
        resource_type = request.resource_type
    except Exception:
        return None

    if resource_type not in NOISE_RESOURCE_TYPES_ALLOWED:
        return None

    url = response.url
    hostname = urlparse(url).netloc.lower()

    if any(hint in hostname for hint in NOISE_DOMAIN_HINTS):
        return None

    try:
        content_type = response.headers.get("content-type", "") or ""
    except Exception:
        content_type = ""

    is_json = "json" in content_type.lower()

    try:
        status = response.status
    except Exception:
        status = None

    try:
        method = request.method
    except Exception:
        method = None

    body = None
    looks_like_job_list = False
    summary = None
    body_preview = None
    items_path_guess = ""

    if is_json:
        try:
            text = response.text()
        except Exception:
            text = None

        if text and len(text) <= MAX_BODY_CHARS:
            try:
                body = json.loads(text)
            except (ValueError, TypeError):
                body = None

        if body is not None:
            found_path, _ = _find_job_array(body)
            items_path_guess = found_path or ""
            looks_like_job_list = _looks_like_job_list(body)
            summary = _summarize_json_body(body)
            body_preview = json.dumps(body, indent=2, ensure_ascii=False)[:1500]
        elif text is not None and len(text) > MAX_BODY_CHARS:
            summary = f"JSON-respons van {len(text)} tekens -- te groot om te analyseren, alleen metadata getoond"

    return {
        "url": url,
        "method": method,
        "status": status,
        "content_type": content_type,
        "is_json": is_json,
        "looks_like_job_list": looks_like_job_list,
        "summary": summary,
        "body_preview": body_preview,
        "items_path_guess": items_path_guess,
    }


def _find_job_array(body):
    """
    Zoekt de meest waarschijnlijke vacature-array in `body`: het
    top-niveau zelf als dat al een niet-lege lijst is, anders de
    eerste dict-waarde die een niet-lege lijst is (één niveau diep --
    bewust niet dieper, om geen willekeurige geneste array uit een
    complexe respons te grijpen).

    Geeft (items_path, lijst) terug. items_path is "" voor een
    top-level array, anders de sleutelnaam (bruikbaar als
    adapters.discovered_api's settings.items_path). (None, None) als
    er geen array-kandidaat gevonden is.
    """

    if isinstance(body, list) and body:
        return "", body

    if isinstance(body, dict):
        for key, value in body.items():
            if isinstance(value, list) and value:
                return key, value

    return None, None


def _looks_like_job_list(body):
    """
    Voorzichtige HINT (geen garantie) of een JSON-respons op een lijst
    vacatures lijkt: een array van objecten (rechtstreeks, of één
    niveau verstopt in een wrapper-object zoals {"results": [...]})
    waarvan de sleutels herkenbare namen bevatten. Puur signaal voor de
    mens die de analyse bekijkt -- net als "looks_blocked" in
    diagnostics.raw_fetch_debug(). Nog GEEN onderdeel van de
    automatische classificatie (_classify()) -- dat is voor een latere
    stap.
    """

    _, candidate_list = _find_job_array(body)

    if not candidate_list:
        return False

    first_item = candidate_list[0]

    if not isinstance(first_item, dict):
        return False

    keys_lower = " ".join(str(key).lower() for key in first_item.keys())

    return any(hint in keys_lower for hint in JOB_LIST_KEY_HINTS)


def _summarize_json_body(body):
    """Korte, mens-leesbare samenvatting van een JSON-respons voor de UI."""

    if isinstance(body, list):
        count = len(body)
        if count and isinstance(body[0], dict):
            fields = ", ".join(list(body[0].keys())[:8])
            return f"Array van {count} object(en), velden: {fields}"
        return f"Array van {count} element(en)"

    if isinstance(body, dict):
        keys = ", ".join(list(body.keys())[:8])
        return f"Object met velden: {keys}"

    return "JSON-waarde"
