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
    ChangeLog,
    Vacancy,
    ALL_WEEKDAYS
)

from services.scheduler_service import (
    start_scheduler
)

from services.vacancy_checker import (
    check_employer
)

from adapters import registry as adapter_registry

from adapter_helper import analyze as run_adapter_helper
from adapter_helper import test_source as run_source_test
from adapter_helper import diagnose_source

from example_sources import EXAMPLE_SOURCES, get_example

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


CANDIDATE_KEY_BY_ADAPTER = {
    "jsonld_listing": "jsonld",
    "microdata_listing": "microdata",
}
# adapter_helper.analyze() gebruikt "jsonld"/"microdata" als sleutel
# voor de kandidaat-preview, maar de adapter-registry (en dus de
# "apply:<adapter>"-knoppen) heet ze "jsonld_listing"/"microdata_listing".
# Zonder deze mapping keek _apply_suggestion() hieronder altijd mis
# (analysis.get("jsonld_listing") bestaat niet), waardoor "Gebruik
# deze instellingen" voor die twee kandidaten stil faalde -- dit zat
# al zo in de oorspronkelijke skeleton, vóór de Website
# Detective-aanpassingen.


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

    if not analysis:
        return

    # De aanbevolen adapter heeft altijd recommended_settings (ook
    # greenhouse, dat geen aparte candidate-preview met
    # suggested_settings heeft zoals jsonld/microdata/html_listing) --
    # check die eerst.
    if chosen_adapter == analysis.get("recommendation") and analysis.get("recommended_settings"):
        form_data["settings"] = json.dumps(
            analysis["recommended_settings"], indent=2, ensure_ascii=False
        )
        return

    candidate_key = CANDIDATE_KEY_BY_ADAPTER.get(chosen_adapter, chosen_adapter)
    candidate = analysis.get(candidate_key)

    if candidate:

        suggestion = candidate.get("suggested_settings")

        if suggestion:
            form_data["settings"] = json.dumps(
                suggestion, indent=2, ensure_ascii=False
            )



def _validate_settings(adapter_name, settings_text):
    """
    Lichte validatie bij het opslaan van een bron, zodat een kapotte
    configuratie meteen zichtbaar is in plaats van pas bij de eerste
    (mislukte) geplande controle. Geeft een foutmelding terug, of None
    als alles in orde is.
    """

    if not settings_text or not settings_text.strip():
        # settings is optioneel voor de meeste adapters (bv. cso_api,
        # of html_listing/jsonld/microdata die op source.url terugvallen
        # als start_url ontbreekt) -- alleen html_listing/browser_listing
        # kunnen zonder selectors niets, dat vangen we hieronder af.
        settings_dict = {}
    else:
        try:
            settings_dict = json.loads(settings_text)
        except (ValueError, TypeError) as error:
            return f"Settings is geen geldige JSON: {error}"

        if not isinstance(settings_dict, dict):
            return "Settings moet een JSON-object zijn (bv. {\"start_url\": \"...\"})."

    if adapter_name in ("html_listing", "browser_listing"):

        if adapter_name == "browser_listing" and settings_dict.get("parse_as", "html_listing") != "html_listing":
            return None

        selectors = settings_dict.get("selectors", {})

        if not selectors.get("item"):
            return "settings.selectors.item ontbreekt (verplicht voor deze adapter)."

        if not selectors.get("title") and not selectors.get("link"):
            return "settings.selectors.title of settings.selectors.link ontbreekt (minstens één is verplicht)."

    return None



