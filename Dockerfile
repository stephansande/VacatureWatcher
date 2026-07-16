FROM python:3.12-slim


WORKDIR /app


COPY requirements.txt .


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
    && chown -R appuser:appuser /app



USER appuser



EXPOSE 5000



HEALTHCHECK \
    --interval=30s \
    --timeout=10s \
    --start-period=30s \
    --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/login')" || exit 1



CMD ["python", "app.py"]
