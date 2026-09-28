"""Tests for the Nortec Go Charge switch."""

from unittest.mock import AsyncMock

from homeassistant.components.switch.const import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pynortecgo import (
    CableNotConnectedError,
    ChargerState,
    ChargeState,
    NortecGoConnectionError,
    VehicleNotFoundError,
)
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import make_charger, setup_integration

ENTITY_ID = "switch.garage_charger_charge"


def _state(hass: HomeAssistant, entity_id: str = ENTITY_ID) -> str:
    state = hass.states.get(entity_id)
    assert state is not None
    return state.state


async def _call(hass: HomeAssistant, service: str) -> None:
    await hass.services.async_call(
        SWITCH_DOMAIN, service, {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
    )


@pytest.mark.parametrize(
    ("charge_state", "expected"),
    [
        (None, STATE_OFF),
        (ChargeState.STARTING, STATE_ON),
        (ChargeState.CHARGING, STATE_ON),
        (ChargeState.PAUSED, STATE_ON),
        (ChargeState.STOPPING, STATE_OFF),
    ],
)
async def test_switch_state(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    charge_state: ChargeState | None,
    expected: str,
) -> None:
    """The switch follows the charge."""
    mock_client.get_charger.return_value = make_charger(
        is_connected=True, charge_state=charge_state
    )
    await setup_integration(hass, mock_config_entry)
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == expected


async def test_turn_on_twice_starts_once(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """turn_on starts once; the switch is on at once; a second turn_on is a no-op (Review Focus 2)."""
    mock_client.get_charger.return_value = make_charger(is_connected=True)
    await setup_integration(hass, mock_config_entry)
    await _call(hass, SERVICE_TURN_ON)
    assert _state(hass) == STATE_ON
    await _call(hass, SERVICE_TURN_ON)
    mock_client.start_charge.assert_awaited_once()


async def test_turn_off_during_pending_start(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """turn_off during a pending start shows off and calls nothing yet."""
    mock_client.get_charger.return_value = make_charger(is_connected=True)
    await setup_integration(hass, mock_config_entry)
    await _call(hass, SERVICE_TURN_ON)
    await _call(hass, SERVICE_TURN_OFF)
    assert _state(hass) == STATE_OFF
    mock_client.stop_charge.assert_not_awaited()


async def test_turn_off_stops(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """turn_off on a charge calls stop_charge once."""
    mock_client.get_charger.return_value = make_charger(
        is_connected=True, charge_state=ChargeState.CHARGING
    )
    await setup_integration(hass, mock_config_entry)
    await _call(hass, SERVICE_TURN_OFF)
    mock_client.stop_charge.assert_awaited_once()


async def test_translated_error(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A pre-check error reaches the caller translated."""
    mock_client.get_charger.return_value = make_charger(is_connected=True)
    mock_client.start_charge.side_effect = CableNotConnectedError("x")
    await setup_integration(hass, mock_config_entry)
    with pytest.raises(ServiceValidationError, match="No cable is connected"):
        await _call(hass, SERVICE_TURN_ON)


async def test_switch_available_after_failed_read(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """After a failed read the switch stays available and turn_off still stops (Review Focus 4)."""
    mock_client.get_charger.return_value = make_charger(
        is_connected=True, charge_state=ChargeState.CHARGING
    )
    await setup_integration(hass, mock_config_entry)
    mock_client.get_charger.side_effect = NortecGoConnectionError("x")
    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass) != STATE_UNAVAILABLE
    assert _state(hass, "binary_sensor.garage_charger_charging") == STATE_UNAVAILABLE
    await _call(hass, SERVICE_TURN_OFF)
    mock_client.stop_charge.assert_awaited_once()


async def test_switch_off_right_after_a_stop(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """After a stop the switch stays off while the charger still says CHARGING; on is refused."""
    mock_client.get_charger.return_value = make_charger(
        is_connected=True,
        charge_state=ChargeState.CHARGING,
        state=ChargerState.BUSY_CHARGING,
    )
    await setup_integration(hass, mock_config_entry)
    assert _state(hass) == STATE_ON
    await _call(hass, SERVICE_TURN_OFF)
    await hass.async_block_till_done()
    assert _state(hass) == STATE_OFF
    with pytest.raises(ServiceValidationError) as exc_info:
        await _call(hass, SERVICE_TURN_ON)
    assert exc_info.value.translation_key == "stop_pending"
    assert "A stop is under way" in str(exc_info.value)
    mock_client.start_charge.assert_not_awaited()


async def test_switch_added_without_a_car(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """The Charge switch is added even when the account has no car (D32)."""
    mock_client.get_vehicle.side_effect = VehicleNotFoundError("no car")
    await setup_integration(hass, mock_config_entry)
    assert not mock_config_entry.runtime_data.has_car
    assert _state(hass) == STATE_OFF
