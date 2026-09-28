"""A charge the car paused, as the owner saw it in Home Assistant (spec §2)."""

from unittest.mock import AsyncMock

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from pynortecgo import ChargerState, ChargeState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import make_charger, setup_integration


async def test_car_paused_charge_entities(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """Charge stays on, Charge status is paused, Charging is off."""
    mock_client.get_charger.return_value = make_charger(
        is_connected=True,
        state=ChargerState.BUSY_NON_CHARGING,
        charge_state=ChargeState.PAUSED,
    )
    await setup_integration(hass, mock_config_entry)

    switch = hass.states.get("switch.garage_charger_charge")
    status = hass.states.get("sensor.garage_charger_charge_status")
    charging = hass.states.get("binary_sensor.garage_charger_charging")
    assert switch is not None
    assert status is not None
    assert charging is not None
    assert switch.state == STATE_ON
    assert status.state == "paused"
    assert charging.state == STATE_OFF
