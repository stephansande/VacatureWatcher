# Voorbeeldconfiguratie per site

Deze waarden vul je in bij het aanmaken/bewerken van een Source
(`type = "jobboard"`). Alles wat adapter-specifiek is staat in de
ÉÉN generieke `settings`-kolom (JSON) -- zie `adapters/base.py` voor
`load_settings()`.

## Werken voor Nederland (adapter: `cso_api`)

Vereist een API-account (username/password) via de CSO-helpdesk
(helpdesk@werkenvoornederland.nl). Zet de gegevens in `.env`:

```
CSO_USERNAME=...
CSO_PASSWORD=...
```

`settings`:
```json
{
  "keywords": "cultuur, erfgoed, museum",
  "job_url_template": "https://www.werkenvoornederland.nl/vacatures/vacature/{code}"
}
```
Verifieer `job_url_template` zelf (zie de docstring in `cso_api.py`) --
en gebruik eventueel `getJobEnumerations` om de juiste `job_branches`-
codes op te zoeken in plaats van op keywords te filteren.

## Sites met schema.org JobPosting-data (adapter: `jsonld_listing`)

Probeer dit EERST voordat je `html_listing` gebruikt: check (via
"Inspecteren" -> zoek naar `<script type="application/ld+json">`) of
een site JobPosting-structured-data aanbiedt. Dat is stabieler dan
CSS-selectors, en scheelt je het uitzoeken van classes.

Als de zoekpagina zelf al JobPosting-blokken bevat:
```json
{
  "start_url": "https://voorbeeld.nl/vacatures/",
  "mode": "listing",
  "crawl_delay": 5
}
```

Als alleen de detailpagina's JobPosting bevatten (vaker het geval):
```json
{
  "start_url": "https://voorbeeld.nl/vacatures/",
  "mode": "detail",
  "link_selector": ".vacature-item a",
  "max_items": 40,
  "crawl_delay": 5
}
```
Let op: mode "detail" doet één request per vacature, dus houd
`max_items` en `crawl_delay` in de gaten voordat je een site
"bombardeert".

## Sites met schema.org microdata (adapter: `microdata_listing`)

Een tweede manier waarop schema.org-data voorkomt: niet als los
`<script>`-blok, maar direct als HTML-attributen op de bestaande
elementen (`itemscope`, `itemtype="https://schema.org/JobPosting"`,
`itemprop="title"` etc.). Check via "Inspecteren" of je `itemtype`
met "JobPosting" erin tegenkomt in de HTML-broncode.

Zelfde configuratievorm als `jsonld_listing` (ook met "listing"/
"detail"-mode):
```json
{
  "start_url": "https://voorbeeld.nl/vacatures/",
  "mode": "listing",
  "crawl_delay": 5
}
```

De Adapter Helper probeert dit automatisch als tweede optie (na
JSON-LD, vóór html_listing) -- meestal hoef je dit dus niet handmatig
te configureren.

## Werken bij Gemeenten, Culturele Vacatures, Werken voor Cultuur,
## OneWorld, Nationale Vacaturebank (adapter: `html_listing`)

Gebruik dit als de site GEEN JSON-LD JobPosting-data heeft. Ik kon de
ruwe HTML-broncode niet inzien (mijn tools laten alleen leesbare tekst
zien, geen class-namen) -- dus onderstaande `settings` is een
SJABLOON, geen kant-en-klare configuratie.

```json
{
  "start_url": "https://werkenbijgemeenten.nl/vacatures",
  "selectors": {
    "item": "VUL_IN",
    "title": "VUL_IN",
    "link": "VUL_IN",
    "location": "VUL_IN",
    "date": "VUL_IN"
  },
  "categories": ["betaalde-functie"],
  "pagination": {
    "url_pattern": "VUL_IN?page={page}",
    "max_pages": 3
  },
  "crawl_delay": 5,
  "include_keywords": ["cultuur", "erfgoed"],
  "exclude_keywords": ["stage", "vrijwilliger"]
}
```

`categories` wordt momenteel niet automatisch verwerkt -- de meeste
sites geven een categorie door als onderdeel van `start_url` zelf
(bv. `.../category/betaalde-functie/`, zoals bij Culturele Vacatures).
Het veld staat klaar voor als je dit per site wilt uitbreiden.

### Zo vind je de juiste selectors (5 minuten werk per site)

1. Open de vacaturesite in Chrome/Firefox.
2. Rechtermuisklik op de titel van één vacature-item -> "Inspecteren"
   (Inspect).
3. Zoek in de devtools het element dat de HELE vacature-kaart omvat
   (titel + locatie + omschrijving samen) -- dat is je
   `selectors.item`. Vaak een `<div class="...">` of `<article>`.
   Rechtermuisklik op dat element -> Copy -> Copy selector.
4. Zoek binnen dat blok het element met de titel/link -> dat is je
   `selectors.title`/`selectors.link` (meestal dezelfde `<a>`-tag).
5. Doe hetzelfde voor locatie/datum als je die apart wilt tonen.
6. Voor paginering: klik op "volgende pagina" en kijk hoe de URL
   verandert (bv. `?page=2` of `/pagina/2/`). Zet dat patroon in
   `pagination.url_pattern` met `{page}` op de juiste plek.

Twijfel je? Plak me een stukje van de "Copy element"-HTML van één
vacature-blok (rechtermuisklik -> Inspecteren -> rechtermuisklik op
het element in de devtools -> Copy -> Copy element) en ik schrijf de
exacte selectors voor je.
