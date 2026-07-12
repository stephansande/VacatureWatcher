from datetime import datetime


from apscheduler.schedulers.background import (
    BackgroundScheduler
)


from models import Source


from services.vacancy_checker import (
    check_source
)



scheduler = BackgroundScheduler()



def run_checks(app):


    with app.app_context():


        employers = Source.query.filter_by(
            enabled=True
        ).all()



        for employer in employers:


            if employer.check_interval == "daily":

                check_source(
                    employer
                )



            elif employer.check_interval == "weekly":


                if datetime.now().weekday() == 0:

                    check_source(
                        employer
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