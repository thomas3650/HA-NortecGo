"""Tests for the Nortec Go integration setup."""

import asyncio
from datetime import timedelta
import json
import logging
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant import loader
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_DEVICE_ID, CONF_EMAIL
from homeassistant.core import DOMAIN as HOMEASSISTANT_DOMAIN, HomeAssistant
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)
from homeassistant.setup import async_setup_component
from pynortecgo import (
    AuthError,
    MultipleVehiclesError,
    NortecGoConnectionError,
    VehicleNotFoundError,
)
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.nortec_go.const import DOMAIN
from custom_components.nortec_go.coordinator import car_device_identifier
from custom_components.nortec_go.entry import tokens_from_data

from .conftest import (
    FAKE_CHARGER_ID,
    FAKE_DEVICE_ID,
    FAKE_EMAIL,
    FAKE_TOKENS,
    NEW_TOKENS,
    setup_integration,
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


async def test_setup_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client_class: MagicMock,
    mock_client: AsyncMock,
) -> None:
    """Setup builds the client from stored data, sets the stored charger, reads it once."""
    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_config_entry.runtime_data.client is mock_client
    kwargs = mock_client_class.call_args.kwargs
    assert kwargs["tokens"] == FAKE_TOKENS
    assert kwargs["device_id"] == FAKE_DEVICE_ID
    assert kwargs["on_tokens_refreshed"] is not None
    mock_client.set_charger.assert_called_once_with(FAKE_CHARGER_ID)
    mock_client.get_charger.assert_awaited_once()
    mock_client.login.assert_not_awaited()


async def test_setup_retry_reuses_stored_tokens(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client_class: MagicMock,
    mock_client: AsyncMock,
) -> None:
    """A retry after a transient error reads with the stored tokens and never logs in."""
    mock_client.get_charger.side_effect = NortecGoConnectionError("network down")
    await setup_integration(hass, mock_config_entry)
    state = mock_config_entry.state  # a local, so mypy doesn't keep the narrowing
    assert state is ConfigEntryState.SETUP_RETRY

    mock_client.get_charger.side_effect = None
    await hass.config_entries.async_reload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_client_class.call_count == 2
    assert mock_client_class.call_args.kwargs["tokens"] == FAKE_TOKENS
    mock_client.login.assert_not_awaited()


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
        await setup_integration(hass, mock_config_entry)

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
    await setup_integration(hass, mock_config_entry)
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
    await setup_integration(hass, mock_config_entry)
    loaded_state = mock_config_entry.state  # a local, so mypy doesn't narrow
    assert loaded_state is ConfigEntryState.LOADED
    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    unloaded_state = mock_config_entry.state  # a local, so mypy doesn't narrow
    assert unloaded_state is ConfigEntryState.NOT_LOADED


async def test_unload_stops_the_timers(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """After unload, neither the polling, the price time nor the tick reads anything."""
    await setup_integration(hass, mock_config_entry)
    # A listener keeps polling scheduled without entities (Task 2), so unload has something to stop.
    mock_config_entry.runtime_data.async_add_listener(lambda: None)
    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    freezer.tick(timedelta(days=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_client.get_price_forecast.await_count == 1
    assert mock_client.get_charger.await_count == 1


async def test_unload_cancels_a_price_read_in_flight(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A scheduled price read still running at unload is cancelled."""
    await setup_integration(hass, mock_config_entry)
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def _slow_forecast() -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    mock_client.get_price_forecast.side_effect = _slow_forecast
    mock_config_entry.runtime_data.async_start_price_read()
    await started.wait()
    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert cancelled.is_set()


async def test_remove_entry_removes_stored_prices(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    hass_storage: dict[str, Any],
) -> None:
    """Deleting the entry deletes its stored prices."""
    await setup_integration(hass, mock_config_entry)
    key = f"nortec_go.{mock_config_entry.entry_id}.prices"
    assert key in hass_storage
    assert await hass.config_entries.async_remove(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert key not in hass_storage


CAR_ENTITY_IDS = (
    "sensor.family_car_battery",
    "sensor.family_car_charge_limit",
    "sensor.family_car_last_seen",
    "binary_sensor.family_car_plugged_in",
    "binary_sensor.family_car_connected_to_charger",
)


@pytest.mark.parametrize(
    "error",
    [VehicleNotFoundError("no car"), MultipleVehiclesError("two cars")],
)
async def test_reload_without_car_removes_car_device(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    error: Exception,
) -> None:
    """A reload that finds no single car removes the car device and its entities."""
    await setup_integration(hass, mock_config_entry)
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    identifier = car_device_identifier(str(FAKE_CHARGER_ID))
    assert (
        device_registry.async_get_device_by_identifier(
            identifier, mock_config_entry.entry_id
        )
        is not None
    )
    for entity_id in CAR_ENTITY_IDS:
        assert entity_registry.async_get(entity_id) is not None

    mock_client.get_vehicle.side_effect = error
    await hass.config_entries.async_reload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert (
        device_registry.async_get_device_by_identifier(
            identifier, mock_config_entry.entry_id
        )
        is None
    )
    for entity_id in CAR_ENTITY_IDS:
        assert entity_registry.async_get(entity_id) is None
        assert hass.states.get(entity_id) is None
