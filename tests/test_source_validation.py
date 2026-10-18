"""
Tests voor de automatische validator vóór opslaan (stap 3 van de
roadmap):

- adapters/registry.validate_settings() -- de dunne, generieke laag
  die per-adapter validate_settings()-functies aanroept.
- app.py's _validate_settings() (structureel, JSON + adapter-check)
  en _maybe_run_live_validation() (live fetch()+parse() via
  diagnostics.test_source(), met de "always"/"opt_in"/"skip"-policy
  uit elke adapter se CAPABILITIES).

Geen Flask-testclient/database hier nodig: beide functies in app.py
nemen hun input als expliciete parameters (geen `request`-object),
dus rechtstreeks aanroepbaar/mockbaar, net zoals strategy_selector._classify()
al puur op een signals-dict werkt.
"""

import json

import pytest
from unittest.mock import patch

import app as app_module
from adapters import registry as adapter_registry
from adapters.base import AdapterError


# ---------------------------------------------------------------------------
# adapters/registry.validate_settings()
# ---------------------------------------------------------------------------

def test_registry_validate_settings_zonder_adapter_implementatie_geeft_none():
    """generic_links definieert geen eigen validate_settings() -- dat
    moet stilzwijgend als geldig gelden, niet crashen."""

    assert adapter_registry.validate_settings("generic_links", {}) is None


def test_registry_validate_settings_delegeert_naar_adapter():

    error = adapter_registry.validate_settings("html_listing", {})

    assert error is not None
    assert "selectors.item" in error


def test_registry_validate_settings_onbekende_adapter_geeft_adaptererror():

    with pytest.raises(AdapterError, match="Onbekende adapter"):
        adapter_registry.validate_settings("bestaat_niet", {})


# ---------------------------------------------------------------------------
# Per-adapter validate_settings() -- structurele regels
# ---------------------------------------------------------------------------

def test_html_listing_validate_settings_zonder_item_selector():

    error = adapter_registry.validate_settings("html_listing", {"selectors": {"title": "a"}})

    assert "selectors.item" in error


def test_html_listing_validate_settings_zonder_title_of_link():

    error = adapter_registry.validate_settings(
        "html_listing", {"selectors": {"item": ".vacature"}}
    )

    assert "title" in error and "link" in error


def test_html_listing_validate_settings_compleet_geeft_none():

    error = adapter_registry.validate_settings(
        "html_listing", {"selectors": {"item": ".vacature", "title": "a"}}
    )

    assert error is None


def test_browser_listing_validate_settings_default_parse_as_hergebruikt_html_listing_regel():

    error = adapter_registry.validate_settings("browser_listing", {})

    assert "selectors.item" in error


def test_browser_listing_validate_settings_parse_as_jsonld_heeft_geen_selectors_nodig():

    error = adapter_registry.validate_settings(
        "browser_listing", {"parse_as": "jsonld_listing"}
    )

    assert error is None


def test_browser_listing_validate_settings_onbekende_parse_as():

    error = adapter_registry.validate_settings(
        "browser_listing", {"parse_as": "onzin"}
    )

    assert "parse_as" in error


def test_discovered_api_validate_settings_zonder_endpoint_url():

    error = adapter_registry.validate_settings("discovered_api", {})

    assert "endpoint_url" in error


def test_discovered_api_validate_settings_leeg_field_map_is_structureel_geldig():
    """
    Een leeg field_map (het resultaat van "Gebruik deze API" vóórdat de
    gebruiker 'm invult) is bewust GEEN structurele fout -- dat vangt
    de live-validatie (test_source()), zie de toelichting in
    adapters/discovered_api.validate_settings().
    """

    error = adapter_registry.validate_settings(
        "discovered_api",
        {"endpoint_url": "https://voorbeeld.nl/api", "field_map": {"title": "", "url": ""}},
    )

    assert error is None


def test_embedded_json_validate_settings_zonder_items_path():

    error = adapter_registry.validate_settings("embedded_json", {})

    assert "items_path" in error


def test_embedded_json_validate_settings_items_path_als_string():

    error = adapter_registry.validate_settings(
        "embedded_json", {"items_path": "props.pageProps.vacatures"}
    )

    assert "lijst van sleutels" in error


def test_embedded_json_validate_settings_geldig():

    error = adapter_registry.validate_settings(
        "embedded_json", {"items_path": ["props", "pageProps", "vacatures"]}
    )

    assert error is None


def test_greenhouse_validate_settings_zonder_token_en_niet_greenhouse_url():

    error = adapter_registry.validate_settings(
        "greenhouse", {}, url="https://werkenbij.voorbeeld.nl/vacatures"
    )

    assert "board_token" in error


