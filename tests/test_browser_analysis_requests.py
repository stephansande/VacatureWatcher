"""
Tests voor de netwerkverkeer-opvang in browser_analysis.py
(render_page_capturing_requests / _maybe_capture_response /
_looks_like_job_list / _summarize_json_body).

Gemockt met nep-response/request-objecten -- geen echte
Playwright/Chromium nodig, consistent met test_browser_analysis.py.
Zie de patch-notities voor het ECHTE end-to-end bewijs: dit is ook
één keer met een daadwerkelijke headless Chromium tegen een lokale
testserver gedraaid (met een JSON-vacature-API én een analytics-achtig
decoy-endpoint), maar die run hoort niet thuis in de permanente
testsuite.
"""

import browser_analysis


class FakeRequest:

    def __init__(self, resource_type="fetch", method="GET"):
        self.resource_type = resource_type
        self.method = method


class FakeResponse:

    def __init__(self, url, resource_type="fetch", method="GET", status=200,
                 content_type="application/json", text=""):
        self.url = url
        self.status = status
        self.request = FakeRequest(resource_type=resource_type, method=method)
        self._text = text
        self._headers = {"content-type": content_type} if content_type else {}

    @property
    def headers(self):
        return self._headers

    def text(self):
        return self._text


# ---------------------------------------------------------------------------
# _maybe_capture_response -- filtering
# ---------------------------------------------------------------------------

def test_capture_negeert_niet_xhr_fetch_resource_types():

    for resource_type in ["document", "stylesheet", "image", "font", "script", "media"]:
        response = FakeResponse("https://example.nl/style.css", resource_type=resource_type)
        assert browser_analysis._maybe_capture_response(response) is None


def test_capture_negeert_bekende_analytics_domeinen():

    response = FakeResponse(
        "https://www.google-analytics.com/g/collect",
        resource_type="fetch",
        content_type="application/json",
        text="{}",
    )

    assert browser_analysis._maybe_capture_response(response) is None


def test_capture_pakt_json_xhr_respons_op():

    body_text = '[{"title": "Data engineer", "location": "Den Haag"}]'

    response = FakeResponse(
        "https://example.nl/api/vacatures",
        resource_type="xhr",
        content_type="application/json; charset=utf-8",
        text=body_text,
    )

    entry = browser_analysis._maybe_capture_response(response)

    assert entry is not None
    assert entry["url"] == "https://example.nl/api/vacatures"
    assert entry["method"] == "GET"
    assert entry["status"] == 200
    assert entry["is_json"] is True
    assert entry["looks_like_job_list"] is True
    assert "title" in entry["summary"]
    assert entry["items_path_guess"] == ""  # top-level array


def test_capture_bepaalt_items_path_guess_voor_wrapper_object():

    body_text = '{"results": [{"functie": "Beleidsmedewerker"}], "total": 1}'

    response = FakeResponse(
        "https://example.nl/api/vacatures",
        resource_type="xhr",
        content_type="application/json",
        text=body_text,
    )

    entry = browser_analysis._maybe_capture_response(response)

    assert entry["items_path_guess"] == "results"


def test_capture_bewaart_geen_headers_of_cookies():
    """
    Expliciete regressie: het resultaat mag NOOIT request-headers,
    response-headers (buiten content-type), of cookies bevatten -- dit
    kan uiteindelijk op een webpagina belanden.
    """

    response = FakeResponse(
        "https://example.nl/api/vacatures",
        resource_type="fetch",
        content_type="application/json",
        text="[]",
    )

    entry = browser_analysis._maybe_capture_response(response)

    assert set(entry.keys()) == {
        "url", "method", "status", "content_type",
        "is_json", "looks_like_job_list", "summary", "body_preview",
        "items_path_guess",
    }
    assert "cookie" not in str(entry).lower()
    assert "authorization" not in str(entry).lower()


def test_capture_niet_json_respons_heeft_geen_body(monkeypatch):

    response = FakeResponse(
        "https://example.nl/vacatures.html",
        resource_type="fetch",
        content_type="text/html",
        text="<html></html>",
    )

    entry = browser_analysis._maybe_capture_response(response)

    assert entry is not None
    assert entry["is_json"] is False
    assert entry["body_preview"] is None


def test_capture_te_grote_json_respons_wordt_niet_geparsed(monkeypatch):

    monkeypatch.setattr(browser_analysis, "MAX_BODY_CHARS", 10)

    response = FakeResponse(
        "https://example.nl/api/groot",
        resource_type="fetch",
        content_type="application/json",
        text='[{"title": "veel te lange respons voor de test-limiet"}]',
    )

    entry = browser_analysis._maybe_capture_response(response)

    assert entry["body_preview"] is None
    assert "te groot" in entry["summary"]


def test_capture_ongeldige_json_crasht_niet():

    response = FakeResponse(
        "https://example.nl/api/kapot",
        resource_type="fetch",
        content_type="application/json",
        text="dit is geen geldige JSON {{{",
    )

    entry = browser_analysis._maybe_capture_response(response)

    assert entry is not None
    assert entry["body_preview"] is None
    assert entry["looks_like_job_list"] is False


