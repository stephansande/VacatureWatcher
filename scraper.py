import hashlib
import requests

from bs4 import BeautifulSoup



USER_AGENT = (
    "Mozilla/5.0 "
    "(VacatureWatcher/1.0)"
)



def fetch_page(url, selector=None):

    headers = {
        "User-Agent": USER_AGENT
    }


    response = requests.get(
        url,
        headers=headers,
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

    headers = {
        "User-Agent":
        USER_AGENT
    }


    response = requests.get(
        url,
        headers=headers,
        timeout=30
    )


    response.raise_for_status()


    return response.text