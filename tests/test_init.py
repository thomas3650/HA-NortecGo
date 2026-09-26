"""Tests for the Nortec Go integration setup."""

import json
import logging
from pathlib import Path

from homeassistant import loader
from homeassistant.core import DOMAIN as HOMEASSISTANT_DOMAIN, HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
import pytest

from custom_components.nortec_go.const import DOMAIN

INTEGRATION_DIR = Path(__file__).parent.parent / "custom_components" / DOMAIN


async def test_setup(hass: HomeAssistant) -> None:
    """The integration sets up without any configuration."""
    assert await async_setup_component(hass, DOMAIN, {})
    assert DOMAIN in hass.config.components


async def test_yaml_config_is_rejected(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """A YAML key doesn't break setup; it logs an error and raises a repair issue."""
    assert await async_setup_component(hass, DOMAIN, {DOMAIN: {}})
    assert "does not support YAML setup" in caplog.text
    issue = ir.async_get(hass).async_get_issue(
        HOMEASSISTANT_DOMAIN, f"config_entry_only_{DOMAIN}"
    )
    assert issue is not None


async def test_component_is_discovered(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Home Assistant's loader finds the custom component."""
    caplog.set_level(logging.WARNING)
    await loader.async_get_integration(hass, "sun")
    assert f"custom integration {DOMAIN}" in caplog.text


def test_translations_match_strings() -> None:
    """translations/en.json is an exact copy of strings.json."""
    strings = json.loads((INTEGRATION_DIR / "strings.json").read_text(encoding="utf-8"))
    english = json.loads(
        (INTEGRATION_DIR / "translations" / "en.json").read_text(encoding="utf-8")
    )
    assert english == strings
