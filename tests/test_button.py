"""Tests for the Nortec Go Refresh button."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from homeassistant.components.button.const import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import UpdateFailed
from pynortecgo import (
    ApiError,
    AuthError,
    ChargerNotFoundError,
    NortecGoConnectionError,
    NortecGoError,
    RateLimitError,
    UnexpectedResponseError,
)
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nortec_go.button import read_error
from custom_components.nortec_go.const import DOMAIN

from .conftest import make_charger, setup_integration

ENTITY_ID = "button.garage_charger_refresh"
CABLE_ID = "binary_sensor.garage_charger_cable_connected"
STRINGS = Path(__file__).parent.parent / "custom_components" / DOMAIN / "strings.json"
CHARGER_KEYS = [
    "auth_failed",
    "rate_limited",
    "cannot_connect",
    "api_error",
    "charger_not_found",
    "unexpected_response",
    "read_failed",
]


async def _press(hass: HomeAssistant) -> None:
    await hass.services.async_call(
        BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
    )
    await hass.async_block_till_done()


async def _failed_press(hass: HomeAssistant) -> HomeAssistantError:
    """Press, and return the error the press raised; reauth is not started for real."""
    with (
        patch.object(ConfigEntry, "async_start_reauth"),
        pytest.raises(HomeAssistantError) as exc_info,
    ):
        await _press(hass)
    await hass.async_block_till_done()
    raised = exc_info.value
    assert type(raised) is HomeAssistantError
    assert raised.translation_domain == DOMAIN
    return raised


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


async def test_press_after_failed_read_raises(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A failed charger read raises its text; the prices are still read and the button stays."""
    await setup_integration(hass, mock_config_entry)
    forecasts = mock_client.get_price_forecast.await_count
    error = NortecGoConnectionError("x")
    mock_client.get_charger.side_effect = error

    raised = await _failed_press(hass)

    assert raised.translation_key == "cannot_connect"
    assert isinstance(raised.__cause__, UpdateFailed)
    assert raised.__cause__.__cause__ is error
    assert mock_client.get_price_forecast.await_count == forecasts + 1
    state = hass.states.get(CABLE_ID)
    assert state is not None
    assert state.state == "unavailable"
    button = hass.states.get(ENTITY_ID)
    assert button is not None
    assert button.state != "unavailable"


@pytest.mark.parametrize(
    ("error", "key"),
    [
        (AuthError("token rejected"), "auth_failed"),
        (RateLimitError("too many requests", retry_after=30.0), "rate_limited"),
        (NortecGoConnectionError("network down"), "cannot_connect"),
        (ApiError("GET /example", 500), "api_error"),
        (ChargerNotFoundError("GET /example: not found"), "charger_not_found"),
        (UnexpectedResponseError("GET /example", "bad shape"), "unexpected_response"),
        (NortecGoError("something new"), "read_failed"),
        (TimeoutError(), "read_failed"),
    ],
)
async def test_press_raises_the_charger_reads_text(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    error: Exception,
    key: str,
) -> None:
    """Each charger read error raises its own text; one outside pynortecgo raises read_failed."""
    await setup_integration(hass, mock_config_entry)
    mock_client.get_charger.side_effect = error

    raised = await _failed_press(hass)

    assert raised.translation_key == key


async def test_press_reports_a_rejected_car_read(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A rejected car read fails the read, so the press raises auth_failed; the prices are read."""
    await setup_integration(hass, mock_config_entry)
    forecasts = mock_client.get_price_forecast.await_count
    mock_client.get_vehicle.side_effect = AuthError("token rejected")

    raised = await _failed_press(hass)

    assert raised.translation_key == "auth_failed"
    assert mock_client.get_price_forecast.await_count == forecasts + 1


async def test_press_ignores_another_car_error(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A car error that keeps the car's last data fails nothing, and the press raises nothing."""
    await setup_integration(hass, mock_config_entry)
    vehicles = mock_client.get_vehicle.await_count
    mock_client.get_vehicle.side_effect = NortecGoConnectionError("network down")

    await _press(hass)

    assert mock_client.get_vehicle.await_count == vehicles + 1


@pytest.mark.parametrize(
    ("error", "key"),
    [
        (NortecGoConnectionError("network down"), "price_read_failed"),
        (RateLimitError("too many requests", retry_after=30.0), "price_read_failed"),
        (AuthError("token rejected"), "auth_failed"),
    ],
)
async def test_press_raises_when_only_the_price_read_fails(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    error: Exception,
    key: str,
) -> None:
    """A failed price read raises its text; the charger's entities stay available."""
    await setup_integration(hass, mock_config_entry)
    mock_client.get_price_forecast.side_effect = error

    raised = await _failed_press(hass)

    assert raised.translation_key == key
    assert raised.__cause__ is error
    state = hass.states.get(CABLE_ID)
    assert state is not None
    assert state.state != "unavailable"


async def test_press_charger_error_wins_when_both_reads_fail(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """With both reads failing, the price read still runs and the charger's text is raised."""
    await setup_integration(hass, mock_config_entry)
    forecasts = mock_client.get_price_forecast.await_count
    mock_client.get_charger.side_effect = ApiError("GET /example", 500)
    mock_client.get_price_forecast.side_effect = NortecGoConnectionError("network down")

    raised = await _failed_press(hass)

    assert raised.translation_key == "api_error"
    assert mock_client.get_price_forecast.await_count == forecasts + 1


async def test_press_after_a_failed_press_works_again(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A good press after a failed one raises nothing: the old error isn't raised again."""
    await setup_integration(hass, mock_config_entry)
    mock_client.get_charger.side_effect = NortecGoConnectionError("network down")
    await _failed_press(hass)

    mock_client.get_charger.side_effect = None
    await _press(hass)

    state = hass.states.get(CABLE_ID)
    assert state is not None
    assert state.state != "unavailable"


def test_read_error_copies_our_translated_error() -> None:
    """Our own translated error gives a plain error with the same key and placeholders."""
    source = UpdateFailed(
        translation_domain=DOMAIN,
        translation_key="rate_limited",
        translation_placeholders={"seconds": "30"},
    )

    raised = read_error(source)

    assert type(raised) is HomeAssistantError
    assert raised.translation_domain == DOMAIN
    assert raised.translation_key == "rate_limited"
    assert raised.translation_placeholders == {"seconds": "30"}


@pytest.mark.parametrize(
    "source",
    [
        None,
        TimeoutError(),
        HomeAssistantError("no translation"),
        HomeAssistantError(translation_domain="other", translation_key="some_key"),
    ],
)
def test_read_error_falls_back_to_read_failed(source: BaseException | None) -> None:
    """Anything that isn't our own translated error is reported as read_failed."""
    raised = read_error(source)

    assert type(raised) is HomeAssistantError
    assert raised.translation_domain == DOMAIN
    assert raised.translation_key == "read_failed"


@pytest.mark.parametrize("key", [*CHARGER_KEYS, "price_read_failed"])
def test_press_error_keys_have_texts(key: str) -> None:
    """Every key a press can raise has a text in strings.json."""
    exceptions = json.loads(STRINGS.read_text(encoding="utf-8"))["exceptions"]
    assert exceptions[key]["message"]


async def test_press_twice_reads_twice(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """Two presses within HA's 10 s debounce cooldown each read the charger and the car."""
    await setup_integration(hass, mock_config_entry)
    chargers = mock_client.get_charger.await_count
    vehicles = mock_client.get_vehicle.await_count

    await _press(hass)
    await _press(hass)

    assert mock_client.get_charger.await_count == chargers + 2
    assert mock_client.get_vehicle.await_count == vehicles + 2
