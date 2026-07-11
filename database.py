import os

from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()



def init_database(app):
    """
    Initialiseert de database.
    Maakt de SQLite database automatisch aan.
    """

    database_file = (
        app.config["DATABASE_PATH"]
    )

    database_directory = os.path.dirname(
        database_file
    )


    if database_directory:

        os.makedirs(
            database_directory,
            exist_ok=True
        )


    db.init_app(
        app
    )


    with app.app_context():

        db.create_all()

        create_admin_user()




def create_admin_user():

    """
    Maakt automatisch de eerste admin gebruiker aan
    op basis van de .env instellingen.
    """

    from models import User


    username = os.getenv(
        "ADMIN_USERNAME"
    )

    password = os.getenv(
        "ADMIN_PASSWORD"
    )


    # Geen admin configuratie aanwezig:
    # niets doen

    if not username or not password:

        return



    existing_user = User.query.filter_by(
        username=username
    ).first()



    # Gebruiker bestaat al

    if existing_user:

        return



    user = User(
        username=username
    )


    user.set_password(
        password
    )


    db.session.add(
        user
    )


    db.session.commit()


    print(
        f"Admin gebruiker '{username}' aangemaakt"
    )
