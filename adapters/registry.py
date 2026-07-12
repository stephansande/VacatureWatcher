"""
Centrale plek waar bekend is welke adapters er zijn.

Nieuwe adapter toevoegen? Schrijf een module met een fetch(source) en
parse(raw, source) functie, en voeg 'm hieronder toe aan ADAPTERS.
"""

from adapters import generic_links
from adapters import html_listing
from adapters import jsonld_listing
from adapters import cso_api
from adapters.base import AdapterError


ADAPTERS = {
    "generic_links": generic_links,
    "html_listing": html_listing,
    "jsonld_listing": jsonld_listing,
    "cso_api": cso_api,
}


def get(adapter_name):

    adapter = ADAPTERS.get(adapter_name)

    if adapter is None:
        raise AdapterError(
            f"Onbekende adapter '{adapter_name}'. "
            f"Beschikbaar: {', '.join(ADAPTERS.keys())}"
        )

    return adapter
