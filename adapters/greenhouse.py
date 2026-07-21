"""
Adapter: greenhouse

Haalt vacatures op via de publieke Greenhouse Job Board API in plaats
van door HTML te scrapen. Greenhouse (boards.greenhouse.io) is een van
de meestgebruikte ATS-platformen; deze API is officieel, kent geen
authenticatie, en is stabieler dan CSS-selectors omdat de HTML van het
board een frontend-implementatiedetail is dat los van de API-vorm kan
veranderen.

API-documentatie: https://developers.greenhouse.io/job-board.html
Endpoint: GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true

board_token is het bedrijfsdeel van de board-URL, bv. voor
https://boards.greenhouse.io/acme is board_token "acme". Datzelfde
board_token wordt ook gebruikt door bedrijven die hun Greenhouse-
vacatures via een embed-widget op hun EIGEN "werken bij"-domein tonen
(een <script src="https://boards.greenhouse.io/embed/job_board/js?for=acme">)
-- ook dan werkt deze adapter, mits board_token is opgegeven of
afleidbaar is.

CONFIGURATIE (Source.settings, als JSON) -- alle velden optioneel:
{
    "board_token": "acme"
}

Wordt niet opgegeven? Dan wordt het afgeleid uit Source.url via
derive_board_token() -- werkt alleen als Source.url zelf op
boards.greenhouse.io draait. Bij een embed op een eigen domein moet
board_token dus altijd expliciet in settings staan.

Wordt automatisch aanbevolen door de Adapter Helper (adapter_helper._classify)
zodra een pagina een script van greenhouse.io laadt of de bron-URL
zelf op boards.greenhouse.io staat, zie matches_fingerprint()
hieronder -- dit is een harde fingerprint-match, geen heuristische
gok, vandaar de hoge confidence (site_fingerprint.CONFIDENCE_GREENHOUSE).

Geen paginering nodig: de API geeft in één call alle openstaande
vacatures van een board terug.
"""

from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from adapters.base import load_settings, AdapterError


API_BASE = "https://boards-api.greenhouse.io/v1/boards"
TIMEOUT = 30

GREENHOUSE_DOMAIN_HINT = "greenhouse.io"


CAPABILITIES = {
    "label": "Greenhouse Job Board API",
    "supports_pagination": False,
    "supports_categories": False,
    "supports_detail_pages": False,
    "supports_dates": True,
    "supports_location": True,
    "requires_credentials": False,
}


def fetch(source):

    settings = load_settings(source)

    board_token = settings.get("board_token") or derive_board_token(source.url)

    if not board_token:
        raise AdapterError(
            f"Kon geen Greenhouse board_token bepalen voor '{source.name}'. "
            "Zet settings.board_token expliciet (het bedrijfsdeel van de "
            "board-URL, bv. 'acme' voor https://boards.greenhouse.io/acme) "
            "-- vooral nodig als dit een embed op een eigen domein is."
        )

    url = f"{API_BASE}/{board_token}/jobs"

    response = requests.get(
        url,
        params={"content": "true"},
        timeout=TIMEOUT,
    )

    _raise_for_greenhouse_error(response, source.name, board_token)

    return response.json().get("jobs", [])


def parse(raw_jobs, source):

    vacancies = []

    for job in raw_jobs:

        title = job.get("title")

        if not title:
            continue

        url = job.get("absolute_url")

        if not url:
            continue

        description = _strip_html(job.get("content", ""))
        location = (job.get("location") or {}).get("name")
        updated_at = job.get("updated_at")

        content_parts = [description or title]

        if location:
            content_parts.append(location)

        if updated_at:
            content_parts.append(str(updated_at))

        vacancy = {
            "title": title,
            "url": url,
            "content": " | ".join(content_parts),
        }

        if location:
            vacancy["location"] = location

        if updated_at:
            vacancy["date"] = updated_at

        vacancies.append(vacancy)

    return vacancies


def derive_board_token(url):
    """
    Leidt het board_token af uit een boards.greenhouse.io-URL, bv.
    "https://boards.greenhouse.io/acme/jobs/12345" -> "acme". Geeft
    None terug als de URL niet op greenhouse.io draait (dan is er geen
    betrouwbare aanname mogelijk -- de aanroeper moet board_token dan
    expliciet opgeven, zie fetch() hierboven).
    """

    parsed = urlparse(url)

    if GREENHOUSE_DOMAIN_HINT not in parsed.netloc.lower():
        return None

    parts = [part for part in parsed.path.split("/") if part]

    return parts[0] if parts else None


def matches_fingerprint(url, script_domains):
    """
    True als deze pagina een harde Greenhouse-fingerprint vertoont:
    de bron-URL zelf draait op een greenhouse.io-domein, OF één van de
    externe scripts wordt geladen vanaf greenhouse.io (het
    embed-widget-scenario: een werkgever toont Greenhouse-vacatures op
    zijn EIGEN "werken bij"-domein via een <script>-embed).

    Gebruikt door adapter_helper._classify() als eerste, harde check
    vóór de bestaande jsonld/microdata/html_listing/generic_links-
    precedentie -- een fingerprint-match is geen gok en hoeft dus niet
    te wachten tot de zwakkere heuristieken hun beurt krijgen.
    """

    own_domain = urlparse(url or "").netloc.lower()

    if GREENHOUSE_DOMAIN_HINT in own_domain:
        return True

    return any(
        GREENHOUSE_DOMAIN_HINT in domain.lower()
        for domain in (script_domains or [])
    )


def _strip_html(text):

    if not text:
        return ""

    return BeautifulSoup(text, "lxml").get_text(" ", strip=True)


def _raise_for_greenhouse_error(response, source_name, board_token):

    if response.status_code == 200:
        return

    if response.status_code == 404:
        raise AdapterError(
            f"'{source_name}': Greenhouse board '{board_token}' niet "
            "gevonden (404) -- klopt de board_token/URL nog?"
        )

    raise AdapterError(
        f"'{source_name}': Greenhouse API-fout ({response.status_code}): "
        f"{response.text[:200]}"
    )
