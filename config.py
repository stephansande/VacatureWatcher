import os

from dotenv import load_dotenv


load_dotenv()



class Config:


    APP_NAME = os.getenv(
        "APP_NAME",
        "VacatureWatcher"
    )


    SECRET_KEY = os.getenv(
        "SECRET_KEY",
        "development-key"
    )


    DATABASE_PATH = os.getenv(
        "DATABASE_PATH",
        "/app/data/vacaturewatcher.db"
    )


    SQLALCHEMY_DATABASE_URI = (
        "sqlite:///"
        + DATABASE_PATH
    )


    SQLALCHEMY_TRACK_MODIFICATIONS = False



    CHECK_INTERVAL = os.getenv(
        "CHECK_INTERVAL",
        "daily"
    )



    EMAIL_ENABLED = (
        os.getenv(
            "EMAIL_ENABLED",
            "false"
        ).lower()
        == "true"
    )



    EMAIL_SERVER = os.getenv(
        "SMTP_SERVER",
        ""
    )


    EMAIL_PORT = int(
        os.getenv(
            "SMTP_PORT",
            587
        )
    )


    EMAIL_USERNAME = os.getenv(
        "SMTP_USERNAME",
        ""
    )


    EMAIL_PASSWORD = os.getenv(
        "SMTP_PASSWORD",
        ""
    )


    EMAIL_FROM = os.getenv(
        "EMAIL_FROM",
        ""
    )


    EMAIL_TO = os.getenv(
        "EMAIL_TO",
        ""
    )



    TELEGRAM_ENABLED = (
        os.getenv(
            "TELEGRAM_ENABLED",
            "false"
        ).lower()
        == "true"
    )


    TELEGRAM_TOKEN = os.getenv(
        "TELEGRAM_TOKEN",
        ""
    )


    TELEGRAM_CHAT_ID = os.getenv(
        "TELEGRAM_CHAT_ID",
        ""
    )


    # CSO Vacature-API (WerkenvoorNederland.nl e.a.)
    # Account aanvragen via helpdesk@werkenvoornederland.nl
    # zie https://docs.api.cso20.net/

    CSO_USERNAME = os.getenv(
        "CSO_USERNAME",
        ""
    )

    CSO_PASSWORD = os.getenv(
        "CSO_PASSWORD",
        ""
    )
