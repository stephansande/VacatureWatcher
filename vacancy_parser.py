from bs4 import BeautifulSoup
from urllib.parse import urljoin



def parse_vacancies(
    html,
    base_url
):

    soup = BeautifulSoup(
        html,
        "lxml"
    )


    vacancies = []



    links = soup.find_all(
        "a",
        href=True
    )


    for link in links:

        title = link.get_text(
            " ",
            strip=True
        )


        url = link["href"]


        if not title:
            continue


        # alleen interessante links
        keywords = [
            "vacature",
            "functie",
            "werken",
            "job",
            "career"
        ]


        combined = (
            title +
            " " +
            url
        ).lower()


        if not any(
            word in combined
            for word in keywords
        ):
            continue



        vacancies.append(
            {
                "title": title,
                "url": urljoin(
                    base_url,
                    url
                ),
                "content": title
            }
        )


    return remove_duplicates(
        vacancies
    )



def remove_duplicates(
    vacancies
):

    result = []

    seen = set()


    for vacancy in vacancies:

        key = vacancy["url"] or vacancy["title"]


        if key not in seen:

            seen.add(key)

            result.append(
                vacancy
            )


    return result