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


    db.init_app(app)

    with app.app_context():
        db.create_all()