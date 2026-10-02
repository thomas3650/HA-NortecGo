"""Tests for the Nortec Go coordinator: polling, errors, prices and timers."""

import asyncio
import copy
from datetime import UTC, datetime, timedelta
import json
import logging
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryError,
    HomeAssistantError,
)
from homeassistant.helpers import device_registry as dr, issue_registry as ir
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util
from pynortecgo import (
    ApiError,
    AuthError,
    Charger,
    ChargerNotFoundError,
    ChargerState,
    ChargeState,
    MultipleVehiclesError,
    NortecGoConnectionError,
    NortecGoError,
    RateLimitError,
    UnexpectedResponseError,
    Vehicle,
    VehicleNotFoundError,
)
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.nortec_go.charge_control import ChargeControlState
from custom_components.nortec_go.const import (
    CAR_GONE_ISSUE_ID,
    DOMAIN,
    FAST_READ_MAX_AGE,
    INTERVAL_CHANGING,
    INTERVAL_CHARGING,
    INTERVAL_IDLE,
    START_CONFIRM_TIMEOUT,
    STOP_CONFIRM_TIMEOUT,
)
from custom_components.nortec_go.coordinator import (
    NortecGoCoordinator,
    car_device_identifier,
    interval_for,
)
from custom_components.nortec_go.energy import EnergyLedger, EnergyStore

from .conftest import (
    FAKE_CHARGE_ID,
    FAKE_CHARGER_ID,
    make_charger,
    make_forecast,
    make_vehicle,
    setup_integration,
)

# 2026-09-27 00:00 local (CEST) is 2026-09-26 22:00 UTC.
MIDNIGHT = datetime(2026, 9, 26, 22, 0, tzinfo=UTC)
STORE_KEY = "nortec_go.{}.prices"
ENERGY_STORE_KEY = "nortec_go.{}.energy"


@pytest.fixture(autouse=True)
async def copenhagen(hass: HomeAssistant) -> None:
    """Run every test in the owner's time zone."""
    await hass.config.async_set_time_zone("Europe/Copenhagen")


def _coordinator(entry: MockConfigEntry) -> NortecGoCoordinator:
    """The entry's coordinator, with a listener so it keeps polling without entities."""
    coordinator: NortecGoCoordinator = entry.runtime_data
    # HA only schedules the next poll while the coordinator has listeners; in Task 2
    # there are no entities yet. Adding the first listener also schedules a poll.
    coordinator.async_add_listener(lambda: None)
    return coordinator


class _UnknownClientError(NortecGoError):
    """A client error type from a later pynortecgo version."""


AUTH_TEXT = "The Nortec Go session was rejected. Sign in again from the repair notice"


_PENDING = ChargeControlState(start_pending=True)


@pytest.mark.parametrize(
    ("charger", "control", "interval"),
    [
        (make_charger(is_connected=True), _PENDING, INTERVAL_CHANGING),
        (
            make_charger(is_connected=True, charge_state=ChargeState.STARTING),
            _PENDING,
            INTERVAL_CHANGING,
        ),
        (
            make_charger(is_connected=True, charge_state=ChargeState.CHARGING),
            _PENDING,
            INTERVAL_CHARGING,
        ),
        (
            make_charger(is_connected=True),
            ChargeControlState(start_pending=True, stop_asked=True),
            INTERVAL_CHANGING,
        ),
        (
            make_charger(is_connected=True, charge_state=ChargeState.CHARGING),
            ChargeControlState(stop_pending=True),
            INTERVAL_CHANGING,
        ),
        (
            make_charger(is_connected=True, charge_state=ChargeState.STARTING),
            ChargeControlState(),
            INTERVAL_CHANGING,
        ),
        (
            make_charger(is_connected=True, charge_state=ChargeState.STOPPING),
            ChargeControlState(),
            INTERVAL_CHANGING,
        ),
        (
            make_charger(is_connected=True, charge_state=ChargeState.CHARGING),
            ChargeControlState(),
            INTERVAL_CHARGING,
        ),
        (
            make_charger(is_connected=True, charge_state=ChargeState.PAUSED),
            ChargeControlState(),
            INTERVAL_IDLE,
        ),
        (make_charger(is_connected=True), ChargeControlState(), INTERVAL_IDLE),
        (make_charger(is_connected=False), ChargeControlState(), INTERVAL_IDLE),
        (
            make_charger(is_connected=True, state=ChargerState.BUSY_NON_RELEASED),
            ChargeControlState(),
            INTERVAL_IDLE,
        ),
        (
            make_charger(is_connected=True),
            ChargeControlState(blocked=True),
            INTERVAL_IDLE,
        ),
    ],
)
def test_interval_for(
    charger: Any, control: ChargeControlState, interval: timedelta
) -> None:
    """30 s while starting or stopping, 5 min while charging, 60 min otherwise (D29)."""
    assert interval_for(charger, control, timedelta(0)) == interval


