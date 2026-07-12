"""
Adapter: cso_api

Gebruikt de officiële CSO Vacature-API (Carrièresites Overheid) om
vacatures op te halen bij WerkenvoorNederland.nl. Documentatie:
https://docs.api.cso20.net/

BELANGRIJK -- dit vereist een eigen API-account (username/password):
neem contact op met de CSO-helpdesk (helpdesk@werkenvoornederland.nl,
zie de documentatie) om toegang aan te vragen. Dit is dus geen
scraping: het is een officiële, geautoriseerde JSON-API.

Werking volgens de documentatie:
    1. getApiKey.json  (username + password)      -> apiKey (20 min geldig)
    2. getJobs.json    (apiKey + filter + fieldSelection) -> lijst vacatures

We vragen telkens een verse apiKey op -- eenvoudiger dan zelf
bijhouden of de vorige key nog geldig is, en dit endpoint kost
weinig.

CONFIGURATIE (Source.settings, als JSON):
{
    "keywords": "cultuur, erfgoed, museum",     // optioneel: RemoteJobContentFilter.keywords
    "job_branches": ["CVG.04"],                  // optioneel: codes uit getJobEnumerations (jobBranches)
    "max_rows": 100,                             // optioneel
    "job_url_template": "https://www.werkenvoornederland.nl/vacatures/vacature/{code}"
}

LET OP -- job_url_template is een aanname en moet je zelf verifiëren:
de API geeft in de RemoteJob geen kant-en-klare vacature-URL terug,
alleen een "code". Open een vacature op werkenvoornederland.nl en
vergelijk de URL-structuur met de "code" die de API voor diezelfde
vacature teruggeeft (via getJobs of getJob), en pas het template
hierboven aan zodat {code} op de juiste plek in de URL komt.
"""

import json

import requests

from adapters.base import load_settings, AdapterError
from config import Config


API_BASE = "https://api.cso20.net/v1/JobAPI"
TIMEOUT = 30


def fetch(source):

    settings = load_settings(source)

    api_key = _get_api_key()

    job_filter = _build_filter(settings)

    field_selection = {
        "__type__": "RemoteJobFieldSelection",
        "jobContent": {
            "__type__": "RemoteJobContentFieldSelection",
            "employer": True,
            "department": True,
        },
        "jobFeatures": {
            "__type__": "RemoteJobFeaturesFieldSelection",
            "location": True,
            "employmentConditions": True,
            "detail": True,
            "applicationContact": True,
        },
        "organisation": True,
    }

    payload = {
        "apiKey": api_key,
        "filter": job_filter,
        "fieldSelection": field_selection,
    }

    response = requests.post(
        f"{API_BASE}/getJobs.json",
        data=json.dumps(payload),
        headers={"Content-Type": "application/json"},
        timeout=TIMEOUT,
    )

    _raise_for_cso_error(response)

    return response.json().get("result", [])


def parse(raw_jobs, source):

    settings = load_settings(source)

    url_template = settings.get(
        "job_url_template",
        "https://www.werkenvoornederland.nl/vacatures/vacature/{code}",
    )

    vacancies = []

    for job in raw_jobs:

        content = job.get("content") or {}

        title = content.get("name")

        if not title:
            continue

        description = content.get("description", "")
        code = job.get("code", "")

        vacancies.append({
            "title": title,
            "url": url_template.format(code=code),
            "content": description or title,
        })

    return vacancies


def _get_api_key():

    if not Config.CSO_USERNAME or not Config.CSO_PASSWORD:
        raise AdapterError(
            "CSO_USERNAME/CSO_PASSWORD zijn niet ingesteld. Vraag een "
            "API-account aan bij de CSO-helpdesk en zet de gegevens in .env"
        )

    payload = {
        "username": Config.CSO_USERNAME,
        "password": Config.CSO_PASSWORD,
    }

    response = requests.post(
        f"{API_BASE}/getApiKey.json",
        data=json.dumps(payload),
        headers={"Content-Type": "application/json"},
        timeout=TIMEOUT,
    )

    _raise_for_cso_error(response)

    return response.json()["result"]


def _build_filter(settings):

    job_filter = {"__type__": "RemoteJobFilter"}

    keywords = settings.get("keywords")
    if keywords:
        job_filter["contentFilter"] = {
            "__type__": "RemoteJobContentFilter",
            "keywords": keywords,
        }

    job_branches = settings.get("job_branches")
    if job_branches:
        job_filter["featuresFilter"] = {
            "__type__": "RemoteJobFeaturesFilter",
            "detailFilter": {
                "__type__": "RemoteJobDetailFilter",
                "jobBranches": [
                    {"__type__": "JobBranch", "code": code}
                    for code in job_branches
                ],
            },
        }

    max_rows = settings.get("max_rows")
    if max_rows:
        job_filter["filterMetadata"] = {
            "__type__": "RemoteFilterMetadata",
            "maxRows": max_rows,
        }

    return job_filter


def _raise_for_cso_error(response):

    if response.status_code == 200:
        return

    try:
        message = response.json().get("message", response.text)
    except ValueError:
        message = response.text

    raise AdapterError(f"CSO API-fout ({response.status_code}): {message}")
