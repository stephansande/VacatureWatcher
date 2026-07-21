from datetime import datetime

from database import db

from flask_login import UserMixin
from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)


ALL_WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
# Python's datetime.weekday() geeft 0=maandag..6=zondag -- deze lijst
# staat in dezelfde volgorde, zodat ALL_WEEKDAYS[datetime.now().weekday()]
# altijd de juiste afkorting oplevert. Gedeeld door Source.runs_today()
# hieronder en services/scheduler_service.py.


class Source(db.Model):
    """
    Een bron die periodiek gecontroleerd wordt op vacatures --
    dit kan een individuele werkgever zijn (type="employer") of een
    vacaturesite/jobboard (type="jobboard").
    """

    __tablename__ = "source"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    name = db.Column(
        db.String(200),
        nullable=False
    )

    url = db.Column(
        db.String(500),
        nullable=False
    )

    selector = db.Column(
        db.String(300),
        nullable=True
    )
    # legacy v1-veld, wordt niet meer gebruikt door de v2-adapters
    # (vervangen door "settings" hieronder) -- blijft bestaan zodat
    # oude data niet verloren gaat

    enabled = db.Column(
        db.Boolean,
        default=True
    )

    check_interval = db.Column(
        db.String(20),
        default="daily"
    )

    check_days = db.Column(
        db.String(30),
        default="mon,tue,wed,thu,fri,sat,sun",
        nullable=False
    )
    # comma-gescheiden weekdag-afkortingen waarop deze bron gecontroleerd
    # MAG worden (naast check_interval hierboven, dat bepaalt HOE VAAK
    # op zo'n toegestane dag -- "dagelijks" of "wekelijks op maandag").
    # Default = alle dagen, zodat bestaande bronnen (en installaties
    # die nog moeten migreren) ongewijzigd blijven draaien. Lees/schrijf
    # dit via check_days_list hieronder, niet rechtstreeks als string.

    keywords = db.Column(
        db.Text,
        nullable=True
    )
    # legacy INCLUDE-filter (komma-gescheiden). Voor nieuwe jobboard-
    # sources kun je include/exclude-keywords ook (of in plaats
    # daarvan) in "settings" opgeven -- zie apply_keyword_filter()
    # in adapters/base.py voor hoe beide samenkomen.

    type = db.Column(
        db.String(20),
        default="employer",
        nullable=False
    )
    # "employer" (v1-gedrag, een enkele werkgeverspagina)
    # "jobboard" (een vacaturesite, met een specifieke adapter)

    adapter = db.Column(
        db.String(50),
        default="generic_links",
        nullable=False
    )
    # zie adapters/registry.py: "generic_links" | "html_listing" |
    # "jsonld_listing" | "cso_api"
    # Blijft een eigen kolom (i.p.v. in settings) omdat de applicatie
    # hierop dispatcht/filtert -- dat hoort in een doorzoekbare kolom,
    # niet verstopt in een JSON-blob.

    settings = db.Column(
        db.Text,
        nullable=True
    )
    # ÉÉN generieke JSON-kolom met alle adapter-specifieke parameters:
    # CSS-selectors, categorieën, paginering, CSO-filtercriteria,
    # include/exclude-keywords, url-templates, etc. -- zie de
    # docstring bovenin het betreffende adapters/*.py bestand voor de
    # exacte vorm per adapter. Zo hoeft een nieuwe adapter-optie nooit
    # meer een databasemigratie te vereisen.

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    last_check = db.Column(
        db.DateTime,
        nullable=True
    )

    last_change = db.Column(
        db.DateTime,
        nullable=True
    )

    last_success = db.Column(
        db.DateTime,
        nullable=True
    )
    # tijdstip van de laatste GESLAAGDE controle (in tegenstelling tot
    # last_check hierboven, dat ook bijgewerkt wordt bij een mislukte
    # controle)

    last_error = db.Column(
        db.Text,
        nullable=True
    )
    # foutmelding van de laatste mislukte controle, of NULL als de
    # laatste controle geslaagd is

    last_new_count = db.Column(
        db.Integer,
        nullable=True
    )
    # aantal nieuwe vacatures gevonden tijdens de laatste geslaagde
    # controle


    pages = db.relationship(
        "VacancyPage",
        backref="source",
        lazy=True,
        cascade="all, delete"
    )


    vacancies = db.relationship(
        "Vacancy",
        backref="source",
        lazy=True,
        cascade="all, delete"
    )


    changes = db.relationship(
        "ChangeLog",
        backref="source",
        lazy=True,
        cascade="all, delete"
    )


    @property
    def check_days_list(self):
        """Geeft check_days als Python-lijst, bv. ['mon', 'wed', 'fri']."""

        if not self.check_days:
            return list(ALL_WEEKDAYS)

        return [
            day.strip().lower()
            for day in self.check_days.split(",")
            if day.strip()
        ]

    @check_days_list.setter
    def check_days_list(self, days):
        """
        Zet check_days vanuit een Python-lijst (bv. rechtstreeks vanuit
        de checkboxes van het bron-formulier). Onbekende/lege waarden
        worden genegeerd; een lege selectie wordt opgeslagen als lege
        string, wat check_days_list weer als "alle dagen" interpreteert
        (zie getter hierboven) -- zo kan een bron nooit per ongeluk
        stilletjes helemaal nooit meer draaien door een leeg formulier.
        """

        valid = [day for day in ALL_WEEKDAYS if day in (days or [])]

        self.check_days = ",".join(valid)

    def runs_today(self, today=None):
        """
        True als deze bron vandaag gecontroleerd mag worden, op basis
        van check_days. `today` is optioneel een weekday-afkorting
        ('mon'..'sun') zodat dit testbaar is zonder de systeemklok te
        hoeven mocken -- zonder argument wordt de systeemdatum gebruikt.
        """

        if today is None:
            today = ALL_WEEKDAYS[datetime.now().weekday()]

        return today in self.check_days_list

    def __repr__(self):

        return f"<Source {self.name}>"




