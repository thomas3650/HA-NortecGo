"""Tests for the Nortec Go diagnostics: only the sign-in secrets are redacted (D38)."""

from dataclasses import fields
from datetime import UTC, datetime
from http import HTTPStatus
import json
from typing import Any
from unittest.mock import AsyncMock

from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import CONF_DEVICE_ID, CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pynortecgo import (
    ActiveCharge,
    Charger,
    ChargerNotFoundError,
    ChargerState,
    ChargeState,
    CompletedCharge,
    NortecGoConnectionError,
    Vehicle,
    VehicleNotFoundError,
)
import pytest
from pytest_homeassistant_custom_component.common import (
    CLIENT_ID,
    MockConfigEntry,
    MockUser,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.nortec_go.const import DOMAIN
from custom_components.nortec_go.entry import tokens_to_data

from .conftest import (
    DEFAULT_FORECAST_START,
    FAKE_CHARGE_ID,
    FAKE_CHARGER_ID,
    FAKE_CHARGER_NAME,
    FAKE_DEVICE_ID,
    FAKE_EMAIL,
    FAKE_LAST_CHARGE_ID,
    FAKE_PASSWORD,
    FAKE_TOKENS,
    FAKE_VEHICLE_NAME,
    NEW_TOKENS,
    make_charger,
    make_completed_charge,
    make_forecast,
    setup_integration,
)

# 2026-09-27 12:00 local (CEST): conftest's forecast slots (2026-09-27 00:00 to 02:00 local) are
# today's, and a price retry at 12:15 comes before the 15:05 read.
NOON = datetime(2026, 9, 27, 10, 0, tzinfo=UTC)
REDACTED = "**REDACTED**"
# strings.json exceptions, without the final period (HA strips it).
CANNOT_CONNECT = "Can't reach the Nortec Go service. Home Assistant will try again"
CHARGER_NOT_FOUND = (
    "The charger is no longer on the Nortec Go account. "
    "Remove the integration and add it again"
)
SECRETS = (
    FAKE_EMAIL,
    FAKE_PASSWORD,
    FAKE_DEVICE_ID,
    FAKE_TOKENS.access_token,
    FAKE_TOKENS.refresh_token,
    NEW_TOKENS.access_token,
    NEW_TOKENS.refresh_token,
)
ENTRY = {
    "title": FAKE_CHARGER_NAME,
    "unique_id": str(FAKE_CHARGER_ID),
    "data": {
        "email": REDACTED,
        "device_id": REDACTED,
        "access_token": REDACTED,
        "refresh_token": REDACTED,
        "expires_at": "2030-01-01T12:00:00+00:00",
    },
    "options": {},
}
# The pynortecgo fields the download shows. A client bump that changes them fails
# test_client_model_fields_are_pinned: decide for each new field whether it is a secret (D38).
CHARGER_FIELDS = {
    "id",
    "name",
    "max_kw",
    "state",
    "state_raw",
    "is_connected",
    "currency",
    "active_charge",
    "last_charge",
}
ACTIVE_CHARGE_FIELDS = {"id", "state", "state_raw", "can_stop", "kwh", "kw", "cost"}
COMPLETED_CHARGE_FIELDS = {"id", "cost", "kwh", "completed_at"}
VEHICLE_FIELDS = {
    "id",
    "name",
    "capacity_kwh",
    "max_kw_ac",
    "brand",
    "model",
    "battery_level",
    "charge_limit",
    "plugged_in",
    "power_delivery_state",
    "power_delivery_state_raw",
    "last_seen",
}


@pytest.fixture(autouse=True)
async def copenhagen(hass: HomeAssistant) -> None:
    """Run every test in the owner's time zone."""
    await hass.config.async_set_time_zone("Europe/Copenhagen")


async def _download_text(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    user: MockUser,
    entry: MockConfigEntry,
) -> str:
    """The whole download as text, fetched with a token made now.

    hass_client's own token is made at fixture setup, and a clock moved before its issue
    time, or more than 30 minutes past it, gets a 401.
    """
    assert await async_setup_component(hass, "diagnostics", {})
    refresh_token = await hass.auth.async_create_refresh_token(user, CLIENT_ID)
    client = await hass_client(hass.auth.async_create_access_token(refresh_token))
    response = await client.get(f"/api/diagnostics/config_entry/{entry.entry_id}")
    assert response.status == HTTPStatus.OK
    text: str = await response.text()
    return text


async def _download(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    user: MockUser,
    entry: MockConfigEntry,
) -> dict[str, Any]:
    """The integration's part of the download."""
    body = json.loads(await _download_text(hass, hass_client, user, entry))
    data: dict[str, Any] = body["data"]
    return data


def _blocked(hass_storage: dict[str, Any], entry: MockConfigEntry) -> None:
    """Store a start block for the entry, as a failed start leaves it."""
    key = f"nortec_go.{entry.entry_id}.charge_control"
    hass_storage[key] = {
        "version": 1,
        "key": key,
        "data": {
            "blocked_since": "2026-09-26T20:00:00+00:00",
            "start_pending_since": None,
            "stop_asked": False,
        },
    }


async def test_diagnostics_output(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    hass_admin_user: MockUser,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The whole output: the four stored secrets redacted, everything else kept (D38)."""
    freezer.move_to(NOON)
    mock_client.get_charger.return_value = make_charger(
        is_connected=True,
        state=ChargerState.BUSY_CHARGING,
        charge_state=ChargeState.CHARGING,
        charge_kwh=4.2,
        charge_kw=7.1,
        charge_cost=9.87,
        last_charge=make_completed_charge(),
    )
    await setup_integration(hass, mock_config_entry)

    assert await _download(hass, hass_client, hass_admin_user, mock_config_entry) == {
        "entry": ENTRY,
        "loaded": True,
        "coordinator": {
            "last_update_success": True,
            "last_exception": None,
            "update_interval_seconds": 300.0,
            "has_car": True,
            "car_read_failing": False,
            "car_gone": False,
            "price_read_failing": False,
            "price_retry_pending": False,
        },
        "data": {
            "read_at": "2026-09-27T10:00:00+00:00",
            "charger": {
                "id": FAKE_CHARGER_ID,
                "name": FAKE_CHARGER_NAME,
                "max_kw": 11.0,
                "state": "busy-charging",
                "state_raw": "busy-charging",
                "is_connected": True,
                "currency": "DKK",
                "active_charge": {
                    "id": FAKE_CHARGE_ID,
                    "state": "charging",
                    "state_raw": "charging",
                    "can_stop": True,
                    "kwh": 4.2,
                    "kw": 7.1,
                    "cost": 9.87,
                },
                "last_charge": {
                    "id": FAKE_LAST_CHARGE_ID,
                    "cost": 42.5,
                    "kwh": 18.4,
                    "completed_at": "2026-09-25T06:15:00+00:00",
                },
            },
            "vehicle": {
                "id": 424242,
                "name": FAKE_VEHICLE_NAME,
                "capacity_kwh": 60.0,
                "max_kw_ac": 11.0,
                "brand": "Example",
                "model": "Model E",
                "battery_level": 55.0,
                "charge_limit": 80.0,
                "plugged_in": False,
                "power_delivery_state": None,
                "power_delivery_state_raw": None,
                "last_seen": "2026-09-26T08:30:00+00:00",
            },
            "control": {
                "blocked": False,
                "start_pending": False,
                "stop_asked": False,
                "stop_pending": False,
            },
        },
        "prices": {
            "currency": "DKK",
            "slot_count": 8,
            "first_slot_start": "2026-09-26T22:00:00+00:00",
            "last_slot_start": "2026-09-26T23:45:00+00:00",
        },
        "energy": {
            "since": "2026-09-27T10:00:00+00:00",
            "settled_kwh": 0.0,
            "settled_id": None,
            "settled_at": None,
            "provisional": [
                {
                    "id": FAKE_CHARGE_ID,
                    "kwh": 4.2,
                    "seen_at": "2026-09-27T10:00:00+00:00",
                }
            ],
        },
    }


async def test_secrets_never_appear(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    hass_admin_user: MockUser,
    hass_storage: dict[str, Any],
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """No secret anywhere in the download, a stored password included; the kept fields are there."""
    freezer.move_to(NOON)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=FAKE_CHARGER_NAME,
        unique_id=str(FAKE_CHARGER_ID),
        data={
            CONF_EMAIL: FAKE_EMAIL,
            CONF_DEVICE_ID: FAKE_DEVICE_ID,
            CONF_PASSWORD: FAKE_PASSWORD,  # never stored; here as the safeguard's case
            **tokens_to_data(FAKE_TOKENS),
        },
    )
    _blocked(hass_storage, entry)
    mock_client.get_charger.return_value = make_charger(is_connected=True)
    await setup_integration(hass, entry)
    blocked = await _download_text(hass, hass_client, hass_admin_user, entry)
    assert f"start_blocked_{entry.entry_id}" in blocked  # the repair issue is in it

    # An open charge clears the block, so the charge ID gets its own download.
    mock_client.get_charger.return_value = make_charger(
        is_connected=True,
        state=ChargerState.BUSY_CHARGING,
        charge_state=ChargeState.CHARGING,
    )
    await entry.runtime_data.async_refresh()
    charging = await _download_text(hass, hass_client, hass_admin_user, entry)

    for body in (blocked, charging):
        for secret in SECRETS:
            assert secret not in body
        assert FAKE_CHARGER_NAME in body
        assert FAKE_VEHICLE_NAME in body
        assert str(FAKE_CHARGER_ID) in body
    assert FAKE_CHARGE_ID in charging


async def test_no_car_and_no_prices(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    hass_admin_user: MockUser,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
) -> None:
    """No car: vehicle is None; no known prices: an empty summary."""
    mock_client.get_vehicle.side_effect = VehicleNotFoundError("fake no car")
    mock_client.get_price_forecast.return_value = make_forecast(
        DEFAULT_FORECAST_START, []
    )
    await setup_integration(hass, mock_config_entry)

    data = await _download(hass, hass_client, hass_admin_user, mock_config_entry)
    assert data["coordinator"]["has_car"] is False
    assert data["data"]["vehicle"] is None
    assert data["prices"] == {
        "currency": "DKK",
        "slot_count": 0,
        "first_slot_start": None,
        "last_slot_start": None,
    }


async def test_car_gone_is_in_the_download(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    hass_admin_user: MockUser,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
) -> None:
    """A car that went while running: car_gone is true, has_car stays true, and there is no car data."""
    await setup_integration(hass, mock_config_entry)
    mock_client.get_vehicle.side_effect = VehicleNotFoundError("fake no car")
    await mock_config_entry.runtime_data.async_read_now(with_car=True)

    data = await _download(hass, hass_client, hass_admin_user, mock_config_entry)
    assert data["coordinator"]["has_car"] is True
    assert data["coordinator"]["car_gone"] is True
    assert data["coordinator"]["car_read_failing"] is True
    assert data["data"]["vehicle"] is None


async def test_failing_reads(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    hass_admin_user: MockUser,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A failed read shows its error; after a good read the old error is gone."""
    freezer.move_to(NOON)
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    error = NortecGoConnectionError("fake network down")
    mock_client.get_charger.side_effect = error
    mock_client.get_vehicle.side_effect = error
    mock_client.get_price_forecast.side_effect = error

    await coordinator.async_refresh()
    await coordinator.async_read_prices(retry_on_failure=True)
    failing = await _download(hass, hass_client, hass_admin_user, mock_config_entry)
    assert failing["coordinator"]["last_update_success"] is False
    assert failing["coordinator"]["last_exception"] == CANNOT_CONNECT
    assert failing["coordinator"]["price_read_failing"] is True
    assert failing["coordinator"]["price_retry_pending"] is True

    # The charger reads again; the car still fails.
    mock_client.get_charger.side_effect = None
    await coordinator.async_read_now(with_car=True)
    recovered = await _download(hass, hass_client, hass_admin_user, mock_config_entry)
    assert recovered["coordinator"]["last_update_success"] is True
    assert recovered["coordinator"]["last_exception"] is None
    assert recovered["coordinator"]["car_read_failing"] is True


@pytest.mark.parametrize(
    ("error", "state", "reason"),
    [
        (NortecGoConnectionError("fake network down"), "setup_retry", CANNOT_CONNECT),
        (ChargerNotFoundError("fake charger gone"), "setup_error", CHARGER_NOT_FOUND),
    ],
)
async def test_failed_setup(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    hass_admin_user: MockUser,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    error: Exception,
    state: str,
    reason: str,
) -> None:
    """A failed setup: the entry, its state and why, secrets redacted."""
    mock_client.get_charger.side_effect = error
    await setup_integration(hass, mock_config_entry)

    assert await _download(hass, hass_client, hass_admin_user, mock_config_entry) == {
        "entry": ENTRY,
        "loaded": False,
        "state": state,
        "reason": reason,
    }


async def test_unloaded_entry(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    hass_admin_user: MockUser,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
) -> None:
    """An unloaded entry still downloads, with no reason."""
    await setup_integration(hass, mock_config_entry)
    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert await _download(hass, hass_client, hass_admin_user, mock_config_entry) == {
        "entry": ENTRY,
        "loaded": False,
        "state": "not_loaded",
        "reason": None,
    }


def test_client_model_fields_are_pinned() -> None:
    """A pynortecgo bump that changes these fields fails here: judge each new one (D38)."""
    assert {f.name for f in fields(Charger)} == CHARGER_FIELDS
    assert {f.name for f in fields(ActiveCharge)} == ACTIVE_CHARGE_FIELDS
    assert {f.name for f in fields(CompletedCharge)} == COMPLETED_CHARGE_FIELDS
    assert {f.name for f in fields(Vehicle)} == VEHICLE_FIELDS
