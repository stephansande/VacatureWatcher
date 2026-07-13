"""
Centrale plek waar bekend is welke adapters er zijn.

Nieuwe adapter toevoegen? Schrijf een module met een fetch(source) en
parse(raw, source) functie, plus een CAPABILITIES-dict (zie
adapters/generic_links.py voor een minimaal voorbeeld), en voeg 'm
hieronder toe aan ADAPTERS.
"""

from adapters import generic_links
from adapters import html_listing
from adapters import jsonld_listing
from adapters import microdata_listing
from adapters import cso_api
from adapters.base import AdapterError


ADAPTERS = {
    "generic_links": generic_links,
    "html_listing": html_listing,
    "jsonld_listing": jsonld_listing,
    "microdata_listing": microdata_listing,
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


def list_adapters():
    """Namen van alle geregistreerde adapters, in vaste volgorde."""

    return list(ADAPTERS.keys())


def get_capabilities(adapter_name):
    """
    Geeft de CAPABILITIES-dict van een adapter terug (leeg dict als de
    adapter er per ongeluk geen heeft gedefinieerd, zodat de UI niet
    crasht op een ontbrekend veld).
    """

    adapter = get(adapter_name)

    return getattr(adapter, "CAPABILITIES", {})


def get_description(adapter_name):
    """
    Leidt een korte beschrijving af uit de docstring van de adapter,
    zodat de beschrijving niet dubbel onderhouden hoeft te worden
    (staat al bovenin elk adapters/*.py bestand). Slaat de "Adapter:
    xxx"-headerregel over en pakt de eerste echte inhoudsalinea.
    """

    adapter = get(adapter_name)

    doc = adapter.__doc__ or ""

    paragraphs = [p.strip() for p in doc.strip().split("\n\n") if p.strip()]

    for paragraph in paragraphs:

        if paragraph.lower().startswith("adapter:"):
            continue

        return " ".join(line.strip() for line in paragraph.splitlines())

    return ""