class SiteFingerprint(db.Model):
    """Zie site_fingerprint.py voor de logica hieromheen."""

    __tablename__ = "site_fingerprint"

    id = db.Column(db.Integer, primary_key=True)
    domain = db.Column(db.String(200), unique=True, nullable=False, index=True)
    adapter = db.Column(db.String(50), nullable=False)
    confidence = db.Column(db.Float, default=0.5)
    settings = db.Column(db.Text, nullable=True)
    last_verified = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<SiteFingerprint {self.domain} -> {self.adapter}>"


class VacancyPage(db.Model):
    """
    Bewaart volledige snapshots van vacaturepagina's.
    Wordt gebruikt voor vergelijking.
    """

    id = db.Column(
        db.Integer,
        primary_key=True
    )


    employer_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "source.id"
        ),
        nullable=False
    )


    content_hash = db.Column(
        db.String(128),
        nullable=False
    )


    content = db.Column(
        db.Text,
        nullable=False
    )


    checked_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )




class ChangeLog(db.Model):
    """
    Historie van wijzigingen.
    """

    id = db.Column(
        db.Integer,
        primary_key=True
    )


    employer_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "source.id"
        ),
        nullable=False
    )


    change_type = db.Column(
        db.String(50),
        default="changed"
    )


    message = db.Column(
        db.Text
    )


    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )




class Vacancy(db.Model):
    """
    Individuele vacaturehistorie.

    Hiermee kunnen we later zien:
    - wanneer een vacature verscheen
    - wanneer deze verdween
    - hoe lang deze online stond
    """

    id = db.Column(
        db.Integer,
        primary_key=True
    )


    employer_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "source.id"
        ),
        nullable=False
    )


    title = db.Column(
        db.String(300),
        nullable=False
    )


    url = db.Column(
        db.String(500),
        nullable=True
    )


    content = db.Column(
        db.Text,
        nullable=True
    )


    active = db.Column(
        db.Boolean,
        default=True
    )


    first_seen = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )


    last_seen = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )


    def __repr__(self):

        return f"<Vacancy {self.title}>"




class Setting(db.Model):
    """
    Algemene applicatie instellingen
    """

    id = db.Column(
        db.Integer,
        primary_key=True
    )


    key = db.Column(
        db.String(100),
        unique=True,
        nullable=False
    )


    value = db.Column(
        db.Text,
        nullable=True
    )


    def __repr__(self):

        return f"<Setting {self.key}>"




class User(UserMixin, db.Model):
    """
    Gebruiker voor toegang tot de webinterface.
    Wachtwoorden worden alleen als hash opgeslagen.
    """

    id = db.Column(
        db.Integer,
        primary_key=True
    )


    username = db.Column(
        db.String(80),
        unique=True,
        nullable=False
    )


    password_hash = db.Column(
        db.String(255),
        nullable=False
    )


    def set_password(
        self,
        password
    ):

        self.password_hash = generate_password_hash(
            password
        )


    def check_password(
        self,
        password
    ):

        return check_password_hash(
            self.password_hash,
            password
        )


    def __repr__(self):

        return f"<User {self.username}>"
