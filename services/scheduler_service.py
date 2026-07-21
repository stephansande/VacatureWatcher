from datetime import datetime


from apscheduler.schedulers.background import (
    BackgroundScheduler
)


from models import Source, ALL_WEEKDAYS


from services.vacancy_checker import (
    check_source
)



scheduler = BackgroundScheduler()



def _should_check(source, today=None):
    """
    Bepaalt of `source` vandaag gecontroleerd moet worden, op basis
    van zowel check_days (OP WELKE dagen dit MAG) als check_interval
    (HOE VAAK op zo'n toegestane dag -- "daily" elke toegestane dag,
    "weekly" alleen op maandag, ongeacht of maandag zelf in check_days
    voorkomt -- zie LET OP hieronder).

    `today` is optioneel een weekday-afkorting ('mon'..'sun'), puur
    voor testbaarheid zonder de systeemklok te hoeven mocken. Zonder
    argument wordt de systeemdatum gebruikt (via Source.runs_today()).

    LET OP -- interactie tussen check_interval="weekly" en check_days:
    "weekly" betekent hier letterlijk "alleen op maandag", ongeacht
    check_days. Kies een bron dus bewust GEEN check_days-selectie
    zonder maandag in combinatie met check_interval="weekly", anders
    draait hij nooit. Dit is bewust niet "stilzwijgend slimmer"
    gemaakt (bv. "eerste toegestane dag van de week"), om het gedrag
    voorspelbaar te houden -- kan in een latere stap alsnog, als dat
    gewenst is.
    """

    if not source.runs_today(today=today):
        return False

    if source.check_interval == "daily":
        return True

    if source.check_interval == "weekly":

        weekday_index = (
            ALL_WEEKDAYS.index(today) if today is not None
            else datetime.now().weekday()
        )

        return weekday_index == 0

    return False  # "disabled" of een onbekende/lege waarde



def run_checks(app):


    with app.app_context():


        sources = Source.query.filter_by(
            enabled=True
        ).all()



        for source in sources:

            if _should_check(source):

                check_source(
                    source
                )





def start_scheduler(app):


    scheduler.add_job(

        lambda:
        run_checks(app),

        "interval",

        hours=24,

        id="vacaturewatcher",

        replace_existing=True

    )


    scheduler.start()