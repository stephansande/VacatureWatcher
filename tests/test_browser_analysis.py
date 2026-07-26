"""
Tests voor browser_analysis.py.

Gemockt, geen echte Playwright/Chromium nodig -- consistent met de
rest van deze testsuite (snel, geen netwerkverkeer, draait overal).
Zie het commit-bericht / patch-notities voor het ECHTE end-to-end
bewijs: dit is in de ontwikkelomgeving ook één keer met een
daadwerkelijke headless Chromium tegen een lokale testserver gedraaid
(inclusief JS-vertraagde content en een cookiebanner), maar die run
hoort niet thuis in de permanente testsuite -- die moet blijven
werken zonder dat er een browser-binary geïnstalleerd staat.
"""

import pytest

import browser_analysis


class FakePlaywrightTimeoutError(Exception):
    """Staat in voor playwright.sync_api.TimeoutError in deze tests."""


class FakePage:

    def __init__(
        self,
        content_value="<html><body>gerenderd</body></html>",
        click_should_timeout=False,
        wait_selector_should_timeout=False,
    ):
        self.goto_calls = []
        self.click_calls = []
        self.wait_for_selector_calls = []
        self.wait_for_timeout_calls = []
        self._content = content_value
        self.click_should_timeout = click_should_timeout
        self.wait_selector_should_timeout = wait_selector_should_timeout

    def goto(self, url, wait_until=None, timeout=None):
        self.goto_calls.append((url, wait_until, timeout))

    def click(self, selector, timeout=None):
        self.click_calls.append((selector, timeout))
        if self.click_should_timeout:
            raise FakePlaywrightTimeoutError()

    def wait_for_selector(self, selector, timeout=None):
        self.wait_for_selector_calls.append((selector, timeout))
        if self.wait_selector_should_timeout:
            raise FakePlaywrightTimeoutError()

    def wait_for_timeout(self, ms):
        self.wait_for_timeout_calls.append(ms)

    def content(self):
        return self._content


class FakeBrowser:

    def __init__(self, page):
        self._page = page
        self.closed = False
        self.new_page_user_agent = None

    def new_page(self, user_agent=None):
        self.new_page_user_agent = user_agent
        return self._page

    def close(self):
        self.closed = True


class FakeChromium:

    def __init__(self, browser):
        self._browser = browser
        self.launch_kwargs = None

    def launch(self, headless=None, args=None):
        self.launch_kwargs = {"headless": headless, "args": args}
        return self._browser


class FakePlaywrightContext:

    def __init__(self, chromium):
        self.chromium = chromium


class FakeSyncPlaywright:
    """Staat in voor de `with sync_playwright() as playwright:`-contextmanager."""

    def __init__(self, chromium):
        self._chromium = chromium

    def __call__(self):
        return self

    def __enter__(self):
        return FakePlaywrightContext(self._chromium)

    def __exit__(self, *args):
        return False


def _patch_playwright(monkeypatch, page):
    """Vervangt browser_analysis._import_playwright() door een nep-versie."""

    browser = FakeBrowser(page)
    chromium = FakeChromium(browser)
    fake_sync_playwright = FakeSyncPlaywright(chromium)

    monkeypatch.setattr(
        browser_analysis,
        "_import_playwright",
        lambda: (fake_sync_playwright, FakePlaywrightTimeoutError),
    )

    return browser, chromium


# ---------------------------------------------------------------------------
# fetch_rendered_html() -- eigen browser-levenscyclus, één pagina
# ---------------------------------------------------------------------------

def test_fetch_rendered_html_geeft_content_terug_en_sluit_browser(monkeypatch):

    page = FakePage(content_value="<html>inhoud</html>")
    browser, chromium = _patch_playwright(monkeypatch, page)

    html = browser_analysis.fetch_rendered_html("https://example.nl/")

    assert html == "<html>inhoud</html>"
    assert browser.closed is True
    assert page.goto_calls == [("https://example.nl/", "networkidle", browser_analysis.NAVIGATION_TIMEOUT_MS)]


