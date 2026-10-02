"""Tests for the Nortec Go integration setup."""

import asyncio
from datetime import UTC, datetime, timedelta
import json
import logging
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant import loader
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_DEVICE_ID, CONF_EMAIL, STATE_UNAVAILABLE
from homeassistant.core import DOMAIN as HOMEASSISTANT_DOMAIN, HassJob, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from homeassistant.util.async_ import get_scheduled_timer_handles
from pynortecgo import (
    AuthError,
    ChargeStartError,
    ChargeStartStep,
    ChargeState,
    MultipleVehiclesError,
    NortecGoConnectionError,
    VehicleNotFoundError,
)
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.nortec_go.const import (
    DOMAIN,
    START_LOAD_GRACE,
    STOP_CONFIRM_TIMEOUT,
)
from custom_components.nortec_go.coordinator import car_device_identifier
from custom_components.nortec_go.entry import tokens_from_data

from .conftest import (
    FAKE_CHARGER_ID,
    FAKE_DEVICE_ID,
    FAKE_EMAIL,
    FAKE_TOKENS,
    NEW_TOKENS,
    make_charger,
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


# 2026-09-27 10:00 local (CEST) is 08:00 UTC.
TEN_AM = datetime(2026, 9, 27, 8, 0, tzinfo=UTC)


async def test_failed_setup_price_read_retries(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A failed setup price read still loads the entry and is read once more 15 minutes later."""
    await hass.config.async_set_time_zone("Europe/Copenhagen")
    freezer.move_to(TEN_AM - timedelta(minutes=30))  # 09:30 local
    mock_client.get_price_forecast.side_effect = NortecGoConnectionError("network down")
    await setup_integration(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_client.get_price_forecast.await_count == 1

    mock_client.get_price_forecast.side_effect = None
    freezer.tick(timedelta(minutes=15))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert mock_client.get_price_forecast.await_count == 2
    assert mock_config_entry.runtime_data.known_prices


async def test_unload_cancels_a_pending_price_retry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Unload cancels a retry that isn't due yet."""
    await hass.config.async_set_time_zone("Europe/Copenhagen")
    freezer.move_to(TEN_AM - timedelta(minutes=30))
    mock_client.get_price_forecast.side_effect = NortecGoConnectionError("network down")
    await setup_integration(hass, mock_config_entry)
    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    freezer.tick(timedelta(minutes=15))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert mock_client.get_price_forecast.await_count == 1


async def test_unload_cancels_a_price_retry_in_flight(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A retry read still running at unload is cancelled."""
    await hass.config.async_set_time_zone("Europe/Copenhagen")
    freezer.move_to(TEN_AM - timedelta(minutes=30))
    mock_client.get_price_forecast.side_effect = NortecGoConnectionError("network down")
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
    freezer.tick(timedelta(minutes=15))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert started.is_set()  # not started.wait(): without a retry that would hang
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


async def test_remove_entry_removes_the_stored_energy_ledger(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    hass_storage: dict[str, Any],
) -> None:
    """Deleting the entry deletes its stored Total energy ledger."""
    await setup_integration(hass, mock_config_entry)
    key = f"nortec_go.{mock_config_entry.entry_id}.energy"
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


@pytest.mark.parametrize(
    "error",
    [VehicleNotFoundError("no car"), MultipleVehiclesError("two cars")],
)
async def test_car_gone_makes_the_car_entities_unavailable(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    error: Exception,
) -> None:
    """While the car is gone its entities are unavailable but still there; a good read brings them back."""
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    entity_registry = er.async_get(hass)

    mock_client.get_vehicle.side_effect = error
    await coordinator.async_read_now(with_car=True)
    await hass.async_block_till_done()
    for entity_id in CAR_ENTITY_IDS:
        assert entity_registry.async_get(entity_id) is not None
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == STATE_UNAVAILABLE

    mock_client.get_vehicle.side_effect = None
    await coordinator.async_read_now(with_car=True)
    await hass.async_block_till_done()
    for entity_id in CAR_ENTITY_IDS:
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state != STATE_UNAVAILABLE
    battery = hass.states.get("sensor.family_car_battery")
    assert battery is not None
    assert battery.state == "55.0"


async def test_stored_block_survives_restart(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    hass_storage: dict[str, Any],
) -> None:
    """A stored block is loaded at setup: starts stay blocked and the issue is back (Review Focus 5)."""
    key = f"nortec_go.{mock_config_entry.entry_id}.charge_control"
    hass_storage[key] = {
        "version": 1,
        "key": key,
        "data": {
            "blocked_since": "2026-09-26T20:00:00+00:00",
            "start_pending_since": None,
            "stop_asked": False,
        },
    }
    mock_client.get_charger.return_value = make_charger(is_connected=True)
    await setup_integration(hass, mock_config_entry)
    assert mock_config_entry.runtime_data.data.control.blocked
    issue = ir.async_get(hass).async_get_issue(
        DOMAIN, f"start_blocked_{mock_config_entry.entry_id}"
    )
    assert issue is not None


async def test_removal_removes_charge_control(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    hass_storage: dict[str, Any],
) -> None:
    """Removing the entry removes the control's store and the issue."""
    key = f"nortec_go.{mock_config_entry.entry_id}.charge_control"
    hass_storage[key] = {
        "version": 1,
        "key": key,
        "data": {
            "blocked_since": "2026-09-26T20:00:00+00:00",
            "start_pending_since": None,
            "stop_asked": False,
        },
    }
    mock_client.get_charger.return_value = make_charger(is_connected=True)
    await setup_integration(hass, mock_config_entry)
    await hass.config_entries.async_remove(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert key not in hass_storage
    assert (
        ir.async_get(hass).async_get_issue(
            DOMAIN, f"start_blocked_{mock_config_entry.entry_id}"
        )
        is None
    )


async def test_block_from_a_start_during_reload_reaches_the_new_control(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A start that fails with a hold while the entry unloads blocks the reloaded control."""
    mock_client.get_charger.return_value = make_charger(is_connected=True)
    await setup_integration(hass, mock_config_entry)
    release = asyncio.Event()

    async def slow_start() -> None:
        await release.wait()
        raise ChargeStartError(ChargeStartStep.CONFIRM, True)

    mock_client.start_charge.side_effect = slow_start
    control = mock_config_entry.runtime_data.charge_control
    start = hass.async_create_task(control.async_start())
    await asyncio.sleep(0)
    reload = hass.async_create_task(
        hass.config_entries.async_reload(mock_config_entry.entry_id)
    )
    # Loop turns, not async_block_till_done (it would wait on the held start).
    await asyncio.sleep(0.05)
    assert not reload.done()  # waiting in async_shutdown for the start in flight
    release.set()
    with pytest.raises(HomeAssistantError):
        await start
    assert await reload
    await hass.async_block_till_done()
    assert mock_config_entry.runtime_data.data.control.blocked


async def test_failed_setup_leaves_no_start_timer(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """A setup whose first read fails cancels its start timer: no repair issue appears later."""
    key = f"nortec_go.{mock_config_entry.entry_id}.charge_control"
    hass_storage[key] = {
        "version": 1,
        "key": key,
        "data": {
            "blocked_since": None,
            "start_pending_since": dt_util.utcnow().isoformat(),
            "stop_asked": False,
        },
    }
    mock_client.get_charger.side_effect = NortecGoConnectionError("network down")
    await setup_integration(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    for _ in range(4):
        freezer.tick(timedelta(minutes=3))
        async_fire_time_changed(hass)
        await hass.async_block_till_done(wait_background_tasks=True)
    issue = ir.async_get(hass).async_get_issue(
        DOMAIN, f"start_blocked_{mock_config_entry.entry_id}"
    )
    assert issue is None
    assert hass_storage[key]["data"]["blocked_since"] is None


def _control_data(**changes: Any) -> dict[str, Any]:
    """The charge control's stored data in the minor version 2 shape, idle unless told otherwise."""
    return {
        "blocked_since": None,
        "block_reason": None,
        "start_pending_since": None,
        "stop_asked_since": None,
        "stop_tries": 0,
        "stop_tried_at": None,
        **changes,
    }


def _timers(hass: HomeAssistant, name: str) -> int:
    """The scheduled, not cancelled timers whose job has this name."""
    return sum(
        1
        for handle in get_scheduled_timer_handles(hass.loop)
        if not handle.cancelled()
        and handle._args  # noqa: SLF001
        and isinstance(job := handle._args[-1], HassJob)  # noqa: SLF001
        and job.name == name
    )


async def test_stop_survives_a_setup_that_fails_on_the_price_read(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """A stop queued by the setup's charger read, then cancelled by a rejected price read, is sent by the next setup (#85, case 1)."""
    key = f"nortec_go.{mock_config_entry.entry_id}.charge_control"
    now = dt_util.utcnow().isoformat()
    hass_storage[key] = {
        "version": 1,
        "minor_version": 2,
        "key": key,
        "data": _control_data(start_pending_since=now, stop_asked_since=now),
    }
    mock_client.get_charger.return_value = make_charger(
        is_connected=True, charge_state=ChargeState.CHARGING
    )
    never = asyncio.Event()

    async def _stop_in_flight() -> None:
        await never.wait()

    mock_client.stop_charge.side_effect = _stop_in_flight
    mock_client.get_price_forecast.side_effect = AuthError("token rejected")
    with patch.object(ConfigEntry, "async_start_reauth_if_available"):
        await setup_integration(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    assert (
        mock_client.stop_charge.await_count == 1
    )  # made, then cancelled with the setup
    # The entry closed the control before it cancelled the call, so the call's end armed no
    # wait on the dead control, and its 30-minute timer went with the others.
    assert _timers(hass, f"{DOMAIN} stop wait") == 0
    assert _timers(hass, f"{DOMAIN} stop limit") == 0
    async_fire_time_changed(hass)  # a delayed save's timer
    await hass.async_block_till_done()
    stored = hass_storage[key]["data"]
    assert stored["start_pending_since"] is None  # the read saw the charge
    assert stored["stop_asked_since"] == now  # the stop is still asked
    assert stored["stop_tries"] == 1

    mock_client.stop_charge.side_effect = None
    mock_client.get_price_forecast.side_effect = None
    # True for a loaded entry (mypy has narrowed the entry's state to the failed one above).
    assert await hass.config_entries.async_reload(mock_config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert (
        mock_client.stop_charge.await_count == 1
    )  # the 2 minutes since the call still run
    assert not mock_config_entry.runtime_data.data.control.start_pending
    assert mock_config_entry.runtime_data.data.control.stop_asked

    freezer.tick(STOP_CONFIRM_TIMEOUT + timedelta(seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    await mock_config_entry.runtime_data.async_read_now()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert mock_client.stop_charge.await_count == 2
    mock_client.start_charge.assert_not_awaited()


async def test_stop_survives_the_start_deadline_at_a_slow_setup(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """A setup try that is slow, lets the start deadline fire and then fails keeps the stop; the next setup sends it (#85, case 2)."""
    key = f"nortec_go.{mock_config_entry.entry_id}.charge_control"
    now = dt_util.utcnow()
    asked = (now - timedelta(minutes=5)).isoformat()
    hass_storage[key] = {
        "version": 1,
        "minor_version": 2,
        "key": key,
        "data": _control_data(
            start_pending_since=(now - timedelta(minutes=9)).isoformat(),
            stop_asked_since=asked,
        ),
    }

    async def _slow_then_fails() -> None:
        # The read outlasts the pending start's deadline at a load (START_LOAD_GRACE), then fails.
        freezer.tick(START_LOAD_GRACE + timedelta(seconds=1))
        async_fire_time_changed(hass)
        await asyncio.sleep(0)
        raise NortecGoConnectionError("network down")

    mock_client.get_charger.side_effect = _slow_then_fails
    await setup_integration(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    async_fire_time_changed(hass)  # a delayed save's timer
    await hass.async_block_till_done()
    stored = hass_storage[key]["data"]
    assert stored["start_pending_since"] is None  # the deadline ended the pending start
    assert stored["blocked_since"] is not None
    assert stored["stop_asked_since"] == asked  # and no longer the stop

    mock_client.get_charger.side_effect = None
    mock_client.get_charger.return_value = make_charger(
        is_connected=True, charge_state=ChargeState.CHARGING
    )
    # True for a loaded entry (mypy has narrowed the entry's state to the failed one above).
    assert await hass.config_entries.async_reload(mock_config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    mock_client.stop_charge.assert_awaited_once()
    assert (
        not mock_config_entry.runtime_data.data.control.blocked
    )  # the charge seen clears it (D26)
    mock_client.start_charge.assert_not_awaited()


async def test_old_format_stop_is_sent_after_the_upgrade(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    hass_storage: dict[str, Any],
) -> None:
    """A stop asked for under the old stored format is migrated, not turned into a block, and sent."""
    key = f"nortec_go.{mock_config_entry.entry_id}.charge_control"
    hass_storage[key] = {
        "version": 1,
        "key": key,
        "data": {
            "blocked_since": None,
            "start_pending_since": dt_util.utcnow().isoformat(),
            "stop_asked": True,
        },
    }
    mock_client.get_charger.return_value = make_charger(
        is_connected=True, charge_state=ChargeState.CHARGING
    )
    await setup_integration(hass, mock_config_entry)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert not mock_config_entry.runtime_data.data.control.blocked
    mock_client.stop_charge.assert_awaited_once()
    assert hass_storage[key]["minor_version"] == 2


async def test_removal_removes_the_stop_issue(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    hass_storage: dict[str, Any],
) -> None:
    """Removing the entry removes the stop notice a give-up at load raised."""
    key = f"nortec_go.{mock_config_entry.entry_id}.charge_control"
    hass_storage[key] = {
        "version": 1,
        "minor_version": 2,
        "key": key,
        "data": _control_data(
            stop_asked_since=(dt_util.utcnow() - timedelta(minutes=31)).isoformat()
        ),
    }
    mock_client.get_charger.return_value = make_charger(
        is_connected=True, charge_state=ChargeState.CHARGING
    )
    await setup_integration(hass, mock_config_entry)
    issue_id = f"stop_failed_{mock_config_entry.entry_id}"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None
    await hass.config_entries.async_remove(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