def test_greenhouse_validate_settings_token_afgeleid_uit_url():

    error = adapter_registry.validate_settings(
        "greenhouse", {}, url="https://boards.greenhouse.io/acme"
    )

    assert error is None


def test_greenhouse_validate_settings_expliciete_token():

    error = adapter_registry.validate_settings(
        "greenhouse",
        {"board_token": "acme"},
        url="https://werkenbij.voorbeeld.nl",
    )

    assert error is None


def test_jsonld_listing_validate_settings_mode_detail_zonder_link_selector():

    error = adapter_registry.validate_settings("jsonld_listing", {"mode": "detail"})

    assert "link_selector" in error


def test_jsonld_listing_validate_settings_mode_listing_heeft_geen_link_selector_nodig():

    assert adapter_registry.validate_settings("jsonld_listing", {}) is None


def test_microdata_listing_validate_settings_mode_detail_zonder_link_selector():

    error = adapter_registry.validate_settings("microdata_listing", {"mode": "detail"})

    assert "link_selector" in error


def test_cso_api_validate_settings_heeft_geen_verplichte_settings():
    """cso_api's credentials komen uit de omgeving, niet uit
    Source.settings -- structureel is een lege settings altijd geldig."""

    assert adapter_registry.validate_settings("cso_api", {}) is None


# ---------------------------------------------------------------------------
# app._validate_settings() -- JSON-parsing + delegatie
# ---------------------------------------------------------------------------

def test_app_validate_settings_lege_settings_is_geldig_voor_generic_links():

    assert app_module._validate_settings("generic_links", "", "https://voorbeeld.nl") is None


def test_app_validate_settings_ongeldige_json():

    error = app_module._validate_settings("generic_links", "{niet geldig,,,}", "https://voorbeeld.nl")

    assert "geldige JSON" in error


def test_app_validate_settings_json_geen_object():

    error = app_module._validate_settings("generic_links", "[1, 2, 3]", "https://voorbeeld.nl")

    assert "JSON-object" in error


def test_app_validate_settings_delegeert_naar_adapter():

    error = app_module._validate_settings("html_listing", "{}", "https://voorbeeld.nl")

    assert "selectors.item" in error


def test_app_validate_settings_onbekende_adapter_geeft_nette_fout_geen_crash():

    error = app_module._validate_settings("bestaat_niet", "{}", "https://voorbeeld.nl")

    assert "Onbekende adapter" in error


# ---------------------------------------------------------------------------
# app._maybe_run_live_validation() -- live-check + always/opt_in/skip-policy
# ---------------------------------------------------------------------------

def test_live_validation_skip_policy_draait_nooit_ook_niet_met_live_test_true():

    with patch.object(app_module, "run_source_test") as mock_test:

        result = app_module._maybe_run_live_validation(
            "cso_api", "https://voorbeeld.nl", "{}", True
        )

        assert result is None
        mock_test.assert_not_called()


def test_live_validation_opt_in_policy_slaat_over_zonder_live_test_vinkje():

    with patch.object(app_module, "run_source_test") as mock_test:

        result = app_module._maybe_run_live_validation(
            "embedded_json", "https://voorbeeld.nl", "{}", False
        )

        assert result is None
        mock_test.assert_not_called()


def test_live_validation_opt_in_policy_draait_met_live_test_vinkje():

    with patch.object(app_module, "run_source_test", return_value={"error": "kapot", "count": 0, "preview": []}) as mock_test:

        result = app_module._maybe_run_live_validation(
            "embedded_json", "https://voorbeeld.nl", '{"items_path": ["a"]}', True
        )

        assert result == "kapot"
        mock_test.assert_called_once()


def test_live_validation_always_policy_draait_automatisch():

    with patch.object(app_module, "run_source_test", return_value={"error": None, "count": 3, "preview": []}) as mock_test:

        result = app_module._maybe_run_live_validation(
            "generic_links", "https://voorbeeld.nl", "", False
        )

        assert result is None
        mock_test.assert_called_once()


def test_live_validation_geeft_foutmelding_van_test_source_door():

    with patch.object(
        app_module,
        "run_source_test",
        return_value={"error": "404 niet gevonden", "count": 0, "preview": []},
    ):

        result = app_module._maybe_run_live_validation(
            "discovered_api",
            "https://voorbeeld.nl",
            json.dumps({"endpoint_url": "https://voorbeeld.nl/api"}),
            False,
        )

        assert result == "404 niet gevonden"
