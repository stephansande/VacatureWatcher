"""
Site Fingerprint cache.

Doel: onthoud per domein welke detectie-uitkomst eerder werkte, zodat
adapter_helper.analyze() niet bij elke aanroep opnieuw de zware
ancestor-heuristiek (_find_best_ancestor_signature) hoeft te draaien
voor een domein dat al eerder succesvol geanalyseerd is.

Dit is de "Detectie met geheugen"-laag van de Website Detective-aanpak
(HTML -> Analyse -> Detectie -> Adapter -> JSON). Los van de
Analyse-stap (die blijft signalen verzamelen zoals nu) beslist deze
module of die signalen daadwerkelijk opnieuw doorlopen moeten worden,
of dat een eerdere, verse uitkomst hergebruikt kan worden.

Gebruik (zie adapter_helper.analyze() voor de volledige integratie):

    cached = lookup(url)

    if cached and is_fresh(cached):
        # gebruik cached.adapter + cached.settings direct, sla de
        # zware heuristiek over
        ...
    else:
        # doe de volledige analyse zoals nu, en roep daarna save() aan
        # met de uitkomst
        save(url, adapter=..., settings_dict=..., confidence=...)

Ontwerpprincipe, in lijn met de rest van adapter_helper.py: dit is geen
onomkeerbare beslissing. Een verouderde fingerprint wordt niet
stilzwijgend weggegooid maar teruggegeven met is_fresh() == False, zodat
de aanroeper zelf kan kiezen (bv. "eerder gedetecteerd als X, mogelijk
verouderd -- opnieuw analyseren?" tonen in de UI, i.p.v. blind
vertrouwen of blind negeren).
"""

import json

from datetime import datetime, timedelta
from urllib.parse import urlparse

from database import db
from models import SiteFingerprint


FRESHNESS_DAYS = 30
# Na deze periode wordt een fingerprint als "verouderd" beschouwd en
# de aanroeper hoort opnieuw volledig te analyseren -- sites
# veranderen soms van structuur zonder dat iemand dat meldt. 30 dagen
# is een startpunt, geen harde wet; kan later per adapter-type
# verschillen (een jsonld_listing-site verandert zelden van
# aanpak, een html_listing-site met een custom theme wat vaker).

CONFIDENCE_JSONLD = 0.95
CONFIDENCE_MICRODATA = 0.9
CONFIDENCE_HTML_LISTING = 0.7
CONFIDENCE_GENERIC_LINKS = 0.35
CONFIDENCE_GREENHOUSE = 0.98
# Hoger dan CONFIDENCE_JSONLD: dit is geen structurele heuristiek maar
# een harde fingerprint-match (scriptbron of domein herkend als
# greenhouse.io) -- zie adapters/greenhouse.matches_fingerprint().
# Vaste scores per adapter-type, geen geleerd model -- bewust simpel
# gehouden. Zodra er platform-specifieke adapters bijkomen (Greenhouse
# e.d., zie stap 4 van de roadmap) verdienen die een eigen, hogere
# confidence op basis van een harde fingerprint-match i.p.v. een gok.


def domain_of(url):
    """Normaliseert een URL naar alleen het domein, als cache-sleutel."""

    parsed = urlparse(url)

    return parsed.netloc.lower().removeprefix("www.")


def lookup(url):
    """
    Geeft de opgeslagen SiteFingerprint voor het domein van deze URL
    terug, of None als er nog niets bekend is. Doet GEEN
    freshness-check -- gebruik is_fresh() apart, zodat de aanroeper
    zelf bepaalt wat te doen met een verouderde-maar-nog-informatieve
    match.
    """

    domain = domain_of(url)

    return SiteFingerprint.query.filter_by(domain=domain).first()


def is_fresh(fingerprint, max_age_days=FRESHNESS_DAYS):

    if fingerprint is None:
        return False

    age = datetime.utcnow() - fingerprint.last_verified

    return age < timedelta(days=max_age_days)


def save(url, adapter, settings_dict, confidence):
    """
    Slaat de fingerprint voor het domein van `url` op (of werkt 'm
    bij als er al één bestaat). `settings_dict` is de
    suggested_settings-dict zoals de Adapter Helper die nu ook al per
    kandidaat teruggeeft -- bewaard zodat een volgende analyse van
    hetzelfde domein die direct kan hergebruiken.

    Committeert meteen: dit wordt aangeroepen vanuit analyze(), dat
    zelf geen open transactie beheert.
    """

    domain = domain_of(url)

    fingerprint = SiteFingerprint.query.filter_by(domain=domain).first()

    if fingerprint is None:
        fingerprint = SiteFingerprint(domain=domain)
        db.session.add(fingerprint)

    fingerprint.adapter = adapter
    fingerprint.confidence = confidence
    fingerprint.settings = json.dumps(settings_dict) if settings_dict else None
    fingerprint.last_verified = datetime.utcnow()

    db.session.commit()

    return fingerprint


def confidence_for(recommendation):
    """
    Vaste confidence-score op basis van welke adapter de Adapter
    Helper aanraadt (result["recommendation"] uit analyze()).
    """

    return {
        "jsonld_listing": CONFIDENCE_JSONLD,
        "microdata_listing": CONFIDENCE_MICRODATA,
        "html_listing": CONFIDENCE_HTML_LISTING,
        "generic_links": CONFIDENCE_GENERIC_LINKS,
        "greenhouse": CONFIDENCE_GREENHOUSE,
    }.get(recommendation, 0.3)
