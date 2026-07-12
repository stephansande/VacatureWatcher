"""
Basisinterface voor alle vacature-adapters.

Elke adapter (generic_links, html_listing, jsonld_listing, cso_api, ...)
implementeert dezelfde functie-signatuur, zodat vacancy_checker.py niet
hoeft te weten met wat voor soort bron hij te maken heeft.

Een adapter levert altijd een lijst van dicts met dezelfde drie velden:
    {
        "title":   str,
        "url":     str,
        "content": str,   # korte omschrijving/samenvatting, mag gelijk zijn aan title
    }
"""

import json
import time


class AdapterError(Exception):
    """Generieke fout die een adapter mag opgooien bij een mislukte check."""


def load_settings(source):
    """
    Parseert Source.settings (JSON-tekst) naar een dict.

    Dit is de ENE plek waar adapter-specifieke configuratie vandaan
    komt -- selectors, categorieën, paginering, keywords, filters,
    url-templates, etc. Ontbreekt settings, dan is de uitkomst een
    lege dict (adapter mag daarna zelf een AdapterError opgooien als
    een verplicht veld ontbreekt).
    """

    if not source.settings:
        return {}

    try:
        parsed = json.loads(source.settings)
    except (ValueError, TypeError) as error:
        raise AdapterError(
            f"settings van '{source.name}' is geen geldige JSON: {error}"
        )

    if not isinstance(parsed, dict):
        raise AdapterError(
            f"settings van '{source.name}' moet een JSON-object zijn, "
            f"geen {type(parsed).__name__}"
        )

    return parsed


def require(settings, key, source_name):
    """Haalt een verplicht settings-veld op, met een duidelijke foutmelding."""

    value = settings.get(key)

    if not value:
        raise AdapterError(
            f"settings.{key} ontbreekt of is leeg (bron: '{source_name}')"
        )

    return value


def get_keyword_filters(source, settings):
    """
    Bepaalt de effectieve include/exclude-keywords voor een source.

    Voorrang: settings.include_keywords / settings.exclude_keywords
    (nieuwe, adapter-agnostische route). Voor "include" valt dit terug
    op het legacy Source.keywords-veld als settings niets opgeeft, zodat
    bestaande v1-werkgevers met een ingevuld keywords-veld gewoon
    blijven werken.
    """

    include_keywords = settings.get("include_keywords") or source.keywords
    exclude_keywords = settings.get("exclude_keywords")

    return include_keywords, exclude_keywords


def apply_keyword_filter(vacancies, include_keywords=None, exclude_keywords=None):
    """
    Filtert een lijst vacatures op basis van include/exclude keywords.

    include_keywords / exclude_keywords mogen een komma-gescheiden
    string zijn (legacy, uit het Source.keywords-veld) of een lijst
    (uit settings.include_keywords / settings.exclude_keywords) --
    beide vormen worden hier genormaliseerd.

    include_keywords: als gezet, moet minstens één keyword voorkomen
                       in titel of content.
    exclude_keywords: als een keyword hierin voorkomt in titel of
                       content, wordt de vacature uitgesloten --
                       ongeacht de include-lijst.
    """

    include_list = _normalize_keywords(include_keywords)
    exclude_list = _normalize_keywords(exclude_keywords)

    if not include_list and not exclude_list:
        return vacancies

    result = []

    for vacancy in vacancies:
        haystack = (vacancy.get("title", "") + " " + vacancy.get("content", "")).lower()

        if exclude_list and any(word in haystack for word in exclude_list):
            continue

        if include_list and not any(word in haystack for word in include_list):
            continue

        result.append(vacancy)

    return result


def _normalize_keywords(raw):

    if not raw:
        return []

    if isinstance(raw, (list, tuple)):
        return [str(word).strip().lower() for word in raw if str(word).strip()]

    return [word.strip().lower() for word in str(raw).split(",") if word.strip()]


def polite_sleep(seconds):
    """Kleine helper zodat crawl-delay expliciet zichtbaar is in adapter-code."""

    if seconds and seconds > 0:
        time.sleep(seconds)