# ---------------------------------------------------------------------------
# _looks_like_job_list
# ---------------------------------------------------------------------------

def test_looks_like_job_list_array_met_titel_veld():

    body = [{"title": "Data engineer"}, {"title": "Projectleider"}]

    assert browser_analysis._looks_like_job_list(body) is True


def test_looks_like_job_list_wrapper_object_met_array():

    body = {"results": [{"functie": "Beleidsmedewerker"}], "total": 1}

    assert browser_analysis._looks_like_job_list(body) is True


def test_looks_like_job_list_negatief_voor_onherkenbare_velden():

    body = [{"foo": "bar"}, {"foo": "baz"}]

    assert browser_analysis._looks_like_job_list(body) is False


def test_looks_like_job_list_negatief_voor_leeg_of_geen_lijst():

    assert browser_analysis._looks_like_job_list({}) is False
    assert browser_analysis._looks_like_job_list([]) is False
    assert browser_analysis._looks_like_job_list("gewoon tekst") is False
    assert browser_analysis._looks_like_job_list(None) is False


# ---------------------------------------------------------------------------
# render_page_capturing_requests -- integratie met een nep-pagina
# ---------------------------------------------------------------------------

class FakePlaywrightTimeoutError(Exception):
    pass


class FakePage:
    """Minimale nep-Playwright-pagina die zelf de response-callback aanroept."""

    def __init__(self, responses_to_fire, content_value="<html></html>"):
        self._responses_to_fire = responses_to_fire
        self._content = content_value
        self._response_handler = None
        self.goto_calls = []

    def goto(self, url, wait_until=None, timeout=None):
        self.goto_calls.append(url)
        # simuleer dat de pagina tijdens het laden een aantal responses vuurt
        for response in self._responses_to_fire:
            if self._response_handler:
                self._response_handler(response)

    def on(self, event, handler):
        if event == "response":
            self._response_handler = handler

    def remove_listener(self, event, handler):
        if event == "response":
            self._response_handler = None

    def click(self, *a, **kw):
        raise FakePlaywrightTimeoutError()

    def wait_for_selector(self, *a, **kw):
        raise FakePlaywrightTimeoutError()

    def wait_for_timeout(self, ms):
        pass

    def content(self):
        return self._content


def test_render_page_capturing_requests_geeft_html_en_kandidaten_terug(monkeypatch):

    monkeypatch.setattr(
        browser_analysis,
        "_import_playwright",
        lambda: (None, FakePlaywrightTimeoutError),
    )

    job_response = FakeResponse(
        "https://example.nl/api/vacatures",
        resource_type="fetch",
        content_type="application/json",
        text='[{"title": "Data engineer"}]',
    )
    noise_response = FakeResponse(
        "https://www.google-analytics.com/collect",
        resource_type="fetch",
        content_type="application/json",
        text="{}",
    )

    page = FakePage([noise_response, job_response], content_value="<html>klaar</html>")

    html, discovered = browser_analysis.render_page_capturing_requests(page, "https://example.nl/")

    assert html == "<html>klaar</html>"
    assert len(discovered) == 1  # de analytics-noise is gefilterd
    assert discovered[0]["url"] == "https://example.nl/api/vacatures"


def test_render_page_capturing_requests_respecteert_max_requests(monkeypatch):

    monkeypatch.setattr(
        browser_analysis,
        "_import_playwright",
        lambda: (None, FakePlaywrightTimeoutError),
    )

    responses = [
        FakeResponse(f"https://example.nl/api/endpoint-{i}", resource_type="fetch",
                     content_type="application/json", text="{}")
        for i in range(5)
    ]

    page = FakePage(responses)

    html, discovered = browser_analysis.render_page_capturing_requests(
        page, "https://example.nl/", max_requests=2
    )

    assert len(discovered) == 2


def test_render_page_capturing_requests_sorteert_job_list_kandidaten_eerst(monkeypatch):

    monkeypatch.setattr(
        browser_analysis,
        "_import_playwright",
        lambda: (None, FakePlaywrightTimeoutError),
    )

    other_response = FakeResponse(
        "https://example.nl/api/config",
        resource_type="fetch",
        content_type="application/json",
        text='{"theme": "blauw"}',
    )
    job_response = FakeResponse(
        "https://example.nl/api/vacatures",
        resource_type="fetch",
        content_type="application/json",
        text='[{"title": "Data engineer"}]',
    )

    # bewust de vacature-respons ALS TWEEDE laten binnenkomen
    page = FakePage([other_response, job_response])

    html, discovered = browser_analysis.render_page_capturing_requests(page, "https://example.nl/")

    assert discovered[0]["url"] == "https://example.nl/api/vacatures"
    assert discovered[0]["looks_like_job_list"] is True


# ---------------------------------------------------------------------------
# _summarize_json_body
# ---------------------------------------------------------------------------

def test_summarize_json_body_array_van_objecten():

    summary = browser_analysis._summarize_json_body([{"title": "x", "location": "y"}])

    assert "1 object" in summary
    assert "title" in summary


def test_summarize_json_body_object():

    summary = browser_analysis._summarize_json_body({"total": 3, "results": []})

    assert "Object met velden" in summary
    assert "total" in summary
