"""
Tests voor de weekdag-selectie uit stap 5:
  - Source.check_days_list (getter/setter) en Source.runs_today() in models.py
  - services.scheduler_service._should_check(), die check_days EN
    check_interval samen laat beslissen

Geen echte databaseverbinding nodig: een Source() aanmaken zonder 'm
aan de sessie toe te voegen/te committen raakt de database niet, dus
deze tests draaien net zo snel en geïsoleerd als test_greenhouse_adapter.py.
"""

import pytest

from models import Source, ALL_WEEKDAYS
from services.scheduler_service import _should_check


# ---------------------------------------------------------------------------
# Source.check_days_list / runs_today()
# ---------------------------------------------------------------------------

def test_check_days_list_default_is_alle_dagen_voor_nieuwe_bron():
    """
    Een net aangemaakte Source() heeft nog geen expliciete check_days
    (het db-default wordt pas bij een echte INSERT toegepast) -- de
    property moet dan ALSNOG "alle dagen" teruggeven, zodat code die
    hierop leunt (bv. runs_today) nooit per ongeluk "nooit" oplevert
    voor een bron waarvoor nog niets is ingesteld.
    """

    source = Source(name="Test", url="https://example.com")

    assert source.check_days_list == list(ALL_WEEKDAYS)


def test_check_days_list_getter_parsed_komma_gescheiden_string():

    source = Source(name="Test", url="https://example.com", check_days="mon,wed,fri")

    assert source.check_days_list == ["mon", "wed", "fri"]


def test_check_days_list_setter_schrijft_geldige_dagen_in_vaste_volgorde():

    source = Source(name="Test", url="https://example.com")

    source.check_days_list = ["fri", "mon", "wed"]  # bewust door elkaar

    assert source.check_days == "mon,wed,fri"


def test_check_days_list_setter_negeert_onbekende_waarden():

    source = Source(name="Test", url="https://example.com")

    source.check_days_list = ["mon", "not-a-day", "fri"]

    assert source.check_days == "mon,fri"


def test_check_days_list_setter_lege_selectie_valt_terug_op_alle_dagen():
    """
    Regressie: niets aanvinken in het formulier mag een bron niet
    stilzwijgend voor altijd stilleggen.
    """

    source = Source(name="Test", url="https://example.com")

    source.check_days_list = []

    assert source.check_days == ""
    assert source.check_days_list == list(ALL_WEEKDAYS)


@pytest.mark.parametrize("today, verwacht", [
    ("mon", True),
    ("wed", True),
    ("fri", True),
    ("tue", False),
    ("sun", False),
])
def test_runs_today_met_expliciete_dag(today, verwacht):

    source = Source(name="Test", url="https://example.com", check_days="mon,wed,fri")

    assert source.runs_today(today=today) is verwacht


# ---------------------------------------------------------------------------
# services.scheduler_service._should_check()
# ---------------------------------------------------------------------------

def _source(check_days="mon,tue,wed,thu,fri,sat,sun", check_interval="daily"):
    return Source(
        name="Test",
        url="https://example.com",
        check_days=check_days,
        check_interval=check_interval,
    )


def test_should_check_daily_op_toegestane_dag():

    source = _source(check_days="mon,wed,fri", check_interval="daily")

    assert _should_check(source, today="wed") is True


def test_should_check_daily_op_niet_toegestane_dag():

    source = _source(check_days="mon,wed,fri", check_interval="daily")

    assert _should_check(source, today="tue") is False


def test_should_check_weekly_op_maandag_binnen_toegestane_dagen():

    source = _source(check_days="mon,tue,wed,thu,fri,sat,sun", check_interval="weekly")

    assert _should_check(source, today="mon") is True


def test_should_check_weekly_op_andere_dag_dan_maandag():

    source = _source(check_days="mon,tue,wed,thu,fri,sat,sun", check_interval="weekly")

    assert _should_check(source, today="tue") is False


def test_should_check_weekly_maar_maandag_niet_in_check_days():
    """
    De caveat uit de docstring van _should_check(): check_interval
    "weekly" betekent hard "op maandag", ongeacht check_days. Vinkt de
    gebruiker maandag niet aan, dan draait de bron dus nooit -- dat is
    hier bewust vastgelegd als verwacht gedrag (en toegelicht in de UI),
    niet als een bug.
    """

    source = _source(check_days="tue,wed", check_interval="weekly")

    assert _should_check(source, today="mon") is False
    assert _should_check(source, today="tue") is False


def test_should_check_disabled_draait_nooit():

    source = _source(check_days="mon,tue,wed,thu,fri,sat,sun", check_interval="disabled")

    assert _should_check(source, today="mon") is False


def test_should_check_check_days_wint_altijd_ongeacht_interval():

    source = _source(check_days="sat,sun", check_interval="daily")

    assert _should_check(source, today="mon") is False
    assert _should_check(source, today="sat") is True