def test_fetch_rendered_html_gebruikt_realistische_user_agent(monkeypatch):

    page = FakePage()
    browser, chromium = _patch_playwright(monkeypatch, page)

    browser_analysis.fetch_rendered_html("https://example.nl/")

    assert browser.new_page_user_agent == browser_analysis.USER_AGENT
    assert "VacatureWatcher" not in browser_analysis.USER_AGENT  # zie scraper.py-fix


def test_fetch_rendered_html_sluit_browser_ook_bij_een_fout(monkeypatch):

    page = FakePage()

    def failing_goto(url, wait_until=None, timeout=None):
        raise RuntimeError("netwerkfout")

    page.goto = failing_goto

    browser, chromium = _patch_playwright(monkeypatch, page)

    with pytest.raises(RuntimeError):
        browser_analysis.fetch_rendered_html("https://example.nl/")

    assert browser.closed is True  # finally-block moet altijd sluiten


# ---------------------------------------------------------------------------
# render_page() -- wachtgedrag
# ---------------------------------------------------------------------------

def test_render_page_wacht_wait_ms_zonder_wait_selector(monkeypatch):

    page = FakePage()
    _patch_playwright(monkeypatch, page)

    browser_analysis.render_page(page, "https://example.nl/", wait_ms=1234)

    assert page.wait_for_timeout_calls == [1234]
    assert page.wait_for_selector_calls == []


def test_render_page_wacht_op_wait_selector_indien_opgegeven(monkeypatch):

    page = FakePage()
    _patch_playwright(monkeypatch, page)

    browser_analysis.render_page(page, "https://example.nl/", wait_selector=".vacature")

    assert page.wait_for_selector_calls == [(".vacature", browser_analysis.WAIT_SELECTOR_TIMEOUT_MS)]
    assert page.wait_for_timeout_calls == []  # wait_ms-tak wordt overgeslagen


def test_render_page_gaat_door_als_wait_selector_niet_verschijnt(monkeypatch):
    """
    Regressie: een niet-gevonden wait_selector mag de hele analyse niet
    laten crashen -- de aanroeper (analyze()/test_source()) moet dan
    gewoon 0 resultaten zien, met de content die er op dat moment wél
    is, in plaats van een onverwachte foutmelding.
    """

    page = FakePage(content_value="<html>gedeeltelijk geladen</html>", wait_selector_should_timeout=True)
    _patch_playwright(monkeypatch, page)

    html = browser_analysis.render_page(page, "https://example.nl/", wait_selector=".nooit-verschijnt")

    assert html == "<html>gedeeltelijk geladen</html>"


# ---------------------------------------------------------------------------
# render_page() -- cookiebanner
# ---------------------------------------------------------------------------

def test_render_page_klikt_consent_selector(monkeypatch):

    page = FakePage()
    _patch_playwright(monkeypatch, page)

    browser_analysis.render_page(page, "https://example.nl/", consent_selector="#accept")

    assert page.click_calls == [("#accept", browser_analysis.CONSENT_CLICK_TIMEOUT_MS)]
    # na een succesvolle klik hoort er een korte "settle"-wachttijd te zijn
    assert browser_analysis.CONSENT_SETTLE_MS in page.wait_for_timeout_calls


def test_render_page_gaat_door_als_geen_cookiebanner_aanwezig(monkeypatch):
    """Regressie: geen banner gevonden (timeout bij click) mag niet crashen."""

    page = FakePage(content_value="<html>ok</html>", click_should_timeout=True)
    _patch_playwright(monkeypatch, page)

    html = browser_analysis.render_page(page, "https://example.nl/", consent_selector="#accept-die-er-niet-is")

    assert html == "<html>ok</html>"


# ---------------------------------------------------------------------------
# Foutafhandeling
# ---------------------------------------------------------------------------

def test_browser_unavailable_error_propageert_correct(monkeypatch):

    def raise_unavailable():
        raise browser_analysis.BrowserUnavailableError("playwright niet geïnstalleerd")

    monkeypatch.setattr(browser_analysis, "_import_playwright", raise_unavailable)

    with pytest.raises(browser_analysis.BrowserUnavailableError):
        browser_analysis.fetch_rendered_html("https://example.nl/")

    with pytest.raises(browser_analysis.BrowserUnavailableError):
        browser_analysis.get_sync_playwright()