def _render_source_editor(source=None):
    """
    Gedeelde logica achter zowel /employer/add als /employer/<id>/edit.
    Werkt voor beide brontypes (employer/jobboard) en voor beide
    acties (aanmaken/bewerken) -- vandaar één template, source_edit.html,
    in plaats van vier losse formulieren zoals voorheen.
    """

    is_new = source is None

    if is_new:
        form_data = {
            "type": "employer",
            "name": "",
            "url": "",
            "adapter": "generic_links",
            "settings": "",
            "keywords": "",
            "check_interval": "daily",
            "check_days": list(ALL_WEEKDAYS),
        }
    else:
        form_data = {
            "type": source.type,
            "name": source.name,
            "url": source.url,
            "adapter": source.adapter,
            "settings": source.settings or "",
            "keywords": source.keywords or "",
            "check_interval": source.check_interval,
            "check_days": source.check_days_list,
        }

    analysis = None
    error = None
    info = None

    if request.method == "POST":

        action = request.form.get("action", "save")

        form_data["type"] = request.form.get("type", "employer")
        form_data["name"] = request.form.get("name", "")
        form_data["url"] = request.form.get("url", "")
        form_data["adapter"] = request.form.get("adapter", "generic_links")
        form_data["settings"] = request.form.get("settings", "")
        form_data["keywords"] = request.form.get("keywords", "")
        form_data["check_interval"] = request.form.get("check_interval", "daily")
        form_data["check_days"] = request.form.getlist("check_days") or list(ALL_WEEKDAYS)
        # getlist(): checkboxes met dezelfde name komen zo allemaal
        # binnen. Leeg (niets aangevinkt) valt terug op "alle dagen",
        # zodat een gebruiker een bron niet per ongeluk stilletjes
        # helemaal uitzet door alle vinkjes weg te halen -- zie ook
        # Source.check_days_list-setter in models.py.

        analysis = _load_analysis_from_form()

        if action == "analyze":

            if not form_data["url"]:
                error = "Vul eerst een URL in om te analyseren."
            else:
                force_refresh = request.form.get("force_refresh") == "1"
                analysis = run_adapter_helper(form_data["url"], force_refresh=force_refresh)

        elif action.startswith("apply:"):

            _apply_suggestion(action, analysis, form_data)

        elif action == "use_example":

            example_key = request.form.get("example_key", "")
            example = get_example(example_key)

            if example:
                form_data["name"] = example["name"]
                form_data["url"] = example["url"]
                form_data["type"] = example["type"]
                form_data["adapter"] = example["adapter"]
                form_data["settings"] = example["settings"]
                analysis = None
                info = f"Voorbeeld '{example['name']}' ingevuld. {example['note']}"

        elif action == "save":

            if not form_data["name"] or not form_data["url"]:
                error = "Naam en URL zijn verplicht."

            else:

                error = _validate_settings(form_data["adapter"], form_data["settings"])

            if not error:

                if is_new:

                    source = Source(
                        name=form_data["name"],
                        url=form_data["url"],
                        type=form_data["type"],
                        adapter=form_data["adapter"],
                        settings=form_data["settings"] or None,
                        keywords=form_data["keywords"] or None,
                        check_interval=form_data["check_interval"],
                    )
                    source.check_days_list = form_data["check_days"]

                    db.session.add(source)

                else:

                    source.name = form_data["name"]
                    source.url = form_data["url"]
                    source.type = form_data["type"]
                    source.adapter = form_data["adapter"]
                    source.settings = form_data["settings"] or None
                    source.keywords = form_data["keywords"] or None
                    source.check_interval = form_data["check_interval"]
                    source.check_days_list = form_data["check_days"]

                db.session.commit()

                return redirect(
                    url_for("employer_detail", id=source.id)
                )

    return render_template(
        "source_edit.html",
        source=source,
        form=form_data,
        analysis=analysis,
        error=error,
        info=info,
        is_new=is_new,
        examples=EXAMPLE_SOURCES,
        all_weekdays=ALL_WEEKDAYS,
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



    @app.route("/vacatures")
    @login_required
    def vacatures_overzicht():
        """
        Bron | Actuele vacatures naast elkaar, over alle bronnen heen --
        dezelfde weergave als het handmatige bronnenoverzicht.html-rapport,
        maar dan met live data uit de database i.p.v. een momentopname.
        """

        sources = Source.query.order_by(Source.name).all()

        rows = []

        for source in sources:

            active_vacancies = [
                vacancy for vacancy in source.vacancies if vacancy.active
            ]

            active_vacancies.sort(key=lambda v: v.title)

            rows.append({
                "source": source,
                "vacancies": active_vacancies,
            })

        total_vacancies = sum(len(row["vacancies"]) for row in rows)

        return render_template(
            "vacatures_overzicht.html",
            rows=rows,
            total_sources=len(rows),
            total_vacancies=total_vacancies,
        )



    @app.route("/vacatures/tijdlijn")
    @login_required
    def vacatures_tijdlijn():
        """
        Chronologisch overzicht (datum -- vacature -- bron) over alle
        bronnen heen, nieuwste eerst. Aanvulling op /vacatures
        hierboven (die per bron groepeert) -- hier staat juist de
        volgorde waarin vacatures zijn verschenen centraal, ongeacht
        welke bron erbij hoort.

        Toont standaard alleen actieve vacatures; ?toon=alle laat ook
        verdwenen vacatures zien (met een "Verdwenen"-badge en de
        datum waarop ze voor het laatst zijn gezien).
        """

        toon_alles = request.args.get("toon") == "alle"

        query = Vacancy.query

        if not toon_alles:
            query = query.filter_by(active=True)

        vacancies = (
            query
            .join(Source, Vacancy.employer_id == Source.id)
            .order_by(Vacancy.first_seen.desc())
            .limit(200)
            .all()
        )

        return render_template(
            "vacatures_tijdlijn.html",
            vacancies=vacancies,
            toon_alles=toon_alles,
            total=len(vacancies),
        )



    @app.route("/system/adapters")
    @login_required
    def system_adapters():

        adapters_info = []

        for name in adapter_registry.list_adapters():

            capabilities = adapter_registry.get_capabilities(name)

            adapters_info.append({
                "name": name,
                "label": capabilities.get("label", name),
                "description": adapter_registry.get_description(name),
                "capabilities": capabilities,
                "source_count": Source.query.filter_by(adapter=name).count(),
            })

        return render_template(
            "system_adapters.html",
            adapters=adapters_info
        )



    @app.route("/system/diagnose")
    @login_required
    def system_diagnose():
        """
        Draait 'Bron testen' in één keer tegen ALLE bronnen, en
        categoriseert de resultaten (ok / geen resultaten / fout).
        Kan even duren bij veel bronnen -- elke bron wordt na elkaar
        opgehaald, net als een geplande controle dat zou doen.
        """

        sources = Source.query.order_by(Source.name).all()

        diagnoses = [diagnose_source(source) for source in sources]

        summary = {
            "ok": sum(1 for d in diagnoses if d["category"] == "ok"),
            "geen_resultaten": sum(1 for d in diagnoses if d["category"] == "geen_resultaten"),
            "fout": sum(1 for d in diagnoses if d["category"] == "fout"),
        }

        # problematische bronnen eerst, zodat je niet door de werkende
        # bronnen heen hoeft te scrollen
        category_order = {"fout": 0, "geen_resultaten": 1, "ok": 2}
        diagnoses.sort(key=lambda d: category_order[d["category"]])

        return render_template(
            "system_diagnose.html",
            diagnoses=diagnoses,
            summary=summary,
            total=len(diagnoses),
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

        return _render_source_editor(source=None)



    @app.route(
        "/source/jobboard/add"
    )
    @login_required
    def add_jobboard_source():
        """Backward-compat redirect -- deze URL is samengevoegd met /employer/add."""

        return redirect(
            url_for("add_employer")
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
        "/employer/<int:id>/test"
    )
    @login_required
    def test_source_route(id):


        employer = Source.query.get_or_404(
            id
        )


        logs = ChangeLog.query.filter_by(
            employer_id=id
        ).order_by(
            ChangeLog.created_at.desc()
        ).all()


        test_result = run_source_test(employer)


        return render_template(
            "employer_detail.html",
            employer=employer,
            logs=logs,
            test_result=test_result
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


        return _render_source_editor(source=employer)



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
