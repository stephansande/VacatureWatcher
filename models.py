from datetime import datetime

from database import db

from flask_login import UserMixin
from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)



class Employer(db.Model):
    """
    Werkgever met een te controleren vacaturepagina
    """

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

    enabled = db.Column(
        db.Boolean,
        default=True
    )

    check_interval = db.Column(
        db.String(20),
        default="daily"
    )

    keywords = db.Column(
        db.Text,
        nullable=True
    )

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


    pages = db.relationship(
        "VacancyPage",
        backref="employer",
        lazy=True,
        cascade="all, delete"
    )


    vacancies = db.relationship(
        "Vacancy",
        backref="employer",
        lazy=True,
        cascade="all, delete"
    )


    changes = db.relationship(
        "ChangeLog",
        backref="employer",
        lazy=True,
        cascade="all, delete"
    )


    def __repr__(self):

        return f"<Employer {self.name}>"




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
            "employer.id"
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
            "employer.id"
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
            "employer.id"
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
```
