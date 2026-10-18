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
from adapters import browser_listing
from adapters import cso_api
from adapters import greenhouse
from adapters import discovered_api
from adapters import embedded_json
from adapters.base import AdapterError


ADAPTERS = {
    "generic_links": generic_links,
    "html_listing": html_listing,
    "jsonld_listing": jsonld_listing,
    "microdata_listing": microdata_listing,
    "browser_listing": browser_listing,
    "cso_api": cso_api,
    "greenhouse": greenhouse,
    "discovered_api": discovered_api,
    "embedded_json": embedded_json,
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


def validate_settings(adapter_name, settings_dict, url=None):
    """
    Structurele pre-opslaan-validatie: vraagt de adapter zelf of
    `settings_dict` (en, voor greenhouse, de bron-URL) er compleet
    genoeg uitziet om te kunnen draaien -- VÓÓR er ook maar een
    request de deur uit gaat (dat is de live-validatie hieronder in
    app.py, via diagnostics.test_source()).

    Elke adapter mag optioneel een eigen
    `validate_settings(settings_dict, url)` functie definiëren die
    None (alles in orde) of een foutmelding-string teruggeeft -- zie
    adapters/html_listing.py of adapters/embedded_json.py voor
    voorbeelden. Een adapter zonder eigen implementatie (bv.
    generic_links, dat niets aan settings vereist) wordt stilzwijgend
    als geldig beschouwd.

    Bewust een FUNCTIE per adapter i.p.v. een declaratieve
    "REQUIRED_SETTINGS"-lijst hier centraal: sommige vereisten zijn
    voorwaardelijk (jsonld_listing.link_selector is alleen verplicht
    bij mode "detail", browser_listing.selectors.item alleen bij
    parse_as "html_listing") of hebben een fallback buiten settings om
    (greenhouse.board_token mag ontbreken als de URL zelf op
    boards.greenhouse.io draait) -- dat soort logica past niet netjes
    in een simpele "deze sleutels moeten aanwezig zijn"-lijst, en elke
    adapter kent zijn eigen vereisten toch al het best (dezelfde
    redenering als waarom fetch()/parse() zelf ook per adapter
    verschillen).
    """

    adapter = get(adapter_name)

    validator = getattr(adapter, "validate_settings", None)

    if validator is None:
        return None

    return validator(settings_dict, url)


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
