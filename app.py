import json

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
    Source,
    ChangeLog
)

from services.scheduler_service import (
    start_scheduler
)

from services.vacancy_checker import (
    check_employer
)

from adapter_helper import analyze as run_adapter_helper

from backup import create_backup

from auth import (
    auth,
    login_manager
)



def _load_analysis_from_form():
    """
    Leest de eerder uitgevoerde analyse terug uit het verborgen
    analysis_json-veld, zodat we niet bij elke klik (bv. op "Gebruik
    deze instellingen") de pagina opnieuw hoeven op te halen.
    """

    raw = request.form.get("analysis_json")

    if not raw:
        return None

    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


def _apply_suggestion(action, analysis, form_data):
    """
    Verwerkt een "Gebruik deze instellingen"-knop: zet form_data['adapter']
    en form_data['settings'] op basis van de gekozen adapter uit de
    analyse-resultaten.
    """

    chosen_adapter = action.split(":", 1)[1]

    form_data["adapter"] = chosen_adapter

    if chosen_adapter == "generic_links":
        form_data["settings"] = ""
        return

    if analysis and analysis.get(chosen_adapter):

        suggestion = analysis[chosen_adapter].get("suggested_settings")

        if suggestion:
            form_data["settings"] = json.dumps(
                suggestion, indent=2, ensure_ascii=False
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

        employers = Source.query.order_by(
            Source.name
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


            employer = Source(

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
        "/source/jobboard/add",
        methods=[
            "GET",
            "POST"
        ]
    )
    @login_required
    def add_jobboard_source():

        form_data = {
            "name": "",
            "url": "",
            "adapter": "generic_links",
            "settings": "",
            "keywords": "",
            "check_interval": "daily",
        }

        analysis = None
        error = None

        if request.method == "POST":

            action = request.form.get("action", "save")

            form_data["name"] = request.form.get("name", "")
            form_data["url"] = request.form.get("url", "")
            form_data["adapter"] = request.form.get("adapter", "generic_links")
            form_data["settings"] = request.form.get("settings", "")
            form_data["keywords"] = request.form.get("keywords", "")
            form_data["check_interval"] = request.form.get("check_interval", "daily")

            analysis = _load_analysis_from_form()

            if action == "analyze":

                if not form_data["url"]:
                    error = "Vul eerst een URL in om te analyseren."
                else:
                    analysis = run_adapter_helper(form_data["url"])

            elif action.startswith("apply:"):

                _apply_suggestion(action, analysis, form_data)

            elif action == "save":

                if not form_data["name"] or not form_data["url"]:
                    error = "Naam en URL zijn verplicht."

                else:

                    source = Source(
                        name=form_data["name"],
                        url=form_data["url"],
                        type="jobboard",
                        adapter=form_data["adapter"],
                        settings=form_data["settings"] or None,
                        keywords=form_data["keywords"] or None,
                        check_interval=form_data["check_interval"],
                    )

                    db.session.add(source)
                    db.session.commit()

                    return redirect(
                        url_for("employer_detail", id=source.id)
                    )

        return render_template(
            "source_jobboard_add.html",
            form=form_data,
            analysis=analysis,
            error=error,
        )



    @app.route(
        "/employer/<int:id>"
    )
    @login_required
    def employer_detail(id):


        employer = Source.query.get_or_404(
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


        employer = Source.query.get_or_404(
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


        employer = Source.query.get_or_404(
            id
        )


        if employer.type == "jobboard":
            return _edit_jobboard_source(employer)


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



    def _edit_jobboard_source(source):
        """
        Aparte afhandeling voor type="jobboard": zelfde wizard-stijl als
        add_jobboard_source, maar dan bewerkend op een bestaande Source.
        """

        form_data = {
            "name": source.name,
            "url": source.url,
            "adapter": source.adapter,
            "settings": source.settings or "",
            "keywords": source.keywords or "",
            "check_interval": source.check_interval,
        }

        analysis = None
        error = None

        if request.method == "POST":

            action = request.form.get("action", "save")

            form_data["name"] = request.form.get("name", "")
            form_data["url"] = request.form.get("url", "")
            form_data["adapter"] = request.form.get("adapter", "generic_links")
            form_data["settings"] = request.form.get("settings", "")
            form_data["keywords"] = request.form.get("keywords", "")
            form_data["check_interval"] = request.form.get("check_interval", "daily")

            analysis = _load_analysis_from_form()

            if action == "analyze":

                if not form_data["url"]:
                    error = "Vul eerst een URL in om te analyseren."
                else:
                    analysis = run_adapter_helper(form_data["url"])

            elif action.startswith("apply:"):

                _apply_suggestion(action, analysis, form_data)

            elif action == "save":

                if not form_data["name"] or not form_data["url"]:
                    error = "Naam en URL zijn verplicht."

                else:

                    source.name = form_data["name"]
                    source.url = form_data["url"]
                    source.adapter = form_data["adapter"]
                    source.settings = form_data["settings"] or None
                    source.keywords = form_data["keywords"] or None
                    source.check_interval = form_data["check_interval"]

                    db.session.commit()

                    return redirect(
                        url_for("employer_detail", id=source.id)
                    )

        return render_template(
            "source_jobboard_edit.html",
            source=source,
            form=form_data,
            analysis=analysis,
            error=error,
        )



    @app.route(
        "/employer/<int:id>/delete"
    )
    @login_required
    def delete_employer(id):


        employer = Source.query.get_or_404(
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


        employer = Source.query.get_or_404(
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