async def test_setup_reads_charger_car_and_prices(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """Setup sets the charger, reads charger, car and prices once, and sets the interval."""
    mock_client.get_charger.return_value = make_charger(is_connected=True)
    await setup_integration(hass, mock_config_entry)

    coordinator = _coordinator(mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert coordinator.client is mock_client
    assert coordinator.has_car
    assert coordinator.data.vehicle == make_vehicle()
    assert coordinator.update_interval == INTERVAL_IDLE
    mock_client.set_charger.assert_called_once_with(FAKE_CHARGER_ID)
    mock_client.get_vehicle.assert_awaited_once()
    mock_client.get_price_forecast.assert_awaited_once_with()


async def test_interval_changes_after_a_poll(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A poll that sees a charge starts polling every 5 minutes."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    assert coordinator.update_interval == INTERVAL_IDLE

    mock_client.get_charger.return_value = make_charger(
        is_connected=True, charge_state=ChargeState.CHARGING
    )
    freezer.tick(INTERVAL_IDLE)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert coordinator.update_interval == INTERVAL_CHARGING
    assert mock_client.get_charger.await_count == 2
    assert mock_client.get_vehicle.await_count == 2


@pytest.mark.parametrize(
    ("error", "state", "key"),
    [
        (
            NortecGoConnectionError("network down"),
            ConfigEntryState.SETUP_RETRY,
            "cannot_connect",
        ),
        (
            RateLimitError("too many requests"),
            ConfigEntryState.SETUP_RETRY,
            "rate_limited",
        ),
        (ApiError("GET /example", 500), ConfigEntryState.SETUP_RETRY, "api_error"),
        (
            UnexpectedResponseError("GET /example", "bad shape"),
            ConfigEntryState.SETUP_ERROR,
            "unexpected_response",
        ),
        (
            ChargerNotFoundError("GET /example: the set charger was not found"),
            ConfigEntryState.SETUP_ERROR,
            "charger_not_found",
        ),
    ],
)
async def test_first_refresh_charger_errors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    error: Exception,
    state: ConfigEntryState,
    key: str,
) -> None:
    """Charger errors at setup retry or stop setup with our text; the car isn't read."""
    mock_client.get_charger.side_effect = error
    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is state
    assert mock_config_entry.error_reason_translation_domain == DOMAIN
    assert mock_config_entry.error_reason_translation_key == key
    assert str(error) not in (mock_config_entry.reason or "")
    mock_client.get_vehicle.assert_not_awaited()


@pytest.mark.parametrize("method", ["get_charger", "get_vehicle", "get_price_forecast"])
async def test_first_refresh_auth_error_starts_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    method: str,
) -> None:
    """An AuthError from any read during setup starts reauth, without logging in."""
    getattr(mock_client, method).side_effect = AuthError("token rejected")
    with patch.object(ConfigEntry, "async_start_reauth_if_available") as start_reauth:
        await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    start_reauth.assert_called_once()
    mock_client.login.assert_not_awaited()


@pytest.mark.parametrize(
    ("method", "debug_line"),
    [
        ("get_charger", "Reading the charger failed: token rejected"),
        ("get_vehicle", "Reading the car was rejected: token rejected"),
        (
            "get_price_forecast",
            "Reading the price forecast was rejected: token rejected",
        ),
    ],
)
async def test_first_refresh_auth_error_text(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    caplog: pytest.LogCaptureFixture,
    method: str,
    debug_line: str,
) -> None:
    """An AuthError at setup fails it with our auth_failed text; the client's text is at debug."""
    caplog.set_level(logging.DEBUG, logger="custom_components.nortec_go")
    getattr(mock_client, method).side_effect = AuthError("token rejected")
    with patch.object(ConfigEntry, "async_start_reauth_if_available"):
        await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.error_reason_translation_domain == DOMAIN
    assert mock_config_entry.error_reason_translation_key == "auth_failed"
    assert "token rejected" not in (mock_config_entry.reason or "")
    assert debug_line in caplog.text


@pytest.mark.parametrize(
    "error", [VehicleNotFoundError("no car"), MultipleVehiclesError("two cars")]
)
async def test_no_car(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
) -> None:
    """No single car: setup works without a car, logs it once, and the car isn't read again."""
    mock_client.get_vehicle.side_effect = error
    await setup_integration(hass, mock_config_entry)

    coordinator = _coordinator(mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert not coordinator.has_car
    assert coordinator.data.vehicle is None
    assert caplog.text.count("No car entities") == 1
    issue_id = CAR_GONE_ISSUE_ID.format(entry_id=mock_config_entry.entry_id)
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
    assert not coordinator.car_gone

    freezer.tick(INTERVAL_IDLE)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_client.get_vehicle.await_count == 1


@pytest.mark.parametrize(
    ("error", "key"),
    [
        (RateLimitError("too many requests", retry_after=30.0), "rate_limited"),
        (NortecGoConnectionError("network down"), "cannot_connect"),
        (ApiError("GET /example", 500), "api_error"),
        (UnexpectedResponseError("GET /example", "bad shape"), "unexpected_response"),
        (_UnknownClientError("something new"), "car_read_failed"),
    ],
)
@pytest.mark.parametrize(
    "answer", [None, VehicleNotFoundError("no car"), MultipleVehiclesError("two cars")]
)
async def test_car_error_at_setup_retries(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    device_registry: dr.DeviceRegistry,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
    key: str,
    answer: Exception | None,
) -> None:
    """A failed car read at setup retries setup; the retry's answer decides the car device (#41)."""
    caplog.set_level(logging.DEBUG, logger="custom_components.nortec_go")
    identifier = car_device_identifier(str(FAKE_CHARGER_ID))
    mock_client.get_vehicle.side_effect = error
    await setup_integration(hass, mock_config_entry)

    state = mock_config_entry.state  # a local, so mypy doesn't keep the narrowing
    assert state is ConfigEntryState.SETUP_RETRY
    assert mock_config_entry.error_reason_translation_domain == DOMAIN
    assert mock_config_entry.error_reason_translation_key == key
    assert str(error) not in (mock_config_entry.reason or "")
    assert f"Reading the car failed: {error}" in caplog.text
    assert (
        device_registry.async_get_device_by_identifier(
            identifier, mock_config_entry.entry_id
        )
        is None
    )

    mock_client.get_vehicle.side_effect = answer
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=10))
    await hass.async_block_till_done(wait_background_tasks=True)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    coordinator = _coordinator(mock_config_entry)
    has_car = answer is None
    assert coordinator.has_car is has_car
    assert coordinator.data.vehicle == (make_vehicle() if has_car else None)
    device = device_registry.async_get_device_by_identifier(
        identifier, mock_config_entry.entry_id
    )
    assert (device is not None) is has_car


def test_car_read_failed_text() -> None:
    """The setup car read's own text is in the strings."""
    strings = json.loads(
        (
            Path(__file__).parent.parent / "custom_components" / DOMAIN / "strings.json"
        ).read_text(encoding="utf-8")
    )
    assert strings["exceptions"]["car_read_failed"] == {
        "message": "Reading the car failed. Home Assistant will try again."
    }


@pytest.mark.parametrize(
    "error", [NortecGoConnectionError("network down"), AuthError("token rejected")]
)
async def test_failed_setup_car_read_keeps_a_stop_asked(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    error: Exception,
) -> None:
    """A setup that fails on the car read sends no stop and keeps the stored control (D44).

    The setup that then works sends the stop the owner asked for, once.
    """
    key = f"nortec_go.{mock_config_entry.entry_id}.charge_control"
    now = dt_util.utcnow().isoformat()
    stored = {
        "blocked_since": None,
        "block_reason": None,
        "start_pending_since": now,
        "stop_asked_since": now,
        "stop_tries": 0,
        "stop_tried_at": None,
    }
    hass_storage[key] = {
        "version": 1,
        "minor_version": 2,
        "key": key,
        "data": dict(stored),
    }
    mock_client.get_charger.return_value = make_charger(
        is_connected=True, charge_state=ChargeState.CHARGING
    )
    mock_client.get_vehicle.side_effect = error
    with patch.object(ConfigEntry, "async_start_reauth_if_available"):
        await setup_integration(hass, mock_config_entry)

    state = mock_config_entry.state  # a local, so mypy doesn't keep the narrowing
    assert state in (ConfigEntryState.SETUP_RETRY, ConfigEntryState.SETUP_ERROR)
    mock_client.stop_charge.assert_not_awaited()
    # A save is written on a timer; let one that was scheduled land before looking.
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass_storage[key]["data"] == stored

    mock_client.get_vehicle.side_effect = None
    await hass.config_entries.async_reload(mock_config_entry.entry_id)
    # The stop is sent as a background task of the entry.
    await hass.async_block_till_done(wait_background_tasks=True)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    mock_client.stop_charge.assert_awaited_once()


