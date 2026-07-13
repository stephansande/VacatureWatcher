from datetime import datetime


from database import db


from models import (
    Vacancy,
    ChangeLog
)


from adapters import registry
from adapters.base import (
    load_settings,
    get_keyword_filters,
    apply_keyword_filter,
    AdapterError,
)


from services.notification_service import notify



def check_employer(source):
    """
    Blijft bestaan als alias voor achterwaartse compatibiliteit
    (bv. bestaande routes die 'check_employer' aanroepen).
    """

    return check_source(source)



def check_source(source):

    adapter = registry.get(source.adapter)

    try:
        raw_content = adapter.fetch(source)
        vacancies = adapter.parse(raw_content, source)

        settings = load_settings(source)
        include_keywords, exclude_keywords = get_keyword_filters(source, settings)

        vacancies = apply_keyword_filter(
            vacancies,
            include_keywords=include_keywords,
            exclude_keywords=exclude_keywords
        )

    except AdapterError as error:

        message = f"Fout bij ophalen van '{source.name}': {error}"

        log = ChangeLog(
            employer_id=source.id,
            change_type="error",
            message=message
        )

        db.session.add(log)

        # ook bij een mislukte controle bijwerken -- anders lijkt een
        # bron die al weken faalt op het dashboard nog "recent
        # gecontroleerd", puur omdat de laatste GESLAAGDE poging lang
        # geleden was
        source.last_check = datetime.utcnow()
        source.last_error = str(error)

        db.session.commit()

        notify("Fout bij vacature-check", message)

        return



    existing = {

        vacancy.url: vacancy

        for vacancy in source.vacancies

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

                employer_id=source.id,

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



    source.last_check = datetime.utcnow()
    source.last_success = datetime.utcnow()
    source.last_error = None
    source.last_new_count = len(new)



    if new or removed:


        message = (
            source.name
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

            employer_id=source.id,

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
