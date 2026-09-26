"""Tests for the Nortec Go integration setup."""

import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant import loader
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_DEVICE_ID, CONF_EMAIL
from homeassistant.core import DOMAIN as HOMEASSISTANT_DOMAIN, HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pynortecgo import (
    ApiError,
    AuthError,
    ChargerNotFoundError,
    MultipleChargersError,
    NortecGoConnectionError,
    RateLimitError,
    UnexpectedResponseError,
)
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nortec_go.const import DOMAIN
from custom_components.nortec_go.entry import tokens_from_data

from .conftest import (
    FAKE_CHARGER_ID,
    FAKE_DEVICE_ID,
    FAKE_EMAIL,
    FAKE_TOKENS,
    NEW_TOKENS,
    OTHER_CHARGER_ID,
    make_charger,
)

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


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client_class: MagicMock,
    mock_client: AsyncMock,
) -> None:
    """Setup builds the client from the stored tokens and device_id, reads the charger once."""
    await _setup(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_config_entry.runtime_data is mock_client
    kwargs = mock_client_class.call_args.kwargs
    assert kwargs["tokens"] == FAKE_TOKENS
    assert kwargs["device_id"] == FAKE_DEVICE_ID
    assert kwargs["on_tokens_refreshed"] is not None
    mock_client.get_charger.assert_awaited_once()
    mock_client.login.assert_not_awaited()


@pytest.mark.parametrize(
    ("error", "state"),
    [
        (NortecGoConnectionError("network down"), ConfigEntryState.SETUP_RETRY),
        (RateLimitError("too many requests"), ConfigEntryState.SETUP_RETRY),
        (ApiError("GET /example", 500), ConfigEntryState.SETUP_RETRY),
        (
            UnexpectedResponseError("GET /example", "bad shape"),
            ConfigEntryState.SETUP_ERROR,
        ),
        (ChargerNotFoundError("no charger"), ConfigEntryState.SETUP_ERROR),
        (MultipleChargersError("two chargers"), ConfigEntryState.SETUP_ERROR),
    ],
)
async def test_setup_errors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    error: Exception,
    state: ConfigEntryState,
) -> None:
    """Transient errors retry setup, permanent ones stop it; neither logs in."""
    mock_client.get_charger.side_effect = error
    await _setup(hass, mock_config_entry)

    assert mock_config_entry.state is state
    mock_client.login.assert_not_awaited()


async def test_setup_retry_reuses_stored_tokens(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client_class: MagicMock,
    mock_client: AsyncMock,
) -> None:
    """A retry after a transient error reads with the stored tokens and never logs in."""
    mock_client.get_charger.side_effect = NortecGoConnectionError("network down")
    await _setup(hass, mock_config_entry)
    state = mock_config_entry.state  # a local, so mypy doesn't keep the narrowing
    assert state is ConfigEntryState.SETUP_RETRY

    mock_client.get_charger.side_effect = None
    await hass.config_entries.async_reload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_client_class.call_count == 2
    assert mock_client_class.call_args.kwargs["tokens"] == FAKE_TOKENS
    mock_client.login.assert_not_awaited()


async def test_setup_auth_error_starts_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
) -> None:
    """A rejected token stops setup and asks HA for reauth, without logging in."""
    mock_client.get_charger.side_effect = AuthError("token rejected")
    with patch.object(ConfigEntry, "async_start_reauth_if_available") as start_reauth:
        await _setup(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    start_reauth.assert_called_once()
    mock_client.login.assert_not_awaited()


async def test_setup_charger_changed(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Another charger on the account stops setup, and neither ID is logged."""
    mock_client.get_charger.return_value = make_charger(OTHER_CHARGER_ID)
    await _setup(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    assert "charger has changed" in caplog.text
    assert str(FAKE_CHARGER_ID) not in caplog.text
    assert str(OTHER_CHARGER_ID) not in caplog.text


async def test_setup_logs_no_credentials(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Setup failures never log the email, tokens or device_id."""
    caplog.set_level(logging.DEBUG, logger="custom_components.nortec_go")
    mock_client.get_charger.side_effect = AuthError("token rejected")
    with patch.object(ConfigEntry, "async_start_reauth_if_available"):
        await _setup(hass, mock_config_entry)

    assert "could not authenticate" in caplog.text
    for secret in (
        FAKE_EMAIL,
        FAKE_DEVICE_ID,
        FAKE_TOKENS.access_token,
        FAKE_TOKENS.refresh_token,
    ):
        assert secret not in caplog.text


async def test_tokens_refreshed_are_stored(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client_class: MagicMock,
) -> None:
    """New tokens from a refresh go into entry.data; email and device_id stay; no reload."""
    await _setup(hass, mock_config_entry)
    on_tokens_refreshed = mock_client_class.call_args.kwargs["on_tokens_refreshed"]

    await on_tokens_refreshed(NEW_TOKENS)
    await hass.async_block_till_done()

    assert tokens_from_data(mock_config_entry.data) == NEW_TOKENS
    assert mock_config_entry.data[CONF_EMAIL] == FAKE_EMAIL
    assert mock_config_entry.data[CONF_DEVICE_ID] == FAKE_DEVICE_ID
    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_client_class.call_count == 1


async def test_unload_entry(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """Unload returns the entry to NOT_LOADED."""
    await _setup(hass, mock_config_entry)
    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED
