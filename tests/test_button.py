"""Tests for the Nortec Go Refresh button."""

from unittest.mock import AsyncMock

from homeassistant.components.button.const import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from pynortecgo import NortecGoConnectionError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import make_charger, setup_integration

ENTITY_ID = "button.garage_charger_refresh"


async def _press(hass: HomeAssistant) -> None:
    await hass.services.async_call(
        BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
    )
    await hass.async_block_till_done()


async def test_press_reads_charger_car_and_prices(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A press reads the charger, the car and the prices once more."""
    await setup_integration(hass, mock_config_entry)
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    chargers = mock_client.get_charger.await_count
    vehicles = mock_client.get_vehicle.await_count
    forecasts = mock_client.get_price_forecast.await_count

    await _press(hass)

    assert mock_client.get_charger.await_count == chargers + 1
    assert mock_client.get_vehicle.await_count == vehicles + 1
    assert mock_client.get_price_forecast.await_count == forecasts + 1


async def test_press_shows_the_new_read(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """The entities show what the press read."""
    await setup_integration(hass, mock_config_entry)
    mock_client.get_charger.return_value = make_charger(is_connected=True)

    await _press(hass)

    state = hass.states.get("binary_sensor.garage_charger_cable_connected")
    assert state is not None
    assert state.state == "on"


async def test_press_after_failed_read_does_not_raise(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A failed read makes the entities unavailable; the press raises nothing."""
    await setup_integration(hass, mock_config_entry)
    mock_client.get_charger.side_effect = NortecGoConnectionError("x")

    await _press(hass)

    state = hass.states.get("binary_sensor.garage_charger_cable_connected")
    assert state is not None
    assert state.state == "unavailable"
    button = hass.states.get(ENTITY_ID)
    assert button is not None
    assert button.state != "unavailable"
