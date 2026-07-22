FROM python:3.12-slim


WORKDIR /app


COPY requirements.txt .


# tzdata: zonder dit pakket heeft de python:3.12-slim-image geen
# tijdzonedatabase, en negeert glibc de TZ-omgevingsvariabele
# (docker-compose.yml zet TZ=Europe/Amsterdam) stilzwijgend -- alles
# zou dan intern op UTC draaien. Belangrijk voor de "controledagen"
# (Source.check_days, zie models.py/scheduler_service.py): zonder
# tzdata kan een controle rond middernacht op de verkeerde weekdag
# vallen.
#
# gosu: om na het (eventueel) aanpassen van UID/GID bij het opstarten
# alsnog veilig als een niet-root gebruiker te draaien (zie
# entrypoint.sh). usermod/groupmod (nodig om PUID/PGID op appuser toe
# te passen) zitten al in de basisimage, via het essentiële
# "passwd"-pakket -- geen aparte install nodig.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata gosu \
    && rm -rf /var/lib/apt/lists/*


RUN pip install --no-cache-dir \
    -r requirements.txt


# --- Optioneel: adapters/browser_listing.py (JavaScript-gerenderde
# vacaturesites, bv. via een headless Chromium-browser). Voegt
# honderden MB's toe aan de image, dus standaard uitgeschakeld.
# Ontkommentarieer onderstaande twee regels als je deze adapter wilt
# gebruiken (en verwijder de eerste regel hieronder als je 'm alsnog
# via requirements.txt wilt laten meelopen):
#
# COPY requirements-browser.txt .
# RUN pip install --no-cache-dir -r requirements-browser.txt \
#     && playwright install --with-deps chromium



COPY . .



RUN mkdir -p /app/data/backups \
    && useradd \
        --create-home \
        --uid 1000 \
        appuser \
    && chown -R appuser:appuser /app \
    && chmod +x entrypoint.sh



# Bewust GEEN "USER appuser" hier: de container start als root, zodat
# entrypoint.sh bij het opstarten (a) PUID/PGID kan toepassen op
# appuser en (b) het gemounte /app/data-volume kan chown'en naar die
# UID/GID -- root-only operaties. entrypoint.sh draagt de daadwerkelijke
# applicatie daarna over aan appuser via gosu; er draait nooit
# applicatiecode als root.



EXPOSE 5000



HEALTHCHECK \
    --interval=30s \
    --timeout=10s \
    --start-period=30s \
    --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/login')" || exit 1



ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "app.py"]