async def test_control_gets_the_charger_read_before_the_car_while_running(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """While running the order is as before: the charge control first, then the car."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    calls: list[str] = []

    async def _get_vehicle() -> Vehicle:
        calls.append("car")
        return make_vehicle()

    mock_client.get_vehicle.side_effect = _get_vehicle
    with patch.object(
        coordinator.charge_control,
        "on_charger_read",
        side_effect=lambda *args: calls.append("control"),
    ):
        await coordinator.async_read_now(with_car=True)

    assert calls == ["control", "car"]


async def test_later_charger_errors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A later charger failure fails the update, skips the car and keeps the interval."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)

    mock_client.get_charger.side_effect = NortecGoConnectionError("network down")
    freezer.tick(INTERVAL_IDLE)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert not coordinator.last_update_success
    assert coordinator.update_interval == INTERVAL_IDLE
    assert mock_client.get_vehicle.await_count == 1


async def test_rate_limit_retry_after(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A later RateLimitError's retry_after sets the next poll (not the 60 min interval)."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)

    mock_client.get_charger.side_effect = RateLimitError(
        "too many requests", retry_after=120.0
    )
    await coordinator.async_refresh()
    assert not coordinator.last_update_success
    reads = mock_client.get_charger.await_count

    # HA rounds timers to whole seconds, so check well before and well after 120 s.
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_client.get_charger.await_count == reads
    freezer.tick(timedelta(seconds=70))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_client.get_charger.await_count == reads + 1


@pytest.mark.parametrize(
    "error",
    [
        ChargerNotFoundError("GET /example: the set charger was not found"),
        UnexpectedResponseError("GET /example", "bad shape"),
    ],
)
async def test_later_permanent_charger_errors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    error: Exception,
) -> None:
    """A later ChargerNotFoundError or UnexpectedResponseError fails the update; the entry stays loaded."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)

    mock_client.get_charger.side_effect = error
    await coordinator.async_refresh()
    assert not coordinator.last_update_success
    assert mock_config_entry.state is ConfigEntryState.LOADED


async def test_unknown_client_error_fails_the_read(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A NortecGoError subclass this integration doesn't know fails the read cleanly."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    mock_client.get_charger.side_effect = _UnknownClientError("something new")
    await coordinator.async_refresh()
    assert not coordinator.last_update_success
    assert isinstance(coordinator.last_exception, UpdateFailed)
    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert "Unexpected error" not in caplog.text


@pytest.mark.parametrize(
    ("error", "error_type", "key", "text"),
    [
        (AuthError("token rejected"), ConfigEntryAuthFailed, "auth_failed", AUTH_TEXT),
        (
            RateLimitError("too many requests", retry_after=30.0),
            UpdateFailed,
            "rate_limited",
            "The Nortec Go service is limiting requests. Home Assistant will read again later",
        ),
        (
            NortecGoConnectionError("network down"),
            UpdateFailed,
            "cannot_connect",
            "Can't reach the Nortec Go service. Home Assistant will try again",
        ),
        (
            ApiError("GET /example", 500),
            UpdateFailed,
            "api_error",
            "The Nortec Go service returned an error. Home Assistant will try again",
        ),
        (
            ChargerNotFoundError("GET /example: the set charger was not found"),
            ConfigEntryError,
            "charger_not_found",
            "The charger is no longer on the Nortec Go account. "
            "Remove the integration and add it again",
        ),
        (
            UnexpectedResponseError("GET /example", "bad shape"),
            ConfigEntryError,
            "unexpected_response",
            "The Nortec Go service sent an answer this integration doesn't understand. "
            "Check for an update of the integration",
        ),
        (
            _UnknownClientError("something new"),
            UpdateFailed,
            "read_failed",
            "Reading the charger failed. Home Assistant will try again",
        ),
    ],
)
async def test_charger_error_texts(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
    error_type: type[HomeAssistantError],
    key: str,
    text: str,
) -> None:
    """A failed charger read raises our translated text; the client's text goes to the debug log."""
    caplog.set_level(logging.DEBUG, logger="custom_components.nortec_go")
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)

    mock_client.get_charger.side_effect = error
    with patch.object(ConfigEntry, "async_start_reauth"):
        await coordinator.async_refresh()

    raised = coordinator.last_exception
    assert isinstance(raised, HomeAssistantError)
    assert type(raised) is error_type
    assert raised.translation_domain == DOMAIN
    assert raised.translation_key == key
    assert str(raised) == text
    assert str(error) not in str(raised)
    assert f"Reading the charger failed: {error}" in caplog.text
    if isinstance(error, RateLimitError):
        assert isinstance(raised, UpdateFailed)
        assert raised.retry_after == 30.0


async def test_later_car_auth_error_text(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A later AuthError from the car raises our auth_failed text; the client's text is at debug."""
    caplog.set_level(logging.DEBUG, logger="custom_components.nortec_go")
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)

    mock_client.get_vehicle.side_effect = AuthError("token rejected")
    with patch.object(ConfigEntry, "async_start_reauth"):
        await coordinator.async_read_now(with_car=True)

    raised = coordinator.last_exception
    assert isinstance(raised, ConfigEntryAuthFailed)
    assert raised.translation_domain == DOMAIN
    assert raised.translation_key == "auth_failed"
    assert str(raised) == AUTH_TEXT
    assert "Reading the car was rejected: token rejected" in caplog.text


async def test_later_price_auth_error_debug_line(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A later price read's AuthError logs the client's text at debug."""
    caplog.set_level(logging.DEBUG, logger="custom_components.nortec_go")
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)

    mock_client.get_price_forecast.side_effect = AuthError("token rejected")
    with patch.object(ConfigEntry, "async_start_reauth"):
        await coordinator.async_read_prices()
    assert "Reading the price forecast was rejected: token rejected" in caplog.text


@pytest.mark.parametrize("method", ["get_charger", "get_vehicle"])
async def test_later_auth_error_starts_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    method: str,
) -> None:
    """A later AuthError from the charger or car starts reauth, and polling stops."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)

    getattr(mock_client, method).side_effect = AuthError("token rejected")
    with patch.object(ConfigEntry, "async_start_reauth") as start_reauth:
        await coordinator.async_read_now(with_car=True)
    start_reauth.assert_called_once()
    mock_client.login.assert_not_awaited()

    reads = mock_client.get_charger.await_count
    freezer.tick(INTERVAL_IDLE * 2)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_client.get_charger.await_count == reads


async def test_later_car_error_keeps_car_data(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A later car error that isn't "no car" keeps the last car data, logs once, and logs the recovery."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)

    mock_client.get_vehicle.side_effect = ApiError("GET /example", 500)
    for _ in range(2):
        await coordinator.async_read_now(with_car=True)
        assert coordinator.last_update_success
        assert coordinator.car_read_failing
        assert not coordinator.car_gone
        assert coordinator.data.vehicle == make_vehicle()
    assert caplog.text.count("Could not read the car") == 1

    mock_client.get_vehicle.side_effect = None
    await coordinator.async_read_now(with_car=True)
    assert "Reading the car works again" in caplog.text


@pytest.mark.parametrize(
    "error", [VehicleNotFoundError("no car"), MultipleVehiclesError("two cars")]
)
async def test_car_gone_while_running(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
) -> None:
    """A "no car" answer while running: no car data, a repair issue, one warning; a good read ends it (D44)."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    issues = ir.async_get(hass)
    issue_id = CAR_GONE_ISSUE_ID.format(entry_id=mock_config_entry.entry_id)
    assert issues.async_get_issue(DOMAIN, issue_id) is None
    assert not coordinator.car_gone

    mock_client.get_vehicle.side_effect = error
    for _ in range(2):
        await coordinator.async_read_now(with_car=True)
        assert coordinator.last_update_success
        assert coordinator.has_car
        assert coordinator.car_gone
        assert coordinator.car_read_failing
        assert coordinator.data.vehicle is None
    assert caplog.text.count("no longer has exactly one car") == 1
    issue = issues.async_get_issue(DOMAIN, issue_id)
    assert issue is not None
    assert issue.translation_key == "car_gone"
    assert issue.severity is ir.IssueSeverity.WARNING
    assert issue.is_fixable
    assert not issue.is_persistent
    assert issue.translation_placeholders == {"name": mock_config_entry.title}
    assert issue.data == {"entry_id": mock_config_entry.entry_id}

    # A read of the charger alone must not bring the old car's data back.
    car_reads = mock_client.get_vehicle.await_count
    await coordinator.async_read_now()
    assert mock_client.get_vehicle.await_count == car_reads
    assert coordinator.data.vehicle is None

    # Another car error keeps it gone, with no second warning.
    mock_client.get_vehicle.side_effect = ApiError("GET /example", 500)
    await coordinator.async_read_now(with_car=True)
    assert coordinator.car_gone
    assert coordinator.data.vehicle is None
    assert "Could not read the car" not in caplog.text

    mock_client.get_vehicle.side_effect = None
    await coordinator.async_read_now(with_car=True)
    assert not coordinator.car_gone
    assert not coordinator.car_read_failing
    assert coordinator.data.vehicle == make_vehicle()
    assert issues.async_get_issue(DOMAIN, issue_id) is None
    assert "Reading the car works again" in caplog.text


async def test_car_gone_warns_after_another_car_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The "no car" warning is logged also when another car error was logged just before."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)

    mock_client.get_vehicle.side_effect = ApiError("GET /example", 500)
    await coordinator.async_read_now(with_car=True)
    assert coordinator.data.vehicle == make_vehicle()
    assert caplog.text.count("Could not read the car") == 1

    mock_client.get_vehicle.side_effect = VehicleNotFoundError("no car")
    await coordinator.async_read_now(with_car=True)
    assert coordinator.car_gone
    assert coordinator.data.vehicle is None
    assert caplog.text.count("no longer has exactly one car") == 1


async def test_car_gone_issue_deleted_at_unload(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """The issue doesn't outlive the loaded entry."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    issues = ir.async_get(hass)
    issue_id = CAR_GONE_ISSUE_ID.format(entry_id=mock_config_entry.entry_id)

    mock_client.get_vehicle.side_effect = VehicleNotFoundError("no car")
    await coordinator.async_read_now(with_car=True)
    assert issues.async_get_issue(DOMAIN, issue_id) is not None

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert issues.async_get_issue(DOMAIN, issue_id) is None


async def test_car_device_follows_another_car(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Another car: the device takes its name and drops a brand and model it lacks; the owner's name stays."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    device = device_registry.async_get_device_by_identifier(
        car_device_identifier(str(FAKE_CHARGER_ID)), mock_config_entry.entry_id
    )
    assert device is not None
    assert (device.manufacturer, device.model) == ("Example", "Model E")
    device_registry.async_update_device(device.id, name_by_user="My car")

    mock_client.get_vehicle.return_value = make_vehicle(
        name="Other car", brand=None, model=""
    )
    await coordinator.async_read_now(with_car=True)

    updated = device_registry.async_get(device.id, include_child_devices=False)
    assert updated is not None
    assert (
        updated.name,
        updated.name_by_user,
        updated.manufacturer,
        updated.model,
    ) == ("Other car", "My car", None, None)


async def test_car_device_updated_on_rename(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    device_registry: dr.DeviceRegistry,
) -> None:
    """A car read with a new name, brand or model updates the car device.

    The empty-name fallback to the translated "Car" needs Task 3's strings; Task 3 tests it.
    """
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    # Task 2 has no device strings yet, so this device starts with the untranslated key as its name;
    # the car read below overwrites it.
    device = device_registry.async_get_or_create(
        config_entry_id=mock_config_entry.entry_id,
        identifiers={car_device_identifier(str(FAKE_CHARGER_ID))},
        translation_key="car",
    )

    mock_client.get_vehicle.return_value = make_vehicle(
        name="Other car", brand="Other", model="Model X"
    )
    await coordinator.async_read_now(with_car=True)
    updated = device_registry.async_get(device.id, include_child_devices=False)
    assert updated is not None
    assert (updated.name, updated.manufacturer, updated.model) == (
        "Other car",
        "Other",
        "Model X",
    )


async def test_charger_device_follows_a_rename(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    device_registry: dr.DeviceRegistry,
) -> None:
    """A rename in the app renames the charger device; an empty name falls back to the title."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    identifier = (DOMAIN, str(FAKE_CHARGER_ID))

    mock_client.get_charger.return_value = make_charger(name="Driveway charger")
    await coordinator.async_refresh()
    device = device_registry.async_get_device_by_identifier(
        identifier, mock_config_entry.entry_id
    )
    assert device is not None
    assert device.name == "Driveway charger"

    mock_client.get_charger.return_value = make_charger(name="")
    await coordinator.async_refresh()
    device = device_registry.async_get_device_by_identifier(
        identifier, mock_config_entry.entry_id
    )
    assert device is not None
    assert device.name == mock_config_entry.title


async def test_charger_rename_before_the_device_exists(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Before the entities create the device, a read creates none."""
    mock_config_entry.add_to_hass(hass)
    coordinator = NortecGoCoordinator(hass, mock_config_entry, mock_client)
    mock_client.get_charger.return_value = make_charger(name="Driveway charger")
    await coordinator.async_refresh()
    assert (
        device_registry.async_get_device_by_identifier(
            (DOMAIN, str(FAKE_CHARGER_ID)), mock_config_entry.entry_id
        )
        is None
    )


async def test_prices_read_at_the_five_times(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Prices are read at setup and at 00:05, 05:05, 10:05, 15:05, 20:05 local, not in between."""
    freezer.move_to(MIDNIGHT - timedelta(minutes=30))  # 23:30 local
    await setup_integration(hass, mock_config_entry)
    assert mock_client.get_price_forecast.await_count == 1

    reads = 1
    for hours in range(24):
        for minute in (0, 5, 30):
            when = MIDNIGHT + timedelta(hours=hours, minutes=minute)
            freezer.move_to(when)
            async_fire_time_changed(hass, when)
            await hass.async_block_till_done()
            local_hour = when.astimezone(dt_util.get_default_time_zone()).hour
            if minute == 5 and local_hour in (0, 5, 10, 15, 20):
                reads += 1
            assert mock_client.get_price_forecast.await_count == reads, when
    assert reads == 6


async def test_price_read_merges_and_saves(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """A price read merges into the known slots, prunes yesterday and saves."""
    freezer.move_to(MIDNIGHT + timedelta(hours=10))
    mock_client.get_price_forecast.return_value = make_forecast(MIDNIGHT, [1.0, 2.0])
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    assert coordinator.known_prices == {
        MIDNIGHT: 1.0,
        MIDNIGHT + timedelta(minutes=15): 2.0,
    }
    data = hass_storage[STORE_KEY.format(mock_config_entry.entry_id)]["data"]
    assert data["currency"] == "DKK"
    assert coordinator.price_currency == "DKK"
    assert [slot["price"] for slot in data["slots"]] == [1.0, 2.0]


async def test_stored_prices_loaded_at_setup(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """Stored slots of today are loaded; yesterday's are dropped; a failed read keeps them."""
    freezer.move_to(MIDNIGHT + timedelta(hours=10))
    key = STORE_KEY.format(mock_config_entry.entry_id)
    hass_storage[key] = {
        "version": 2,
        "minor_version": 1,
        "key": key,
        "data": {
            "currency": "DKK",
            "slots": [
                {"start": "2026-09-26T21:45:00+00:00", "price": 9.0},
                {"start": "2026-09-26T22:00:00+00:00", "price": 1.0},
            ],
        },
    }
    mock_client.get_price_forecast.side_effect = NortecGoConnectionError("network down")
    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert _coordinator(mock_config_entry).known_prices == {MIDNIGHT: 1.0}
    assert _coordinator(mock_config_entry).price_currency == "DKK"


async def test_version_1_store_migrates_at_setup(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """A version 1 store (spot prices) loads as empty; the setup's read refills it as version 2."""
    freezer.move_to(MIDNIGHT + timedelta(hours=10))
    key = STORE_KEY.format(mock_config_entry.entry_id)
    hass_storage[key] = {
        "version": 1,
        "minor_version": 1,
        "key": key,
        "data": {"slots": [{"start": "2026-09-26T22:00:00+00:00", "price": 9.0}]},
    }
    mock_client.get_price_forecast.return_value = make_forecast(
        MIDNIGHT + timedelta(hours=10), [2.0]
    )
    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    coordinator = _coordinator(mock_config_entry)
    assert coordinator.known_prices == {MIDNIGHT + timedelta(hours=10): 2.0}
    assert hass_storage[key]["version"] == 2
    assert hass_storage[key]["data"]["currency"] == "DKK"


async def test_price_currency_kept_when_forecast_has_none(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    hass_storage: dict[str, Any],
) -> None:
    """A forecast without a currency keeps the last known one, in memory and stored."""
    mock_client.get_price_forecast.return_value = make_forecast(MIDNIGHT, [1.0])
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)

    mock_client.get_price_forecast.return_value = make_forecast(
        MIDNIGHT, [1.0], currency=None
    )
    await coordinator.async_read_prices()
    assert coordinator.price_currency == "DKK"
    data = hass_storage[STORE_KEY.format(mock_config_entry.entry_id)]["data"]
    assert data["currency"] == "DKK"


async def test_failed_price_read_keeps_slots(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failed scheduled read logs a warning and keeps the known slots."""
    freezer.move_to(MIDNIGHT + timedelta(hours=1))
    mock_client.get_price_forecast.return_value = make_forecast(MIDNIGHT, [1.0])
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)

    mock_client.get_price_forecast.side_effect = UnexpectedResponseError(
        "GET /example", "gap"
    )
    await coordinator.async_read_prices()
    assert coordinator.known_prices == {MIDNIGHT: 1.0}
    assert "Could not read the price forecast" in caplog.text


async def test_later_price_auth_error_starts_reauth(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """An AuthError in a scheduled price read starts reauth, without logging in."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)

    mock_client.get_price_forecast.side_effect = AuthError("token rejected")
    with patch.object(ConfigEntry, "async_start_reauth") as start_reauth:
        await coordinator.async_read_prices()
    start_reauth.assert_called_once()
    mock_client.login.assert_not_awaited()


async def test_price_read_raises_when_asked(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A failed price read asked to raise raises our text, after marking the reads as failing."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)

    error = NortecGoConnectionError("network down")
    mock_client.get_price_forecast.side_effect = error
    with pytest.raises(HomeAssistantError) as exc_info:
        await coordinator.async_read_prices(raise_on_failure=True)

    raised = exc_info.value
    assert type(raised) is HomeAssistantError
    assert raised.translation_domain == DOMAIN
    assert raised.translation_key == "price_read_failed"
    assert raised.__cause__ is error
    assert coordinator.price_read_failing is True


async def test_price_read_auth_error_raises_when_asked(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A rejected price read asked to raise starts reauth first, then raises auth_failed."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)

    error = AuthError("token rejected")
    mock_client.get_price_forecast.side_effect = error
    with (
        patch.object(ConfigEntry, "async_start_reauth") as start_reauth,
        pytest.raises(HomeAssistantError) as exc_info,
    ):
        await coordinator.async_read_prices(raise_on_failure=True)

    raised = exc_info.value
    assert type(raised) is HomeAssistantError
    assert raised.translation_domain == DOMAIN
    assert raised.translation_key == "auth_failed"
    assert raised.__cause__ is error
    start_reauth.assert_called_once()
    mock_client.login.assert_not_awaited()


@pytest.mark.parametrize("retry_on_failure", [False, True])
async def test_price_read_raises_nothing_by_default(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    retry_on_failure: bool,
) -> None:
    """A failed price read that isn't asked to raise raises nothing, as before."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)

    mock_client.get_price_forecast.side_effect = NortecGoConnectionError("network down")
    await coordinator.async_read_prices(retry_on_failure=retry_on_failure)
    assert coordinator.price_read_failing is True

    mock_client.get_price_forecast.side_effect = AuthError("token rejected")
    with patch.object(ConfigEntry, "async_start_reauth") as start_reauth:
        await coordinator.async_read_prices(retry_on_failure=retry_on_failure)
    start_reauth.assert_called_once()


async def _at(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, when: datetime
) -> None:
    """Move the clock to when and run what is due, background tasks included."""
    freezer.move_to(when)
    async_fire_time_changed(hass, when)
    await hass.async_block_till_done(wait_background_tasks=True)


def _local(hours: int, minutes: int = 0) -> datetime:
    """A local time on 2026-09-27, in UTC."""
    return MIDNIGHT + timedelta(hours=hours, minutes=minutes)


@pytest.mark.parametrize(
    "error",
    [
        NortecGoConnectionError("network down"),
        UnexpectedResponseError("GET /example", "gap"),
    ],
)
async def test_failed_scheduled_price_read_retries_once(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    error: NortecGoError,
) -> None:
    """A failed 15:05 read is read once more at 15:20, and then not until 20:05."""
    freezer.move_to(_local(15))
    await setup_integration(hass, mock_config_entry)
    forecast = mock_client.get_price_forecast
    mock_client.get_price_forecast.side_effect = error

    await _at(hass, freezer, _local(15, 5))
    assert forecast.await_count == 2
    await _at(hass, freezer, _local(15, 19))
    assert forecast.await_count == 2
    await _at(hass, freezer, _local(15, 20))
    assert forecast.await_count == 3
    await _at(hass, freezer, _local(15, 35))
    await _at(hass, freezer, _local(20, 4))
    assert forecast.await_count == 3
    await _at(hass, freezer, _local(20, 5))
    assert forecast.await_count == 4


async def test_successful_refresh_cancels_price_retry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A successful read (Refresh) cancels a pending retry."""
    freezer.move_to(_local(15))
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    mock_client.get_price_forecast.side_effect = NortecGoConnectionError("network down")
    await _at(hass, freezer, _local(15, 5))

    mock_client.get_price_forecast.side_effect = None
    freezer.move_to(_local(15, 10))
    await coordinator.async_read_prices()
    assert mock_client.get_price_forecast.await_count == 3
    await _at(hass, freezer, _local(15, 20))
    assert mock_client.get_price_forecast.await_count == 3


async def test_failed_refresh_keeps_a_pending_retry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A failed Refresh schedules no retry of its own and leaves a pending one."""
    freezer.move_to(_local(12))
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    forecast = mock_client.get_price_forecast
    forecast.side_effect = NortecGoConnectionError("network down")

    await coordinator.async_read_prices()
    assert forecast.await_count == 2
    await _at(hass, freezer, _local(12, 15))
    assert forecast.await_count == 2

    await _at(hass, freezer, _local(15, 5))
    assert forecast.await_count == 3
    freezer.move_to(_local(15, 10))
    await coordinator.async_read_prices()
    assert forecast.await_count == 4
    await _at(hass, freezer, _local(15, 20))
    assert forecast.await_count == 5
    await _at(hass, freezer, _local(15, 35))
    assert forecast.await_count == 5


async def test_failed_setup_read_near_a_read_time_gets_no_retry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A failed setup read at 14:55 gets no retry: the 15:05 read comes first."""
    freezer.move_to(_local(14, 55))
    mock_client.get_price_forecast.side_effect = NortecGoConnectionError("network down")
    await setup_integration(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.LOADED
    forecast = mock_client.get_price_forecast
    assert forecast.await_count == 1

    await _at(hass, freezer, _local(15, 4))
    assert forecast.await_count == 1
    await _at(hass, freezer, _local(15, 5))
    assert forecast.await_count == 2
    await _at(hass, freezer, _local(15, 10))
    assert forecast.await_count == 2
    await _at(hass, freezer, _local(15, 20))
    assert forecast.await_count == 3


@pytest.mark.parametrize(
    ("retry_after", "retry_minutes"),
    [(1800.0, 30), (60.0, 15), (None, 15), (18000.0, None)],
)
async def test_rate_limited_price_read_retry_delay(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    retry_after: float | None,
    retry_minutes: int | None,
) -> None:
    """The retry waits the longer of 15 minutes and retry_after, and is dropped if it reaches 20:05."""
    freezer.move_to(_local(15))
    await setup_integration(hass, mock_config_entry)
    forecast = mock_client.get_price_forecast
    forecast.side_effect = RateLimitError("too many requests", retry_after=retry_after)
    await _at(hass, freezer, _local(15, 5))
    assert forecast.await_count == 2

    for minutes in range(10, 300, 5):  # 15:15 to 20:00
        await _at(hass, freezer, _local(15, 5 + minutes))
        retried = retry_minutes is not None and minutes >= retry_minutes
        assert forecast.await_count == (3 if retried else 2), minutes


async def test_no_retry_due_at_the_next_read(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A retry that would be due at the next read time is not scheduled."""
    freezer.move_to(_local(12))
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    forecast = mock_client.get_price_forecast
    forecast.side_effect = NortecGoConnectionError("network down")
    # The next read time is exactly when the retry would be due; no scheduled read runs then.
    with patch(
        "custom_components.nortec_go.coordinator.next_price_read",
        return_value=_local(12, 15),
    ):
        await coordinator.async_read_prices(retry_on_failure=True)
    await _at(hass, freezer, _local(12, 15))
    assert forecast.await_count == 2


async def test_price_auth_error_schedules_no_retry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """An AuthError in a scheduled read starts reauth, with no retry and no login."""
    freezer.move_to(_local(15))
    await setup_integration(hass, mock_config_entry)
    mock_client.get_price_forecast.side_effect = AuthError("token rejected")
    with patch.object(ConfigEntry, "async_start_reauth") as start_reauth:
        await _at(hass, freezer, _local(15, 5))
        await _at(hass, freezer, _local(15, 20))
    assert mock_client.get_price_forecast.await_count == 2
    start_reauth.assert_called_once()
    mock_client.login.assert_not_awaited()


async def test_price_auth_error_on_the_retry_starts_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """An AuthError in the retry starts reauth, without logging in."""
    freezer.move_to(_local(15))
    await setup_integration(hass, mock_config_entry)
    mock_client.get_price_forecast.side_effect = NortecGoConnectionError("network down")
    await _at(hass, freezer, _local(15, 5))

    mock_client.get_price_forecast.side_effect = AuthError("token rejected")
    with patch.object(ConfigEntry, "async_start_reauth") as start_reauth:
        await _at(hass, freezer, _local(15, 20))
    assert mock_client.get_price_forecast.await_count == 3
    start_reauth.assert_called_once()
    mock_client.login.assert_not_awaited()


async def test_price_auth_error_cancels_a_pending_retry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """An AuthError (here in a Refresh) cancels a pending retry."""
    freezer.move_to(_local(15))
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    mock_client.get_price_forecast.side_effect = NortecGoConnectionError("network down")
    await _at(hass, freezer, _local(15, 5))

    mock_client.get_price_forecast.side_effect = AuthError("token rejected")
    freezer.move_to(_local(15, 10))
    with patch.object(ConfigEntry, "async_start_reauth"):
        await coordinator.async_read_prices()
    mock_client.get_price_forecast.side_effect = None
    await _at(hass, freezer, _local(15, 20))
    assert mock_client.get_price_forecast.await_count == 3


async def test_scheduled_read_cancels_a_pending_retry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A scheduled read cancels a pending retry, also when it schedules none of its own."""
    freezer.move_to(_local(14, 55))
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    forecast = mock_client.get_price_forecast
    forecast.side_effect = NortecGoConnectionError("network down")
    # Let the too-late check pass, so a retry is pending for 15:10, past the 15:05 read.
    with patch(
        "custom_components.nortec_go.coordinator.next_price_read",
        return_value=_local(24),
    ):
        await coordinator.async_read_prices(retry_on_failure=True)
    assert forecast.await_count == 2

    # retry_after reaches 20:05, so the 15:05 read schedules no retry of its own.
    forecast.side_effect = RateLimitError("too many requests", retry_after=18000.0)
    await _at(hass, freezer, _local(15, 5))
    assert forecast.await_count == 3
    await _at(hass, freezer, _local(15, 10))
    assert forecast.await_count == 3


async def test_price_log_run(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A run of failed price reads logs one warning, then debug; its end logs one info line."""
    caplog.set_level(logging.DEBUG, logger="custom_components.nortec_go")
    freezer.move_to(_local(12))
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    assert "Reading the price forecast works again" not in caplog.text

    mock_client.get_price_forecast.side_effect = NortecGoConnectionError("network down")
    await coordinator.async_read_prices()
    await coordinator.async_read_prices()
    failures = [
        record.levelno
        for record in caplog.records
        if record.getMessage().startswith("Could not read the price forecast")
    ]
    assert failures == [logging.WARNING, logging.DEBUG]

    mock_client.get_price_forecast.side_effect = None
    await coordinator.async_read_prices()
    await coordinator.async_read_prices()
    recoveries = [
        record.levelno
        for record in caplog.records
        if record.getMessage() == "Reading the price forecast works again"
    ]
    assert recoveries == [logging.INFO]


async def test_tick_updates_listeners_without_api_calls(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The quarter-hour tick calls the listeners and makes no API call."""
    freezer.move_to(MIDNIGHT + timedelta(hours=1, minutes=10))
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    calls = []
    coordinator.async_add_listener(lambda: calls.append(1))

    when = MIDNIGHT + timedelta(hours=1, minutes=15)
    freezer.move_to(when)
    async_fire_time_changed(hass, when)
    await hass.async_block_till_done()
    assert calls == [1]
    assert mock_client.get_charger.await_count == 1
    assert mock_client.get_price_forecast.await_count == 1


def test_car_device_identifier() -> None:
    """The car device is keyed on the charger."""
    assert car_device_identifier("123") == (DOMAIN, "123_car")


async def test_data_carries_the_control_snapshot(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """NortecGoData.control is the control's snapshot."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    assert coordinator.data.control == ChargeControlState()


async def test_interval_while_start_pending(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A pending start reads every 30 s."""
    mock_client.get_charger.return_value = make_charger(is_connected=True)
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    await coordinator.charge_control.async_start()
    await hass.async_block_till_done()
    assert coordinator.update_interval == INTERVAL_CHANGING
    assert coordinator.data.control.start_pending


async def test_read_counter_handoff(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A read that began before a start attempt doesn't end the pending start (Review Focus 1)."""
    mock_client.get_charger.return_value = make_charger(is_connected=True)
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    control = coordinator.charge_control
    read_started = asyncio.Event()
    release_read = asyncio.Event()

    async def slow_get_charger() -> Any:
        read_started.set()
        await release_read.wait()
        return make_charger(
            is_connected=False
        )  # would end the pending start if trusted

    mock_client.get_charger.side_effect = slow_get_charger
    refresh = hass.async_create_task(coordinator.async_refresh())
    await read_started.wait()
    mock_client.get_charger.side_effect = None
    await control.async_start()
    release_read.set()
    await refresh
    assert control.state.start_pending


async def test_timeout_on_unchanged_read_updates_entities(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The start timer's block reaches listeners even when the reads don't change."""
    mock_client.get_charger.return_value = make_charger(is_connected=True)
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    await coordinator.charge_control.async_start()
    await hass.async_block_till_done()
    listener = MagicMock()
    coordinator.async_add_listener(listener)
    freezer.tick(START_CONFIRM_TIMEOUT)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert coordinator.data.control.blocked
    listener.assert_called()


async def test_stop_after_failed_read_keeps_others_unavailable(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A stop after a failed read doesn't mark the coordinator successful (Review Focus 4)."""
    mock_client.get_charger.return_value = make_charger(
        is_connected=True, charge_state=ChargeState.CHARGING
    )
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    mock_client.get_charger.side_effect = NortecGoConnectionError("x")
    await coordinator.async_refresh()
    assert not coordinator.last_update_success
    # A change outside a read, before any read.
    coordinator.charge_control._on_change()  # noqa: SLF001
    assert not coordinator.last_update_success
    await coordinator.charge_control.async_stop()
    await hass.async_block_till_done()
    mock_client.stop_charge.assert_awaited_once()
    assert not coordinator.last_update_success
    state = hass.states.get("binary_sensor.garage_charger_charging")
    assert state is not None
    assert state.state == "unavailable"


async def test_control_change_before_the_first_read_is_ignored(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A control change before any data exists doesn't make up data or call listeners."""
    mock_config_entry.add_to_hass(hass)
    coordinator = NortecGoCoordinator(hass, mock_config_entry, mock_client)
    listener = MagicMock()
    remove_listener = coordinator.async_add_listener(listener)
    coordinator.charge_control._on_change()  # noqa: SLF001
    remove_listener()  # also stops the poll the first listener scheduled
    assert coordinator.data is None
    listener.assert_not_called()


async def test_actions_within_the_cooldown_each_read_right_away(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A start and a stop within HA's 10 s debounce cooldown each read at once (Review Focus 4)."""
    mock_client.get_charger.return_value = make_charger(is_connected=True)
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    calls = mock_client.get_charger.await_count
    await coordinator.charge_control.async_start()
    await hass.async_block_till_done()
    assert mock_client.get_charger.await_count == calls + 1
    await (
        coordinator.charge_control.async_stop()
    )  # a stop asked during the pending start
    await hass.async_block_till_done()
    assert mock_client.get_charger.await_count == calls + 2


async def test_start_whose_read_fails_is_read_again_after_30_s(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The control change sets the 30 s interval before its read, so a failed read retries soon (Review Focus 2)."""
    mock_client.get_charger.return_value = make_charger(is_connected=True)
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    mock_client.get_charger.side_effect = NortecGoConnectionError("x")
    await coordinator.charge_control.async_start()
    await hass.async_block_till_done()
    assert not coordinator.last_update_success
    assert coordinator.update_interval == INTERVAL_CHANGING
    mock_client.get_charger.side_effect = None
    calls = mock_client.get_charger.await_count
    freezer.tick(
        INTERVAL_CHANGING + timedelta(seconds=1)
    )  # HA adds a sub-second offset
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_client.get_charger.await_count == calls + 1


async def test_car_skipped_on_fast_reads(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """30 s reads skip the car until its last try is 4.5 minutes old."""
    mock_client.get_charger.return_value = make_charger(
        is_connected=True, charge_state=ChargeState.STARTING
    )
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    assert coordinator.update_interval == INTERVAL_CHANGING
    vehicles = mock_client.get_vehicle.await_count
    chargers = mock_client.get_charger.await_count
    # Direct refreshes: HA's timer adds a random sub-second offset, and the car rule is
    # about the clock, not the timer.
    for _ in range(8):  # 4 minutes of 30 s reads
        freezer.tick(INTERVAL_CHANGING)
        await coordinator.async_refresh()
    assert mock_client.get_charger.await_count == chargers + 8
    assert mock_client.get_vehicle.await_count == vehicles
    freezer.tick(INTERVAL_CHANGING)  # 4.5 minutes after the last car read
    await coordinator.async_refresh()
    assert mock_client.get_vehicle.await_count == vehicles + 1


async def test_car_read_on_an_early_charging_read(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A 5-minute read that comes a second early still reads the car (Review Focus 3)."""
    mock_client.get_charger.return_value = make_charger(
        is_connected=True, charge_state=ChargeState.CHARGING
    )
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    vehicles = mock_client.get_vehicle.await_count
    freezer.tick(INTERVAL_CHARGING - timedelta(seconds=1))
    await coordinator.async_refresh()
    assert mock_client.get_vehicle.await_count == vehicles + 1


async def test_read_now_with_car(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """async_read_now skips a fresh car unless asked; the read that reads it clears the ask."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    vehicles = mock_client.get_vehicle.await_count
    await coordinator.async_read_now()
    assert mock_client.get_vehicle.await_count == vehicles
    await coordinator.async_read_now(with_car=True)
    assert mock_client.get_vehicle.await_count == vehicles + 1
    await coordinator.async_read_now()
    assert mock_client.get_vehicle.await_count == vehicles + 1


async def test_read_at_on_every_read(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Each successful read stamps read_at, so listeners hear of a read with unchanged data."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    first = coordinator.data.read_at
    listener = MagicMock()
    coordinator.async_add_listener(listener)
    freezer.tick(timedelta(seconds=5))
    await coordinator.async_refresh()
    assert coordinator.data.read_at == first + timedelta(seconds=5)
    listener.assert_called()


async def test_read_at_kept_on_a_control_change(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A change outside a read keeps the last read's time."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    read_at = coordinator.data.read_at
    coordinator.charge_control._on_change()  # noqa: SLF001
    assert coordinator.data.read_at == read_at


def _switch(hass: HomeAssistant) -> str:
    """The Charge switch's state."""
    state = hass.states.get("switch.garage_charger_charge")
    assert state is not None
    return state.state


_STARTING = make_charger(is_connected=True, charge_state=ChargeState.STARTING)
_STOPPING = make_charger(is_connected=True, charge_state=ChargeState.STOPPING)


@pytest.mark.parametrize(
    ("charger", "control", "age", "interval"),
    [
        (
            _STOPPING,
            ChargeControlState(),
            FAST_READ_MAX_AGE - timedelta(seconds=1),
            INTERVAL_CHANGING,
        ),
        (_STOPPING, ChargeControlState(), FAST_READ_MAX_AGE, INTERVAL_CHARGING),
        (_STARTING, ChargeControlState(), FAST_READ_MAX_AGE, INTERVAL_CHARGING),
        (
            _STARTING,
            ChargeControlState(start_pending=True),
            timedelta(minutes=9),
            INTERVAL_CHANGING,
        ),
        (
            make_charger(is_connected=True, charge_state=ChargeState.CHARGING),
            ChargeControlState(stop_pending=True),
            timedelta(minutes=1, seconds=50),
            INTERVAL_CHANGING,
        ),
        (
            make_charger(is_connected=True),
            ChargeControlState(start_pending=True),
            timedelta(minutes=9),
            INTERVAL_CHANGING,
        ),
        (_STOPPING, ChargeControlState(blocked=True), timedelta(0), INTERVAL_IDLE),
        (
            make_charger(is_connected=True, state=ChargerState.UNKNOWN),
            ChargeControlState(),
            timedelta(0),
            INTERVAL_IDLE,
        ),
        (
            make_charger(is_connected=True),
            ChargeControlState(),
            timedelta(hours=5),
            INTERVAL_IDLE,
        ),
    ],
)
def test_interval_for_by_read_age(
    charger: Any, control: ChargeControlState, age: timedelta, interval: timedelta
) -> None:
    """Our own pending states keep 30 s; the charger's own starting or stopping only while the read is fresh (D31)."""
    assert interval_for(charger, control, age) == interval


async def test_charger_stopping_during_an_outage_slows_down(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The charger's own STOPPING gives 30 s reads for about 2 minutes of an outage, then 5 min (Review Focus 5)."""
    mock_client.get_charger.return_value = _STOPPING
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    assert coordinator.update_interval == INTERVAL_CHANGING
    mock_client.get_charger.side_effect = NortecGoConnectionError("network down")
    freezer.tick(INTERVAL_CHANGING + timedelta(seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert not coordinator.last_update_success
    assert coordinator.update_interval == INTERVAL_CHANGING
    freezer.tick(timedelta(minutes=2))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert coordinator.update_interval == INTERVAL_CHARGING


async def test_pending_stop_during_an_outage_ends_at_2_minutes(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """With reads failing, the pending stop ends at 2 minutes: the switch shows the last read, reads every 5 min."""
    mock_client.get_charger.return_value = make_charger(
        is_connected=True,
        charge_state=ChargeState.CHARGING,
        state=ChargerState.BUSY_CHARGING,
    )
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    mock_client.get_charger.side_effect = NortecGoConnectionError("network down")
    await coordinator.charge_control.async_stop()
    await hass.async_block_till_done()
    assert coordinator.data.control.stop_pending
    assert _switch(hass) == "off"
    freezer.tick(STOP_CONFIRM_TIMEOUT)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert not coordinator.data.control.stop_pending
    assert _switch(hass) == "on"
    assert coordinator.update_interval == INTERVAL_CHARGING


async def test_pending_start_during_an_outage_blocks_at_10_minutes(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """With reads failing, the pending start ends at 10 minutes with the block, and reads every 60 min."""
    mock_client.get_charger.return_value = make_charger(is_connected=True)
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    mock_client.get_charger.side_effect = NortecGoConnectionError("network down")
    await coordinator.charge_control.async_start()
    await hass.async_block_till_done()
    assert coordinator.update_interval == INTERVAL_CHANGING
    freezer.tick(START_CONFIRM_TIMEOUT)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert coordinator.data.control.blocked
    assert coordinator.update_interval == INTERVAL_IDLE
    assert _switch(hass) == "off"


async def test_control_change_during_an_outage_keeps_the_read_age(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A control change works the interval out from the last good read's real age."""
    mock_client.get_charger.return_value = _STOPPING
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    mock_client.get_charger.side_effect = NortecGoConnectionError("network down")
    freezer.tick(timedelta(minutes=3))
    coordinator.charge_control._on_change()  # noqa: SLF001
    assert coordinator.update_interval == INTERVAL_CHARGING


async def test_rate_limit_retry_after_beats_the_fast_interval(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A RateLimitError's retry_after wins over the 30 s the failed read works out."""
    mock_client.get_charger.return_value = _STOPPING
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    mock_client.get_charger.side_effect = RateLimitError(
        "too many requests", retry_after=120.0
    )
    await coordinator.async_refresh()
    reads = mock_client.get_charger.await_count
    # HA rounds timers to whole seconds, so check well before and well after 120 s.
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_client.get_charger.await_count == reads
    freezer.tick(timedelta(seconds=70))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_client.get_charger.await_count == reads + 1


def _charging(kwh: float) -> Charger:
    """A charger with a charge open at the given energy."""
    return make_charger(
        is_connected=True, charge_state=ChargeState.CHARGING, charge_kwh=kwh
    )


async def test_first_setup_creates_and_saves_the_energy_ledger(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """With no stored ledger, setup makes one that starts now and saves it before any charge."""
    freezer.move_to(MIDNIGHT)
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    key = ENERGY_STORE_KEY.format(mock_config_entry.entry_id)
    assert hass_storage[key]["version"] == 1
    assert hass_storage[key]["data"] == {
        "since": "2026-09-26T22:00:00+00:00",
        "settled_kwh": 0.0,
        "settled_id": None,
        "settled_at": None,
        "provisional": [],
    }
    assert coordinator.energy_ledger.since == MIDNIGHT
    assert coordinator.data.total_energy_kwh == 0.0


async def test_stored_energy_ledger_loaded_at_setup(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """A stored ledger is loaded, and a charge open across the restart carries on from it."""
    freezer.move_to(MIDNIGHT)
    key = ENERGY_STORE_KEY.format(mock_config_entry.entry_id)
    hass_storage[key] = {
        "version": 1,
        "minor_version": 1,
        "key": key,
        "data": {
            "since": "2026-09-20T08:00:00+00:00",
            "settled_kwh": 40.0,
            "settled_id": "fake-earlier-charge-id",
            "settled_at": "2026-09-25T06:15:00+00:00",
            "provisional": [
                {
                    "id": FAKE_CHARGE_ID,
                    "kwh": 2.0,
                    "seen_at": "2026-09-26T21:55:00+00:00",
                }
            ],
        },
    }
    mock_client.get_charger.return_value = _charging(3.5)
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    assert coordinator.data.total_energy_kwh == 43.5
    assert coordinator.energy_ledger.since == datetime(2026, 9, 20, 8, 0, tzinfo=UTC)
    assert hass_storage[key]["data"]["provisional"] == [
        {"id": FAKE_CHARGE_ID, "kwh": 3.5, "seen_at": "2026-09-26T22:00:00+00:00"}
    ]


async def test_energy_ledger_saved_only_when_it_changes(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A read that changes nothing doesn't save; a read with an open charge does."""
    freezer.move_to(MIDNIGHT)
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    with patch.object(EnergyStore, "async_save", autospec=True) as save:
        freezer.tick(INTERVAL_IDLE)
        await coordinator.async_refresh()
        save.assert_not_awaited()
        assert coordinator.data.total_energy_kwh == 0.0

        mock_client.get_charger.return_value = _charging(1.0)
        freezer.tick(INTERVAL_IDLE)
        await coordinator.async_refresh()
        save.assert_awaited_once()
        assert coordinator.data.total_energy_kwh == 1.0


async def test_failed_reads_leave_the_energy_ledger(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """A failed charger read, and a read whose car read is rejected, move nothing."""
    freezer.move_to(MIDNIGHT)
    mock_client.get_charger.return_value = _charging(1.0)
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    key = ENERGY_STORE_KEY.format(mock_config_entry.entry_id)
    ledger = coordinator.energy_ledger
    stored = copy.deepcopy(hass_storage[key]["data"])

    freezer.tick(INTERVAL_CHARGING)
    mock_client.get_charger.side_effect = NortecGoConnectionError("network down")
    await coordinator.async_refresh()
    assert not coordinator.last_update_success
    assert coordinator.energy_ledger is ledger
    assert hass_storage[key]["data"] == stored

    mock_client.get_charger.side_effect = None
    mock_client.get_charger.return_value = _charging(2.0)
    mock_client.get_vehicle.side_effect = AuthError("token rejected")
    freezer.tick(INTERVAL_CHARGING)
    with patch.object(ConfigEntry, "async_start_reauth"):
        await coordinator.async_read_now(with_car=True)
    assert coordinator.energy_ledger is ledger
    assert hass_storage[key]["data"] == stored
    assert coordinator.data.total_energy_kwh == 1.0


async def test_wrong_shaped_energy_store_starts_a_new_ledger(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A stored ledger of the wrong shape is replaced by a new one that starts at 0."""
    freezer.move_to(MIDNIGHT)
    key = ENERGY_STORE_KEY.format(mock_config_entry.entry_id)
    hass_storage[key] = {
        "version": 1,
        "minor_version": 1,
        "key": key,
        "data": {"since": "nonsense"},
    }
    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert _coordinator(mock_config_entry).data.total_energy_kwh == 0.0
    assert hass_storage[key]["data"]["since"] == "2026-09-26T22:00:00+00:00"
    assert "Ignoring the stored energy total" in caplog.text


async def test_control_change_during_the_energy_save_is_kept(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A stop that returns while the ledger is saved is in the data the read returns."""
    freezer.move_to(MIDNIGHT)
    mock_client.get_charger.return_value = _charging(1.0)
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    control = coordinator.charge_control
    assert _switch(hass) == "on"

    async def _save(store: EnergyStore, ledger: EnergyLedger) -> None:
        # The stop returns while the ledger is written. The read it asks for fails, so only
        # the read under test can carry the change.
        await control.async_stop()
        mock_client.get_charger.side_effect = NortecGoConnectionError("network down")

    freezer.tick(INTERVAL_CHARGING)
    mock_client.get_charger.return_value = _charging(2.0)
    with patch.object(EnergyStore, "async_save", _save):
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    mock_client.stop_charge.assert_awaited_once()
    assert control.state.stop_pending
    assert coordinator.data.control == control.state
    assert _switch(hass) == "off"
