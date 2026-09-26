"""Tests for the Nortec Go binary sensors."""

from unittest.mock import AsyncMock

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import ATTR_DEVICE_CLASS, STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from pynortecgo import ChargeState
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import make_charger, make_vehicle, setup_integration


@pytest.mark.parametrize(
    ("charge_state", "charging"),
    [
        (None, STATE_OFF),
        (ChargeState.STARTING, STATE_OFF),
        (ChargeState.CHARGING, STATE_ON),
        (ChargeState.PAUSED, STATE_OFF),
    ],
)
async def test_charger_binary_sensors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    charge_state: ChargeState | None,
    charging: str,
) -> None:
    """Cable connected and Charging follow the charger."""
    mock_client.get_charger.return_value = make_charger(
        is_connected=True, charge_state=charge_state
    )
    await setup_integration(hass, mock_config_entry)

    cable = hass.states.get("binary_sensor.garage_charger_cable_connected")
    assert cable is not None
    assert cable.state == STATE_ON
    assert cable.attributes[ATTR_DEVICE_CLASS] == BinarySensorDeviceClass.PLUG
    state = hass.states.get("binary_sensor.garage_charger_charging")
    assert state is not None
    assert state.state == charging
    assert (
        state.attributes[ATTR_DEVICE_CLASS] == BinarySensorDeviceClass.BATTERY_CHARGING
    )


@pytest.mark.parametrize(
    ("is_connected", "plugged_in", "plugged", "connected"),
    [
        (False, True, STATE_ON, STATE_OFF),
        (False, None, STATE_UNKNOWN, STATE_OFF),
        (True, True, STATE_ON, STATE_ON),
        (True, False, STATE_OFF, STATE_OFF),
        (True, None, STATE_UNKNOWN, STATE_UNKNOWN),
    ],
)
async def test_car_binary_sensors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    is_connected: bool,
    plugged_in: bool | None,
    plugged: str,
    connected: str,
) -> None:
    """Plugged in follows the car; Connected to charger needs the cable and the car."""
    mock_client.get_charger.return_value = make_charger(is_connected=is_connected)
    mock_client.get_vehicle.return_value = make_vehicle(plugged_in=plugged_in)
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get("binary_sensor.family_car_plugged_in")
    assert state is not None
    assert state.state == plugged
    state = hass.states.get("binary_sensor.family_car_connected_to_charger")
    assert state is not None
    assert state.state == connected
    assert state.attributes[ATTR_DEVICE_CLASS] == BinarySensorDeviceClass.PLUG
