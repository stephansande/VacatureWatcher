FROM python:3.12-slim


WORKDIR /app


# Vaste, voorspelbare locatie voor de Chromium-browser die Playwright
# straks installeert -- BINNEN /app, zodat de "chown -R appuser:appuser
# /app"-stap verderop 'm ook meepakt. Zonder dit zou "playwright
# install" (draait als root tijdens het bouwen) de browser wegzetten
# in /root/.cache/ms-playwright, een map die appuser tijdens het
# draaien niet kan lezen -- Playwright zou dan pas bij de eerste
# ECHTE poging tot renderen falen, niet bij het bouwen van de image.
ENV PLAYWRIGHT_BROWSERS_PATH=/app/.playwright-browsers


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


# Playwright + Chromium: sinds "Analyseren" zelf ook een echte
# (headless) browser gebruikt (zie browser_analysis.py) is dit geen
# optionele dependency meer, maar standaard nodig -- niet alleen voor
# adapters/browser_listing.py. Dit voegt aanzienlijk toe aan de
# image-grootte (een volledige Chromium-binary, honderden MB's) en de
# bouwtijd -- een bewuste afweging: zonder een echte browser tijdens
# analyse zou VacatureWatcher JavaScript-afhankelijke vacaturesites
# (bv. Werken bij Wassenaar) stelselmatig verkeerd beoordelen.
# --with-deps installeert ook de systeembibliotheken die Chromium
# nodig heeft (via apt) -- vandaar dat dit als root moet draaien,
# vóór de "useradd"/rechten-stap verderop.
RUN playwright install --with-deps chromium



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
