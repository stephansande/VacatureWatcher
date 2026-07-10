from datetime import datetime


from apscheduler.schedulers.background import (
    BackgroundScheduler
)


from models import Employer


from services.vacancy_checker import (
    check_employer
)



scheduler = BackgroundScheduler()



def run_checks(app):


    with app.app_context():


        employers = Employer.query.filter_by(
            enabled=True
        ).all()



        for employer in employers:


            if employer.check_interval == "daily":

                check_employer(
                    employer
                )



            elif employer.check_interval == "weekly":


                if datetime.now().weekday() == 0:

                    check_employer(
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