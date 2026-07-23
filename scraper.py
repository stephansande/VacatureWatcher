import hashlib
import requests

from bs4 import BeautifulSoup



# Een realistische, actuele browser-UA -- de vorige waarde,
# "Mozilla/5.0 (VacatureWatcher/1.0)", verklapte in dezelfde string
# dat het een script was, wat veel sites (WAF's, CDN's, of de
# oorspronkelijke server zelf) laat blokkeren of een andere
# (lege/afwijkende) pagina laat teruggeven -- precies het verschil
# tussen "een in de browser opgeslagen pagina analyseren" (werkt
# altijd) en "de container haalt 'm zelf op" (kan stilzwijgend
# geblokkeerd worden, zonder foutmelding: je krijgt gewoon een
# 200-response met andere/lege inhoud terug).
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Alleen een geloofwaardige User-Agent meesturen is vaak niet genoeg --
# een verzoek met UITSLUITEND een User-Agent-header (geen Accept,
# geen Accept-Language) is zelf ook een bekend bot-signaal. Dit is de
# headerset die een gewone Chrome-browser standaard meestuurt.
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "nl-NL,nl;q=0.9,en-US;q=0.8,en;q=0.7",
}



def fetch_page(url, selector=None):

    response = requests.get(
        url,
        headers=DEFAULT_HEADERS,
        timeout=30
    )

    response.raise_for_status()


    html = response.text


    soup = BeautifulSoup(
        html,
        "lxml"
    )


    if selector:

        element = soup.select_one(
            selector
        )

        if element:
            soup = element


    return clean_html(
        str(soup)
    )



def clean_html(content):

    soup = BeautifulSoup(
        content,
        "lxml"
    )


    # verwijderen van scripts
    for item in soup(
        [
            "script",
            "style",
            "noscript"
        ]
    ):
        item.decompose()


    text = soup.get_text(
        separator=" ",
        strip=True
    )


    return text



def create_hash(content):

    return hashlib.sha256(
        content.encode(
            "utf-8"
        )
    ).hexdigest()

def fetch_html(
    url
):

    response = requests.get(
        url,
        headers=DEFAULT_HEADERS,
        timeout=30
    )


    response.raise_for_status()


    return response.text