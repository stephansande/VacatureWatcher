"""
Kleine bibliotheek met voorbeeldbronnen, voor nieuwe gebruikers die
niet weten hoe een bron eruit hoort te zien.

Bewust minimaal: alleen naam + URL (+ adapter/settings waar dat al
geverifieerd is, zoals bij CSO). Voor de rest vullen we GEEN
CSS-selectors in die we niet zelf tegen de echte pagina geverifieerd
hebben -- de gebruiker klikt na het kiezen van een voorbeeld zelf op
"Analyseren" (Adapter Helper) om de juiste instellingen te vinden.

Alle URL's hieronder zijn tijdens de ontwikkeling van deze bibliotheek
opgezocht/bevestigd (officiële "werken bij"-sites, of sites waarvan
robots.txt expliciet gecontroleerd is) -- geen giswerk.
"""

EXAMPLE_SOURCES = [
    {
        "key": "werken_voor_nederland",
        "name": "Werken voor Nederland",
        "url": "https://www.werkenvoornederland.nl/vacatures",
        "type": "jobboard",
        "adapter": "cso_api",
        "settings": (
            "{\n"
            '  "keywords": "",\n'
            '  "job_url_template": "https://www.werkenvoornederland.nl/vacatures/vacature/{code}"\n'
            "}"
        ),
        "note": (
            "Vereist een eigen CSO API-account (zie adapters/EXAMPLES.md). "
            "job_url_template is een aanname -- verifieer zelf aan de hand "
            "van één echte vacature-URL."
        ),
    },
    {
        "key": "culturele_vacatures",
        "name": "Culturele Vacatures",
        "url": "https://www.culturele-vacatures.nl/category/betaalde-functie/",
        "type": "jobboard",
        "adapter": "generic_links",
        "settings": "",
        "note": (
            "robots.txt van deze site staat geautomatiseerde toegang toe "
            "(met crawl-delay: 5s). Klik na het kiezen op Analyseren."
        ),
    },
    {
        "key": "werken_bij_gemeenten",
        "name": "Werken bij Gemeenten",
        "url": "https://werkenbijgemeenten.nl/vacatures",
        "type": "jobboard",
        "adapter": "generic_links",
        "settings": "",
        "note": (
            "Verzamelt vacatures van losse gemeentesites op één "
            "overzichtspagina. Klik na het kiezen op Analyseren."
        ),
    },
    {
        "key": "oneworld",
        "name": "OneWorld vacaturebank",
        "url": "https://www.oneworld.nl/vacaturebank/vacatureoverzicht/",
        "type": "jobboard",
        "adapter": "generic_links",
        "settings": "",
        "note": "Klik na het kiezen op Analyseren.",
    },
    {
        "key": "gemeente_rotterdam",
        "name": "Gemeente Rotterdam",
        "url": "https://www.werkenvoorrotterdam.nl/",
        "type": "employer",
        "adapter": "generic_links",
        "settings": "",
        "note": "Officiële werken-bij-site. Klik na het kiezen op Analyseren.",
    },
    {
        "key": "gemeente_utrecht",
        "name": "Gemeente Utrecht",
        "url": "https://www.werkenbijutrecht.nl/vacatures/",
        "type": "employer",
        "adapter": "generic_links",
        "settings": "",
        "note": "Officiële werken-bij-site. Klik na het kiezen op Analyseren.",
    },
    {
        "key": "provincie_zuid_holland",
        "name": "Provincie Zuid-Holland",
        "url": "https://werkenvoor.zuid-holland.nl/vacatures/",
        "type": "employer",
        "adapter": "generic_links",
        "settings": "",
        "note": "Officiële werken-bij-site. Klik na het kiezen op Analyseren.",
    },
]


def get_example(key):

    for example in EXAMPLE_SOURCES:

        if example["key"] == key:
            return example

    return None
