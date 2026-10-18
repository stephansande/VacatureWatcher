import json

from types import SimpleNamespace

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for
)

from flask_login import (
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
from diagnostics import test_source as run_source_test
from diagnostics import diagnose_source
from diagnostics import raw_fetch_debug
from adapters import discovered_api
from adapters.base import AdapterError

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


def _apply_discovered_api(action, analysis, form_data):
    """
    Verwerkt een "Gebruik deze API"-knop bij een ontdekte
    netwerkverkeer-kandidaat (analysis["discovered_requests"][N], zie
    browser_analysis.py). Zet adapter op "discovered_api" en stelt
    endpoint_url/items_path voor -- field_map blijft BEWUST leeg: welke
    JSON-sleutel bij titel/url/locatie hoort is per site anders, en
    dat raden zou stille verkeerde matches kunnen opleveren. De
    gebruiker vult dit zelf in aan de hand van de getoonde
    body_preview.
    """

    try:
        index = int(action.split(":", 1)[1])
    except (IndexError, ValueError):
        return

    if not analysis:
        return

    discovered = analysis.get("discovered_requests") or []

    if index < 0 or index >= len(discovered):
        return

    candidate = discovered[index]

    form_data["adapter"] = "discovered_api"
    form_data["settings"] = json.dumps(
        discovered_api.settings_from_discovered_request(candidate),
        indent=2,
        ensure_ascii=False,
    )



TEST_SOURCE_PREVIEW_LIMIT = 5
# Zelfde beperking als diagnostics.TEST_PREVIEW_LIMIT -- een live
# pre-save-check hoeft geen volledige scrape te doen, alleen genoeg om
# te weten of fetch()+parse() daadwerkelijk werkt.


def _parse_settings_json(settings_text):
    """
    Parseert het settings-tekstveld naar een dict, of geeft een
    foutmelding terug bij ongeldige JSON. Gedeeld door
    _validate_settings() en _maybe_run_live_validation() zodat een
    kapotte JSON maar op één plek als "geen geldige JSON"-fout
    herkend wordt.
    """

    if not settings_text or not settings_text.strip():
        # settings is optioneel voor de meeste adapters (bv. cso_api,
        # of html_listing/jsonld/microdata die op source.url terugvallen
        # als start_url ontbreekt).
        return {}, None

    try:
        settings_dict = json.loads(settings_text)
    except (ValueError, TypeError) as error:
        return None, f"Settings is geen geldige JSON: {error}"

    if not isinstance(settings_dict, dict):
        return None, "Settings moet een JSON-object zijn (bv. {\"start_url\": \"...\"})."

    return settings_dict, None


def _validate_settings(adapter_name, settings_text, url):
    """
    STRUCTURELE validatie bij het opslaan van een bron: is de settings-
    JSON geldig, en heeft de gekozen adapter de velden die hij
    sowieso nodig heeft (zie adapters/registry.validate_settings() en
    de validate_settings()-functie van de adapter zelf)? Dit is de
    HARDE, niet-overslaanbare stap -- geen netwerk nodig, dus geen
    reden om ooit een save tegen te houden op basis van bv. een
    trage/onbereikbare site. Geeft een foutmelding terug, of None als
    alles in orde is.

    Dit is stap 1 van de validator uit de roadmap; stap 2 is de LIVE
    check in _maybe_run_live_validation() hieronder, die pas draait
    als deze structurele check al geslaagd is.
    """

    settings_dict, error = _parse_settings_json(settings_text)

    if error:
        return error

    try:
        return adapter_registry.validate_settings(adapter_name, settings_dict, url)
    except AdapterError as error:
        # Onbekende adapternaam (bv. via een handmatig aangepast
        # formulier) -- dezelfde soort foutmelding als de rest van
        # deze functie, i.p.v. een kale stacktrace.
        return str(error)


def _maybe_run_live_validation(adapter_name, url, settings_text, live_test_requested):
    """
    LIVE validatie: voert de daadwerkelijke fetch()+parse() van de
    gekozen adapter uit tegen de (nog niet opgeslagen) ingevulde
    instellingen, via diagnostics.test_source() -- exact dezelfde
    functie als achter de "Bron testen"-knop, dus geen aparte
    testpijplijn om uit de pas te laten lopen. Dit vangt fouten die
    een structurele check niet kan zien: een settings.items_path dat
    er geldig uitziet maar niet naar een array wijst, een 404 op de
    endpoint_url, een CSS-selector die niets meer matcht sinds een
    redesign, etc.

    Draait alleen als _validate_settings() hierboven al is geslaagd
    (geen zin om een kapotte pagina op te halen voor settings die
    toch al ongeldig zijn), en alleen als het adapter-type dat
    volgens zijn CAPABILITIES["live_validation"] toestaat:

    - "always"  -- gewone HTTP-adapters (generic_links, html_listing,
                   jsonld/microdata_listing, discovered_api,
                   greenhouse): snel, geen credentials nodig, dus
                   automatisch bij elke opslag.
    - "opt_in"  -- browser-adapters (browser_listing, embedded_json):
                   starten een headless Chromium, dat kost een paar
                   seconden en is niet overal beschikbaar -- draait
                   dus ALLEEN als de gebruiker het vinkje "Ook live
                   testen" aanzet (zie source_edit.html).
    - "skip"    -- adapters die van omgevingsconfiguratie buiten
                   Source.settings om afhangen (cso_api's
                   CSO_USERNAME/CSO_PASSWORD): ontbrekende
                   credentials in bv. een dev-omgeving zeggen niets
                   over of DEZE bron goed is ingesteld, dus nooit
                   automatisch.

    Geeft de foutmelding van test_source() terug (of None bij succes
    of een bewust overgeslagen check) -- dit blokkeert het opslaan
    NIET zelf; dat beslist de aanroeper in _render_source_editor(),
    die de gebruiker ook de kans geeft om dit te negeren ("Toch
    opslaan").
    """

    capabilities = adapter_registry.get_capabilities(adapter_name)
    live_policy = capabilities.get("live_validation", "always")

    if live_policy == "skip":
        return None

    if live_policy == "opt_in" and not live_test_requested:
        return None

    temp_source = SimpleNamespace(
        id=None,
        name="(nog niet opgeslagen)",
        url=url,
        adapter=adapter_name,
        settings=settings_text or None,
        keywords=None,
    )

    result = run_source_test(temp_source, limit=TEST_SOURCE_PREVIEW_LIMIT)

    return result["error"]





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
            "live_test": False,
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
            "live_test": False,
        }

    analysis = None
    error = None
    info = None
    live_validation_failed = False

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
        form_data["live_test"] = request.form.get("live_test") == "1"
        # Alleen relevant voor adapters met CAPABILITIES["live_validation"]
        # == "opt_in" (browser_listing, embedded_json) -- zie
        # _maybe_run_live_validation(). Onthouden in form_data zodat het
        # vinkje blijft staan als de pagina opnieuw gerenderd wordt (bv.
        # na een validatiefout).

        analysis = _load_analysis_from_form()

        if action == "analyze":

            if not form_data["url"]:
                error = "Vul eerst een URL in om te analyseren."
            else:
                force_refresh = request.form.get("force_refresh") == "1"
                analysis = run_adapter_helper(form_data["url"], force_refresh=force_refresh)

        elif action.startswith("apply:"):

            _apply_suggestion(action, analysis, form_data)

        elif action.startswith("apply_api:"):

            _apply_discovered_api(action, analysis, form_data)

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

                error = _validate_settings(
                    form_data["adapter"], form_data["settings"], form_data["url"]
                )

            if not error:

                confirm_despite_error = request.form.get("confirm_save_despite_error") == "1"

                if not confirm_despite_error:
                    # Alleen de duurdere live-check draaien als de
                    # gebruiker 'm niet al bewust overrulet -- anders
                    # zou "Toch opslaan" zelf weer een onnodige extra
                    # request naar de doelsite triggeren.
                    live_check_error = _maybe_run_live_validation(
                        form_data["adapter"],
                        form_data["url"],
                        form_data["settings"],
                        form_data["live_test"],
                    )

                    if live_check_error:
                        # Zachte blokkade: de structurele instellingen
                        # zijn geldig, maar fetch()+parse() faalde
                        # daadwerkelijk tegen de live site. Anders dan
                        # een structurele fout (ongeldige JSON,
                        # ontbrekend verplicht veld) kan dit ook een
                        # tijdelijk probleem aan de kant van de
                        # doelsite zijn -- vandaar de
                        # "Toch opslaan"-optie in source_edit.html
                        # i.p.v. een harde blokkade.
                        error = live_check_error
                        live_validation_failed = True

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
        live_validation_failed=live_validation_failed,
        adapter_capabilities=adapter_registry.get_capabilities(form_data["adapter"]),
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
        "/employer/<int:id>/raw_fetch"
    )
    @login_required
    def raw_fetch_route(id):
        """
        "Ruwe respons bekijken" -- haalt de bron-URL rechtstreeks op,
        zonder adapter/selector-logica ertussen. Bedoeld voor precies
        het scenario waarbij zowel de Adapter Helper als een
        handmatige adapter-configuratie 0 resultaten geven: dan wil je
        weten of de content er überhaupt is, vóór je aan selectors
        gaat sleutelen. Zie adapter_helper.raw_fetch_debug().
        """

        employer = Source.query.get_or_404(
            id
        )


        logs = ChangeLog.query.filter_by(
            employer_id=id
        ).order_by(
            ChangeLog.created_at.desc()
        ).all()


        raw_fetch_result = raw_fetch_debug(employer)


        return render_template(
            "employer_detail.html",
            employer=employer,
            logs=logs,
            raw_fetch_result=raw_fetch_result
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
