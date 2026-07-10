import smtplib

from email.mime.text import MIMEText

import requests

from config import Config



def send_notification(
    title,
    message
):
    """
    Centrale notificatiefunctie.

    Stuurt meldingen naar de
    ingestelde kanalen.
    """

    print(
        "\n============================"
    )

    print(
        title
    )

    print(
        message
    )

    print(
        "============================\n"
    )


    # E-mail

    if Config.EMAIL_ENABLED:

        try:

            send_email(
                subject=title,
                message=message
            )


        except Exception as error:

            print(
                f"E-mail melding mislukt: {error}"
            )



    # Telegram

    if Config.TELEGRAM_ENABLED:

        try:

            send_telegram(
                message=
                title
                +
                "\n\n"
                +
                message
            )


        except Exception as error:

            print(
                f"Telegram melding mislukt: {error}"
            )





def send_email(
    subject,
    message
):
    """
    Verstuur een e-mailmelding.
    """

    if not Config.EMAIL_SERVER:

        print(
            "Geen SMTP server ingesteld"
        )

        return



    mail = MIMEText(
        message,
        "plain",
        "utf-8"
    )


    mail["Subject"] = subject

    mail["From"] = (
        Config.EMAIL_FROM
    )

    mail["To"] = (
        Config.EMAIL_TO
    )



    with smtplib.SMTP(
        Config.EMAIL_SERVER,
        Config.EMAIL_PORT
    ) as smtp:


        smtp.starttls()



        smtp.login(
            Config.EMAIL_USERNAME,
            Config.EMAIL_PASSWORD
        )



        smtp.send_message(
            mail
        )





def send_telegram(
    message
):
    """
    Verstuur een Telegram bericht.
    """

    if not Config.TELEGRAM_TOKEN:

        print(
            "Geen Telegram token ingesteld"
        )

        return



    if not Config.TELEGRAM_CHAT_ID:

        print(
            "Geen Telegram chat ID ingesteld"
        )

        return



    url = (
        "https://api.telegram.org/"
        f"bot{Config.TELEGRAM_TOKEN}"
        "/sendMessage"
    )



    response = requests.post(
        url,
        json={
            "chat_id":
                Config.TELEGRAM_CHAT_ID,

            "text":
                message
        },

        timeout=10
    )



    response.raise_for_status()