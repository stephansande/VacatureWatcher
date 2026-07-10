from datetime import datetime


from database import db


from models import (
    Vacancy,
    ChangeLog
)


from scraper import fetch_html


from vacancy_parser import parse_vacancies


from services.notification_service import notify



def check_employer(
    employer
):


    html = fetch_html(
        employer.url
    )


    vacancies = parse_vacancies(
        html,
        employer.url
    )



    existing = {

        vacancy.url: vacancy

        for vacancy in employer.vacancies

        if vacancy.url

    }



    found = set()


    new = []

    removed = []



    for item in vacancies:


        url = item["url"]


        found.add(
            url
        )



        if url not in existing:


            vacancy = Vacancy(

                employer_id=employer.id,

                title=item["title"],

                url=url,

                content=item["content"]

            )


            db.session.add(
                vacancy
            )


            new.append(
                item["title"]
            )


        else:


            vacancy = existing[url]

            vacancy.active = True

            vacancy.last_seen = datetime.utcnow()



    for url, vacancy in existing.items():


        if url not in found:


            if vacancy.active:


                vacancy.active = False

                removed.append(
                    vacancy.title
                )



    employer.last_check = datetime.utcnow()



    if new or removed:


        message = (
            employer.name
            +
            "\n\n"
        )


        if new:

            message += (
                "Nieuwe vacatures:\n"
            )


            for item in new:

                message += (
                    "+ "
                    +
                    item
                    +
                    "\n"
                )



        if removed:


            message += (
                "\nVerdwenen vacatures:\n"
            )


            for item in removed:

                message += (
                    "- "
                    +
                    item
                    +
                    "\n"
                )



        log = ChangeLog(

            employer_id=employer.id,

            change_type="vacancy",

            message=message

        )


        db.session.add(
            log
        )


        notify(
            "Vacature wijziging",
            message
        )



    db.session.commit()