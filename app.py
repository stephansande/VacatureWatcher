from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for
)

from flask_login import (
    LoginManager,
    login_required
)

from config import Config

from database import (
    db,
    init_database
)

from models import (
    Employer,
    ChangeLog
)

from services.scheduler_service import (
    start_scheduler
)

from services.vacancy_checker import (
    check_employer
)

from backup import create_backup

from auth import (
    auth,
    login_manager
)



def create_app():

    app = Flask(__name__)

    app.config.from_object(
        Config
    )


    # Login configuratie

    login_manager.init_app(
        app
    )

    login_manager.login_view = (
        "auth.login"
    )

    app.register_blueprint(
        auth
    )


    init_database(
        app
    )


    # Start automatische controles

    start_scheduler(
        app
    )



    @app.route("/")
    @login_required
    def dashboard():

        employers = Employer.query.order_by(
            Employer.name
        ).all()


        return render_template(
            "dashboard.html",
            employers=employers
        )



    @app.route(
        "/employer/add",
        methods=[
            "GET",
            "POST"
        ]
    )
    @login_required
    def add_employer():


        if request.method == "POST":


            employer = Employer(

                name=request.form["name"],

                url=request.form["url"],

                selector=request.form.get(
                    "selector"
                ),

                keywords=request.form.get(
                    "keywords"
                ),

                check_interval=request.form.get(
                    "check_interval",
                    "daily"
                )

            )


            db.session.add(
                employer
            )


            db.session.commit()



            return redirect(
                url_for(
                    "dashboard"
                )
            )



        return render_template(
            "employer.html"
        )



    @app.route(
        "/employer/<int:id>"
    )
    @login_required
    def employer_detail(id):


        employer = Employer.query.get_or_404(
            id
        )


        logs = ChangeLog.query.filter_by(
            employer_id=id
        ).order_by(
            ChangeLog.created_at.desc()
        ).all()



        return render_template(
            "employer_detail.html",
            employer=employer,
            logs=logs
        )



    @app.route(
        "/employer/<int:id>/check"
    )
    @login_required
    def manual_check(id):


        employer = Employer.query.get_or_404(
            id
        )


        check_employer(
            employer
        )



        return redirect(
            url_for(
                "employer_detail",
                id=id
            )
        )



    @app.route(
        "/history"
    )
    @login_required
    def history():


        logs = ChangeLog.query.order_by(
            ChangeLog.created_at.desc()
        ).all()



        return render_template(
            "history.html",
            logs=logs
        )



    @app.route(
        "/employer/<int:id>/edit",
        methods=[
            "GET",
            "POST"
        ]
    )
    @login_required
    def edit_employer(id):


        employer = Employer.query.get_or_404(
            id
        )


        if request.method == "POST":


            employer.name = (
                request.form["name"]
            )


            employer.url = (
                request.form["url"]
            )


            employer.selector = (
                request.form.get(
                    "selector"
                )
            )


            employer.keywords = (
                request.form.get(
                    "keywords"
                )
            )


            employer.check_interval = (
                request.form.get(
                    "check_interval",
                    "daily"
                )
            )


            db.session.commit()



            return redirect(
                url_for(
                    "employer_detail",
                    id=id
                )
            )



        return render_template(
            "employer_edit.html",
            employer=employer
        )



    @app.route(
        "/employer/<int:id>/delete"
    )
    @login_required
    def delete_employer(id):


        employer = Employer.query.get_or_404(
            id
        )


        db.session.delete(
            employer
        )


        db.session.commit()



        return redirect(
            url_for(
                "dashboard"
            )
        )



    @app.route(
        "/employer/<int:id>/vacancies"
    )
    @login_required
    def vacancies(id):


        employer = Employer.query.get_or_404(
            id
        )


        return render_template(
            "vacancies.html",
            employer=employer
        )



    @app.route(
        "/settings"
    )
    @login_required
    def settings():


        return render_template(
            "settings.html"
        )



    @app.route(
        "/backup"
    )
    @login_required
    def backup():


        filename = create_backup()



        return (
            "Backup gemaakt:<br>"
            +
            filename
        )



    return app





app = create_app()



if __name__ == "__main__":


    app.run(
        host="0.0.0.0",
        port=5000
    )
```
