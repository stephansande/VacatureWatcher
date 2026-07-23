"""
Tests voor de link_attr/"self"-uitbreiding in adapters/html_listing.py.

Aanleiding: Werken voor Wassenaar bouwt vacaturekaarten met
<div onclick="location.href='...'"> in plaats van een echte
<a href="...">. Vóór deze uitbreiding kon geen enkele adapter
(inclusief browser_listing, dat html_listing.parse() hergebruikt na
JS-rendering) zulke sites verwerken. Zie ook de echte, opgeslagen HTML
van deze site voor het end-to-end bewijs dat dit werkt.
"""

from types import SimpleNamespace
import json

from adapters.html_listing import parse


SAMPLE_HTML_ONCLICK = """
<html><body>
<div id="app">
  <div class="card customCard" onclick="location.href='vacature.html?id=1';">
    <h4 class="card-title">Eerste vacature</h4>
  </div>
  <div class="card customCard" onclick="location.href='vacature.html?id=2';">
    <h4 class="card-title">Tweede vacature</h4>
  </div>
  <!-- template-placeholder zonder onclick, hoort overgeslagen te worden -->
  <div class="card customCard">
    <h4 class="card-title"></h4>
  </div>
</div>
</body></html>
"""


def _source(selectors, start_url="https://example.nl/"):
    return SimpleNamespace(
        name="Test",
        url=start_url,
        settings=json.dumps({"start_url": start_url, "selectors": selectors}),
        keywords=None,
    )


def test_link_attr_onclick_met_self_extraheert_url():

    source = _source({
        "item": "div.customCard[onclick]",
        "title": ".card-title",
        "link": "self",
        "link_attr": "onclick",
    })

    result = parse([SAMPLE_HTML_ONCLICK], source)

    assert len(result) == 2
    assert result[0]["url"] == "https://example.nl/vacature.html?id=1"
    assert result[0]["title"] == "Eerste vacature"
    assert result[1]["url"] == "https://example.nl/vacature.html?id=2"


def test_link_attr_onclick_zonder_item_filter_slaat_lege_kaart_over():
    """
    Zonder [onclick] in de item-selector zou de derde (template-)kaart
    ook meegenomen worden -- title is dan leeg, en _extract_url geeft
    None terug omdat er geen onclick-attribuut is, dus die kaart wordt
    alsnog overgeslagen (net als een ontbrekende href bij de normale
    "href"-modus).
    """

    source = _source({
        "item": "div.customCard",
        "title": ".card-title",
        "link": "self",
        "link_attr": "onclick",
    })

    result = parse([SAMPLE_HTML_ONCLICK], source)

    assert len(result) == 2  # de lege template-kaart is overgeslagen
    urls = [v["url"] for v in result]
    assert "https://example.nl/vacature.html?id=1" in urls
    assert "https://example.nl/vacature.html?id=2" in urls


def test_link_attr_default_blijft_href_zoals_voorheen():
    """Regressie: bestaande configuraties zonder link_attr blijven werken."""

    html = """
    <ul>
      <li class="item"><a href="/vacature/1">Titel 1</a></li>
      <li class="item"><a href="/vacature/2">Titel 2</a></li>
    </ul>
    """

    source = _source({
        "item": "li.item",
        "link": "a",
    }, start_url="https://example.nl/")

    result = parse([html], source)

    assert len(result) == 2
    assert result[0]["url"] == "https://example.nl/vacature/1"
