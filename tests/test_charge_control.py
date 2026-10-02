"""Tests for the Nortec Go charge control: start, stop, pending start and the start guard."""

import asyncio
from collections.abc import AsyncGenerator
from datetime import timedelta
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HassJob, HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from homeassistant.util.async_ import get_scheduled_timer_handles
from pynortecgo import (
    ApiError,
    AuthError,
    CableNotConnectedError,
    ChargeAlreadyActiveError,
    ChargeNotStoppableError,
    ChargerNotReleasedError,
    ChargerState,
    ChargeStartError,
    ChargeStartStep,
    ChargeState,
    MultiplePaymentSourcesError,
    MultipleVehiclesError,
    NoActiveChargeError,
    NortecGoClient,
    NortecGoConnectionError,
    PaymentSourceNotFoundError,
    RateLimitError,
    UnexpectedResponseError,
    UnknownChargerStateError,
    VehicleNotFoundError,
)
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.nortec_go.charge_control import (
    ChargeControl,
    ChargeControlState,
    async_remove_charge_control,
    charge_is_open,
    charge_status,
    is_charge_off,
    is_charge_on,
    is_stoppable,
)
from custom_components.nortec_go.const import (
    DOMAIN,
    START_CONFIRM_TIMEOUT,
    START_LOAD_GRACE,
    STOP_ASKED_MAX_AGE,
    STOP_CONFIRM_TIMEOUT,
    STOP_MAX_TRIES,
)

from .conftest import make_charger

IDLE = ChargeControlState()
PENDING = ChargeControlState(start_pending=True)
STOP_ASKED = ChargeControlState(start_pending=True, stop_asked=True)
STOP_ASKED_ONLY = ChargeControlState(stop_asked=True)
STOP_PENDING = ChargeControlState(stop_asked=True, stop_pending=True)
BLOCKED = ChargeControlState(blocked=True)
CONNECTED = make_charger(is_connected=True)
CHARGING = make_charger(
    is_connected=True,
    charge_state=ChargeState.CHARGING,
    state=ChargerState.BUSY_CHARGING,
)
BUSY_NO_CHARGE_STATE = make_charger(
    is_connected=True, state=ChargerState.BUSY_NON_CHARGING
)
NOT_STOPPABLE = make_charger(
    is_connected=True,
    charge_state=ChargeState.STARTING,
    state=ChargerState.BUSY,
    can_stop=False,
)
STORE_KEY = "nortec_go.{}.charge_control"


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


async def _fire(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, delta: timedelta
) -> None:
    """Move time on, fire due timers and wait for their background work."""
    freezer.tick(delta)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)


async def _saved(
    hass: HomeAssistant, entry: MockConfigEntry, hass_storage: dict[str, Any]
) -> dict[str, Any]:
    """The stored data, once a delayed save has landed."""
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    data: dict[str, Any] = hass_storage[STORE_KEY.format(entry.entry_id)]["data"]
    return data


@pytest.mark.parametrize(
    ("charger", "expected"),
    [
        (CONNECTED, False),
        (make_charger(is_connected=True, state=ChargerState.BUSY), True),
        (make_charger(is_connected=True, state=ChargerState.BUSY_CHARGING), True),
        (make_charger(is_connected=True, state=ChargerState.BUSY_NON_CHARGING), True),
        (make_charger(is_connected=True, charge_state=ChargeState.PAUSED), True),
        (make_charger(is_connected=True, state=ChargerState.BUSY_NON_RELEASED), False),
    ],
)
def test_charge_is_open(charger: Any, expected: bool) -> None:
    """A charge is open on a charge state, BUSY, BUSY_CHARGING or BUSY_NON_CHARGING."""
    assert charge_is_open(charger) is expected


@pytest.mark.parametrize(
    ("charge_state", "control", "expected"),
    [
        (None, IDLE, False),
        (ChargeState.STARTING, IDLE, True),
        (ChargeState.CHARGING, IDLE, True),
        (ChargeState.PAUSED, IDLE, True),
        (ChargeState.STOPPING, IDLE, False),
        (ChargeState.UNKNOWN, IDLE, False),
        (None, PENDING, True),
        (None, STOP_ASKED, False),
        (ChargeState.CHARGING, STOP_ASKED, False),
        (ChargeState.CHARGING, STOP_PENDING, False),
        (ChargeState.PAUSED, STOP_PENDING, False),
    ],
)
def test_is_charge_on(
    charge_state: ChargeState | None, control: ChargeControlState, expected: bool
) -> None:
    """On for an open, not ending charge, or a pending start without a stop asked; off while our stop is pending."""
    charger = make_charger(is_connected=True, charge_state=charge_state)
    assert is_charge_on(charger, control) is expected


@pytest.mark.parametrize(
    ("charger", "control", "expected"),
    [
        (CHARGING, BLOCKED, "start_blocked"),
        (CONNECTED, PENDING, "starting"),
        (CONNECTED, STOP_ASKED, "stopping"),
        (CHARGING, PENDING, "charging"),
        (make_charger(is_connected=True, state=ChargerState.UNKNOWN), IDLE, None),
        (make_charger(is_connected=True, charge_state=ChargeState.UNKNOWN), IDLE, None),
        (
            make_charger(is_connected=True, charge_state=ChargeState.STARTING),
            IDLE,
            "starting",
        ),
        (CHARGING, IDLE, "charging"),
        (
            make_charger(is_connected=True, charge_state=ChargeState.PAUSED),
            IDLE,
            "paused",
        ),
        (
            make_charger(
                is_connected=True,
                state=ChargerState.BUSY_NON_CHARGING,
                charge_state=ChargeState.PAUSED,
            ),
            IDLE,
            "paused",
        ),
        (
            make_charger(is_connected=True, state=ChargerState.BUSY_NON_CHARGING),
            IDLE,
            "idle",
        ),
        (
            make_charger(is_connected=True, charge_state=ChargeState.STOPPING),
            IDLE,
            "stopping",
        ),
        (
            make_charger(is_connected=True, charge_state=ChargeState.COMPLETED),
            IDLE,
            "idle",
        ),
        (
            make_charger(is_connected=True, state=ChargerState.BUSY_NON_RELEASED),
            IDLE,
            "not_released",
        ),
        (make_charger(is_connected=False), IDLE, "unplugged"),
        (CONNECTED, IDLE, "idle"),
        (CHARGING, STOP_PENDING, "stopping"),
        (
            CHARGING,
            ChargeControlState(blocked=True, stop_pending=True),
            "start_blocked",
        ),
    ],
)
def test_charge_status(
    charger: Any, control: ChargeControlState, expected: str | None
) -> None:
    """The status follows the spec's table, first match wins."""
    assert charge_status(charger, control) == expected


@pytest.fixture
def entry(hass: HomeAssistant, mock_config_entry: MockConfigEntry) -> MockConfigEntry:
    """The conftest entry (with email, device ID and tokens, so reauth can run), in hass."""
    mock_config_entry.add_to_hass(hass)
    return mock_config_entry


@pytest.fixture
def client() -> AsyncMock:
    """A mocked client; nothing here reaches the real API."""
    return AsyncMock(spec=NortecGoClient)


@pytest.fixture
def on_change() -> MagicMock:
    """The control's on_change callback."""
    return MagicMock()


@pytest.fixture
def request_refresh() -> AsyncMock:
    """The control's request_refresh callback."""
    return AsyncMock()


@pytest.fixture
async def control(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    client: AsyncMock,
    on_change: MagicMock,
    request_refresh: AsyncMock,
) -> AsyncGenerator[ChargeControl]:
    """A loaded control that has seen one connected, idle read; shut down at teardown."""
    control = ChargeControl(
        hass, entry, client, on_change=on_change, request_refresh=request_refresh
    )
    await control.async_load()
    control.on_charger_read(CONNECTED, control.start_attempts)
    yield control
    await control.async_shutdown()


def _issue(hass: HomeAssistant, entry: MockConfigEntry) -> ir.IssueEntry | None:
    return ir.async_get(hass).async_get_issue(DOMAIN, f"start_blocked_{entry.entry_id}")


async def test_start_sets_pending_and_asks_for_a_read(
    hass: HomeAssistant,
    control: ChargeControl,
    client: AsyncMock,
    on_change: MagicMock,
    request_refresh: AsyncMock,
) -> None:
    """A successful start is pending, tells the coordinator and asks for a read."""
    await control.async_start()
    await hass.async_block_till_done()
    client.start_charge.assert_awaited_once()
    assert control.state == PENDING
    on_change.assert_called()
    request_refresh.assert_awaited()


async def test_second_start_is_noop(control: ChargeControl, client: AsyncMock) -> None:
    """EVSC's repeated turn_on during a pending start makes no API call (Review Focus 2)."""
    await control.async_start()
    await control.async_start()
    client.start_charge.assert_awaited_once()


async def test_start_noop_while_charge_open(
    control: ChargeControl, client: AsyncMock
) -> None:
    """A charge open in the last read: no API call."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_start()
    client.start_charge.assert_not_awaited()


async def test_start_noop_while_busy_non_charging(
    control: ChargeControl, client: AsyncMock
) -> None:
    """BUSY_NON_CHARGING without a charge state is a charge in progress: no API call."""
    control.on_charger_read(BUSY_NO_CHARGE_STATE, control.start_attempts)
    await control.async_start()
    client.start_charge.assert_not_awaited()


@pytest.mark.parametrize(
    ("error", "key"),
    [
        (CableNotConnectedError("x"), "cable_not_connected"),
        (ChargerNotReleasedError("x"), "charger_not_released"),
        (UnknownChargerStateError("mystery"), "charger_state_unknown"),
        (PaymentSourceNotFoundError("x"), "no_payment_source"),
        (MultiplePaymentSourcesError("x"), "multiple_payment_sources"),
        (VehicleNotFoundError("x"), "no_vehicle"),
        (MultipleVehiclesError("x"), "multiple_vehicles"),
    ],
)
async def test_pre_check_errors(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    client: AsyncMock,
    error: Exception,
    key: str,
) -> None:
    """Pre-check errors raise a translated validation error and never block."""
    client.start_charge.side_effect = error
    with pytest.raises(ServiceValidationError) as exc_info:
        await control.async_start()
    assert exc_info.value.translation_key == key
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__
    assert control.state == IDLE
    assert _issue(hass, entry) is None
    client.start_charge.assert_awaited_once()


@pytest.mark.parametrize(
    "error",
    [
        NortecGoConnectionError("x"),
        RateLimitError("x"),
        ApiError("POST /x", 500),
        UnexpectedResponseError("GET /x", "bad"),
    ],
)
async def test_other_pre_check_errors(
    control: ChargeControl, client: AsyncMock, error: Exception
) -> None:
    """Connection, rate limit and API errors before a payment: start_failed, no block."""
    client.start_charge.side_effect = error
    with pytest.raises(HomeAssistantError) as exc_info:
        await control.async_start()
    assert exc_info.value.translation_key == "start_failed"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__
    assert control.state == IDLE


async def test_start_hold_error_blocks(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    client: AsyncMock,
    request_refresh: AsyncMock,
) -> None:
    """A ChargeStartError with a hold blocks, raises the issue and asks for a read."""
    client.start_charge.side_effect = ChargeStartError(ChargeStartStep.CONFIRM, True)
    with pytest.raises(HomeAssistantError) as exc_info:
        await control.async_start()
    await hass.async_block_till_done()
    assert exc_info.value.translation_key == "start_failed_hold"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__
    assert control.state == BLOCKED
    issue = _issue(hass, entry)
    assert issue is not None
    assert issue.translation_key == "start_blocked"
    assert issue.is_fixable
    assert issue.translation_placeholders == {"name": "Garage charger"}
    assert issue.data == {"entry_id": entry.entry_id}
    request_refresh.assert_awaited()
    # Blocked: the next turn_on raises and makes no API call (hard rule 6).
    with pytest.raises(ServiceValidationError) as exc_info:
        await control.async_start()
    assert exc_info.value.translation_key == "start_blocked"
    client.start_charge.assert_awaited_once()


async def test_start_error_without_hold(
    control: ChargeControl, client: AsyncMock
) -> None:
    """A ChargeStartError at the payment intent step: start_failed, no block."""
    client.start_charge.side_effect = ChargeStartError(
        ChargeStartStep.PAYMENT_INTENT, False
    )
    with pytest.raises(HomeAssistantError) as exc_info:
        await control.async_start()
    assert exc_info.value.translation_key == "start_failed"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__
    assert control.state == IDLE


async def test_start_already_active(
    hass: HomeAssistant,
    control: ChargeControl,
    client: AsyncMock,
    on_change: MagicMock,
    request_refresh: AsyncMock,
) -> None:
    """ChargeAlreadyActiveError: no error, a read asked for, no pending start."""
    client.start_charge.side_effect = ChargeAlreadyActiveError("x")
    await control.async_start()
    await hass.async_block_till_done()
    assert control.state == IDLE
    request_refresh.assert_awaited()
    on_change.assert_not_called()


async def test_start_auth_error_starts_reauth(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    client: AsyncMock,
) -> None:
    """AuthError in the pre-check starts reauth and raises auth_failed, no block."""
    client.start_charge.side_effect = AuthError("x")
    with pytest.raises(HomeAssistantError) as exc_info:
        await control.async_start()
    await hass.async_block_till_done()
    assert exc_info.value.translation_key == "auth_failed"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__
    assert control.state == IDLE
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert any(flow["context"]["source"] == "reauth" for flow in flows)


async def test_cancelled_start_blocks(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    client: AsyncMock,
) -> None:
    """A start cancelled during the call blocks, then re-raises."""
    client.start_charge.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await control.async_start()
    assert control.state == BLOCKED
    assert _issue(hass, entry) is not None


async def test_unknown_charger_refuses(
    control: ChargeControl, client: AsyncMock
) -> None:
    """An UNKNOWN charger state: charger_state_unknown, no API call."""
    control.on_charger_read(
        make_charger(is_connected=True, state=ChargerState.UNKNOWN),
        control.start_attempts,
    )
    with pytest.raises(ServiceValidationError) as exc_info:
        await control.async_start()
    assert exc_info.value.translation_key == "charger_state_unknown"
    client.start_charge.assert_not_awaited()


@pytest.mark.parametrize(
    "charger",
    [
        CHARGING,
        BUSY_NO_CHARGE_STATE,
        make_charger(is_connected=True, state=ChargerState.BUSY_NON_RELEASED),
        make_charger(is_connected=False),
    ],
)
async def test_pending_start_ends_without_block(
    control: ChargeControl, charger: Any
) -> None:
    """A charge seen (also BUSY_NON_CHARGING without a charge state), BUSY_NON_RELEASED or the cable unplugged ends the pending start."""
    await control.async_start()
    control.on_charger_read(charger, control.start_attempts)
    assert control.state == IDLE


async def test_pending_start_times_out_into_block(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    freezer: FrozenDateTimeFactory,
    on_change: MagicMock,
) -> None:
    """No charge seen within 10 minutes, with no read at all: the start counts as failed with a hold."""
    await control.async_start()
    await _fire(hass, freezer, START_CONFIRM_TIMEOUT - timedelta(seconds=1))
    assert control.state == PENDING
    on_change.reset_mock()
    await _fire(hass, freezer, timedelta(seconds=1))
    assert control.state == BLOCKED
    assert _issue(hass, entry) is not None
    on_change.assert_called()


async def test_unplugged_read_after_the_timeout_clears_the_block(
    hass: HomeAssistant, control: ChargeControl, freezer: FrozenDateTimeFactory
) -> None:
    """The timer blocks at 10 minutes; a later read that sees the cable unplugged clears it (D26)."""
    await control.async_start()
    await _fire(hass, freezer, START_CONFIRM_TIMEOUT)
    assert control.state == BLOCKED
    control.on_charger_read(make_charger(is_connected=False), control.start_attempts)
    assert control.state == IDLE


async def test_read_with_a_charge_ends_the_start_timer(
    hass: HomeAssistant, control: ChargeControl, freezer: FrozenDateTimeFactory
) -> None:
    """A read that sees a charge ends the pending start; its timer blocks nothing later."""
    await control.async_start()
    control.on_charger_read(CHARGING, control.start_attempts)
    assert control.state == IDLE
    await _fire(hass, freezer, START_CONFIRM_TIMEOUT)
    assert control.state == IDLE


async def test_new_start_gets_a_fresh_timer(
    hass: HomeAssistant, control: ChargeControl, freezer: FrozenDateTimeFactory
) -> None:
    """A second start after the first ended has its own 10 minutes; the first timer is gone."""
    await control.async_start()
    control.on_charger_read(make_charger(is_connected=False), control.start_attempts)
    await _fire(hass, freezer, timedelta(minutes=5))
    await control.async_start()
    await _fire(hass, freezer, timedelta(minutes=6))
    assert control.state == PENDING
    await _fire(hass, freezer, timedelta(minutes=4))
    assert control.state == BLOCKED


async def test_start_timer_does_nothing_after_shutdown(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    freezer: FrozenDateTimeFactory,
    on_change: MagicMock,
) -> None:
    """After unload the start timer changes nothing."""
    await control.async_start()
    await control.async_shutdown()
    on_change.reset_mock()
    await _fire(hass, freezer, START_CONFIRM_TIMEOUT)
    assert control.state == PENDING
    assert _issue(hass, entry) is None
    on_change.assert_not_called()


async def test_start_timer_after_the_start_ended_does_nothing(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A start timer whose work waits for the lock while a read ends the pending start blocks nothing."""
    await control.async_start()
    async with control._lock:  # noqa: SLF001
        freezer.tick(START_CONFIRM_TIMEOUT)
        async_fire_time_changed(hass)
        await asyncio.sleep(0)
        control.on_charger_read(CHARGING, control.start_attempts)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert control.state == IDLE
    assert _issue(hass, entry) is None


@pytest.mark.parametrize(
    ("age", "left"),
    [
        (timedelta(minutes=3), timedelta(minutes=7)),
        (timedelta(minutes=9), START_LOAD_GRACE),
        (timedelta(minutes=30), START_LOAD_GRACE),
        (-timedelta(hours=1), START_CONFIRM_TIMEOUT),
    ],
)
async def test_load_arms_the_start_timer(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    client: AsyncMock,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
    age: timedelta,
    left: timedelta,
) -> None:
    """A stored pending start gets the time left, at least the grace, at most 10 minutes."""
    key = STORE_KEY.format(entry.entry_id)
    hass_storage[key] = {
        "version": 1,
        "key": key,
        "data": {
            "blocked_since": None,
            "start_pending_since": (dt_util.utcnow() - age).isoformat(),
            "stop_asked": False,
        },
    }
    control = ChargeControl(
        hass, entry, client, on_change=MagicMock(), request_refresh=AsyncMock()
    )
    await control.async_load()
    assert control.state == PENDING
    await _fire(hass, freezer, left - timedelta(seconds=1))
    assert control.state == PENDING
    await _fire(hass, freezer, timedelta(seconds=1))
    assert control.state == BLOCKED
    await control.async_shutdown()


@pytest.mark.parametrize(
    "charger",
    [
        CHARGING,
        make_charger(is_connected=True, state=ChargerState.BUSY_NON_RELEASED),
        make_charger(is_connected=False),
    ],
)
async def test_overdue_start_at_load_decided_by_the_first_read(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    client: AsyncMock,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
    charger: Any,
) -> None:
    """An overdue stored start is ended by a first read with evidence, with no block (Review Focus 1).

    The read here runs before the loop could fire any timer; the grace itself is pinned by
    test_load_arms_the_start_timer's 9- and 30-minute rows.
    """
    key = STORE_KEY.format(entry.entry_id)
    hass_storage[key] = {
        "version": 1,
        "key": key,
        "data": {
            "blocked_since": None,
            "start_pending_since": (dt_util.utcnow() - timedelta(hours=8)).isoformat(),
            "stop_asked": False,
        },
    }
    control = ChargeControl(
        hass, entry, client, on_change=MagicMock(), request_refresh=AsyncMock()
    )
    await control.async_load()
    control.on_charger_read(charger, control.start_attempts)
    await _fire(hass, freezer, START_CONFIRM_TIMEOUT)
    assert control.state == IDLE
    assert _issue(hass, entry) is None
    await control.async_shutdown()


async def test_overdue_start_at_load_blocks_after_the_grace_without_evidence(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    client: AsyncMock,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """An overdue stored start whose first read brings no evidence blocks once the grace is over (§8)."""
    key = STORE_KEY.format(entry.entry_id)
    hass_storage[key] = {
        "version": 1,
        "key": key,
        "data": {
            "blocked_since": None,
            "start_pending_since": (dt_util.utcnow() - timedelta(hours=8)).isoformat(),
            "stop_asked": False,
        },
    }
    control = ChargeControl(
        hass, entry, client, on_change=MagicMock(), request_refresh=AsyncMock()
    )
    await control.async_load()
    control.on_charger_read(CONNECTED, control.start_attempts)
    await _fire(hass, freezer, START_LOAD_GRACE - timedelta(seconds=1))
    assert control.state == PENDING
    await _fire(hass, freezer, timedelta(seconds=1))
    assert control.state == BLOCKED
    assert _issue(hass, entry) is not None
    await control.async_shutdown()


async def test_stale_read_changes_nothing(
    control: ChargeControl, client: AsyncMock
) -> None:
    """A read begun before the latest start attempt neither ends the pending start nor clears the block."""
    attempts_before = control.start_attempts
    await control.async_start()
    for stale in (
        make_charger(is_connected=False),
        make_charger(is_connected=True, state=ChargerState.BUSY_NON_RELEASED),
        CHARGING,
    ):
        control.on_charger_read(stale, attempts_before)
        assert control.state == PENDING
    # And a block from a failed start.
    control.on_charger_read(CHARGING, control.start_attempts)  # ends the pending start
    client.start_charge.side_effect = ChargeStartError(ChargeStartStep.START, True)
    control.on_charger_read(CONNECTED, control.start_attempts)  # last read: no charge
    attempts_before = control.start_attempts
    with pytest.raises(HomeAssistantError):
        await control.async_start()
    for stale in (make_charger(is_connected=False), CHARGING):
        control.on_charger_read(stale, attempts_before)
        assert control.state.blocked


@pytest.mark.parametrize(
    "charger",
    [make_charger(is_connected=False), CHARGING, BUSY_NO_CHARGE_STATE],
)
async def test_block_cleared_by_a_fresh_read(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    client: AsyncMock,
    charger: Any,
) -> None:
    """The cable unplugged or a charge open (also BUSY_NON_CHARGING without a charge state) clears the block and the issue."""
    client.start_charge.side_effect = ChargeStartError(ChargeStartStep.CONFIRM, True)
    with pytest.raises(HomeAssistantError):
        await control.async_start()
    control.on_charger_read(charger, control.start_attempts)
    assert control.state == IDLE
    assert _issue(hass, entry) is None


async def test_block_cleared_by_release_after_the_block(
    control: ChargeControl, client: AsyncMock
) -> None:
    """BUSY_NON_RELEASED then AVAILABLE, both after the block, clears it; one from before doesn't."""
    control.on_charger_read(
        make_charger(is_connected=True, state=ChargerState.BUSY_NON_RELEASED),
        control.start_attempts,
    )
    client.start_charge.side_effect = ChargeStartError(ChargeStartStep.CONFIRM, True)
    with pytest.raises(HomeAssistantError):
        await control.async_start()
    control.on_charger_read(
        CONNECTED, control.start_attempts
    )  # AVAILABLE after a pre-block read
    assert control.state.blocked
    control.on_charger_read(
        make_charger(is_connected=True, state=ChargerState.BUSY_NON_RELEASED),
        control.start_attempts,
    )
    control.on_charger_read(CONNECTED, control.start_attempts)
    assert not control.state.blocked


async def test_turn_on_after_turn_off_clears_stop_asked(
    control: ChargeControl, client: AsyncMock
) -> None:
    """turn_on during a pending start with a stop asked clears it, no API call."""
    await control.async_start()
    await control.async_stop()
    await control.async_start()
    assert control.state == PENDING
    client.start_charge.assert_awaited_once()


async def test_stop_calls_stop_charge(
    control: ChargeControl, client: AsyncMock
) -> None:
    """A charge open: stop_charge once."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    client.stop_charge.assert_awaited_once()


async def test_stop_while_stopping_is_noop(
    control: ChargeControl, client: AsyncMock
) -> None:
    """charge_state STOPPING: no API call."""
    control.on_charger_read(
        make_charger(is_connected=True, charge_state=ChargeState.STOPPING),
        control.start_attempts,
    )
    await control.async_stop()
    client.stop_charge.assert_not_awaited()
    assert control.state == IDLE  # and no stop is stored: the charge is ending already


async def test_stop_no_active_charge_asks_for_a_read(
    hass: HomeAssistant,
    control: ChargeControl,
    client: AsyncMock,
    request_refresh: AsyncMock,
) -> None:
    """NoActiveChargeError: not an error, but a read is asked for."""
    control.on_charger_read(CHARGING, control.start_attempts)
    client.stop_charge.side_effect = NoActiveChargeError("x")
    await control.async_stop()
    await hass.async_block_till_done()
    client.stop_charge.assert_awaited_once()
    request_refresh.assert_awaited()


async def test_stop_auth_error_starts_reauth(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    client: AsyncMock,
    request_refresh: AsyncMock,
) -> None:
    """AuthError starts reauth and raises auth_failed, from None; no read is asked for."""
    control.on_charger_read(CHARGING, control.start_attempts)
    client.stop_charge.side_effect = AuthError("x")
    with pytest.raises(HomeAssistantError) as exc_info:
        await control.async_stop()
    assert exc_info.value.translation_key == "auth_failed"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__
    client.stop_charge.assert_awaited_once()
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert any(flow["context"]["source"] == "reauth" for flow in flows)
    assert control.state == STOP_ASKED_ONLY
    request_refresh.assert_not_awaited()  # reauth takes over: a read would be rejected too


async def test_stop_sets_pending_stop(
    control: ChargeControl, client: AsyncMock, on_change: MagicMock
) -> None:
    """A successful stop is pending: the switch shows off until the charger follows."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    client.stop_charge.assert_awaited_once()
    assert control.state == STOP_PENDING
    on_change.assert_called()


async def test_stop_while_stop_pending_is_noop(
    control: ChargeControl, client: AsyncMock
) -> None:
    """A second turn_off while the stop is pending makes no API call."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    client.stop_charge.assert_awaited_once()


async def test_start_while_stop_pending_is_refused(
    control: ChargeControl, client: AsyncMock
) -> None:
    """turn_on while a stop is pending raises stop_pending; no start, no attempt counted."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    attempts = control.start_attempts
    with pytest.raises(ServiceValidationError) as exc_info:
        await control.async_start()
    assert exc_info.value.translation_key == "stop_pending"
    client.start_charge.assert_not_awaited()
    assert control.start_attempts == attempts


@pytest.mark.parametrize(
    "charger",
    [
        make_charger(
            is_connected=True,
            charge_state=ChargeState.STOPPING,
            state=ChargerState.BUSY_CHARGING,
        ),
        make_charger(is_connected=True, charge_state=ChargeState.COMPLETED),
        make_charger(is_connected=True, state=ChargerState.BUSY_NON_RELEASED),
        make_charger(is_connected=False),
    ],
)
async def test_pending_stop_ends_when_the_charge_is_not_on(
    control: ChargeControl, charger: Any
) -> None:
    """A read with STOPPING, COMPLETED or no open charge ends the pending stop."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    control.on_charger_read(charger, control.start_attempts)
    assert control.state == IDLE


@pytest.mark.parametrize(
    "charger",
    [
        make_charger(is_connected=True, charge_state=ChargeState.CHARGING),
        make_charger(is_connected=True, charge_state=ChargeState.PAUSED),
        # Not evidence that the charge is off: the pending stop runs its 2 minutes (D50).
        make_charger(is_connected=True, charge_state=ChargeState.UNKNOWN),
        BUSY_NO_CHARGE_STATE,
    ],
)
async def test_pending_stop_stays_while_the_charge_is_on(
    hass: HomeAssistant, control: ChargeControl, client: AsyncMock, charger: Any
) -> None:
    """A read that doesn't show the charge off keeps the pending stop, and makes no second call.

    That is a charge still on (the charger lags), an open charge in an unknown state, and an
    open charger without a charge object.
    """
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    control.on_charger_read(charger, control.start_attempts)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert control.state == STOP_PENDING
    client.stop_charge.assert_awaited_once()


async def test_pending_stop_stays_on_a_stale_read(control: ChargeControl) -> None:
    """A stale read (begun before the latest start attempt) still showing CHARGING keeps it."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    control.on_charger_read(CHARGING, control.start_attempts - 1)
    assert control.state == STOP_PENDING


async def test_stop_after_the_timeout_without_a_read(
    hass: HomeAssistant,
    control: ChargeControl,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Once the pending stop has timed out, turn_off stops again."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    await _fire(hass, freezer, STOP_CONFIRM_TIMEOUT)
    await control.async_stop()
    assert client.stop_charge.await_count == 2


async def test_start_after_the_timeout_takes_the_normal_checks(
    hass: HomeAssistant,
    control: ChargeControl,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Once the pending stop has timed out, turn_on isn't refused; the open charge makes it a no-op."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    await _fire(hass, freezer, STOP_CONFIRM_TIMEOUT)
    await control.async_start()
    client.start_charge.assert_not_awaited()
    assert control.state == IDLE


async def test_read_without_the_charge_ends_the_stop_timer(
    hass: HomeAssistant,
    control: ChargeControl,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A read that sees the charge off ends the pending stop; the wait's timer does nothing later."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    control.on_charger_read(CONNECTED, control.start_attempts)
    assert control.state == IDLE
    await _fire(hass, freezer, STOP_CONFIRM_TIMEOUT)
    assert "Stopping the charge failed" not in caplog.text


async def test_stop_timer_does_nothing_after_shutdown(
    hass: HomeAssistant,
    control: ChargeControl,
    freezer: FrozenDateTimeFactory,
    on_change: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """After unload the wait's timer changes nothing."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    await control.async_shutdown()
    on_change.reset_mock()
    await _fire(hass, freezer, STOP_CONFIRM_TIMEOUT)
    assert control.state == STOP_PENDING
    assert "Stopping the charge failed" not in caplog.text
    on_change.assert_not_called()


async def test_stop_timer_after_the_stop_ended_does_nothing(
    hass: HomeAssistant,
    control: ChargeControl,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A wait timer whose work waits for the lock while a read ends the pending stop does nothing."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    async with control._lock:  # noqa: SLF001
        freezer.tick(STOP_CONFIRM_TIMEOUT)
        async_fire_time_changed(hass)
        await asyncio.sleep(0)
        control.on_charger_read(CONNECTED, control.start_attempts)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert control.state == IDLE
    assert "Stopping the charge failed" not in caplog.text


async def test_background_stop_leaves_one_stop_timer(
    hass: HomeAssistant,
    control: ChargeControl,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A stop asked during a pending start, sent by the read's try: one wait timer, and one timeout warning."""
    await control.async_start()
    await control.async_stop()  # asked during the pending start
    control.on_charger_read(CHARGING, control.start_attempts)
    await hass.async_block_till_done(wait_background_tasks=True)
    client.stop_charge.assert_awaited_once()
    assert _timers(hass, f"{DOMAIN} stop wait") == 1
    await _fire(hass, freezer, STOP_CONFIRM_TIMEOUT)
    assert caplog.text.count("Stopping the charge failed") == 1


async def test_turn_off_before_the_background_stop_is_noop(
    hass: HomeAssistant, control: ChargeControl, client: AsyncMock
) -> None:
    """A turn_off queued ahead of the background stop sends no second stop (Review Focus 1)."""
    await control.async_start()
    await control.async_stop()
    await control._lock.acquire()  # noqa: SLF001
    stop = hass.async_create_task(control.async_stop())
    await asyncio.sleep(0)  # the turn_off queues for the lock first
    control.on_charger_read(
        CHARGING, control.start_attempts
    )  # the background stop second
    control._lock.release()  # noqa: SLF001
    await stop
    await hass.async_block_till_done(wait_background_tasks=True)
    client.stop_charge.assert_awaited_once()


async def test_clear_block(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    client: AsyncMock,
    hass_storage: dict[str, Any],
) -> None:
    """clear_block (the fix flow) clears the block and its stored reason, and deletes the issue."""
    client.start_charge.side_effect = ChargeStartError(ChargeStartStep.CONFIRM, True)
    with pytest.raises(HomeAssistantError):
        await control.async_start()
    control.clear_block()
    assert control.state == IDLE
    assert _issue(hass, entry) is None
    saved = await _saved(hass, entry, hass_storage)
    assert saved["blocked_since"] is None
    assert saved["block_reason"] is None


async def test_store_round_trip(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    client: AsyncMock,
    hass_storage: dict[str, Any],
) -> None:
    """A new control loads the saved block and pending start, and recreates the issue."""
    client.start_charge.side_effect = ChargeStartError(ChargeStartStep.CONFIRM, True)
    with pytest.raises(HomeAssistantError):
        await control.async_start()
    async_fire_time_changed(hass)  # the delayed save's timer
    await hass.async_block_till_done()
    saved = hass_storage[STORE_KEY.format(entry.entry_id)]["data"]
    assert saved["blocked_since"] is not None
    assert saved["block_reason"] == "start_blocked"
    ir.async_delete_issue(hass, DOMAIN, f"start_blocked_{entry.entry_id}")
    again = ChargeControl(
        hass, entry, client, on_change=MagicMock(), request_refresh=AsyncMock()
    )
    await again.async_load()
    assert again.state == BLOCKED
    assert _issue(hass, entry) is not None


@pytest.mark.parametrize(
    "data",
    [
        {"blocked_since": 5},
        {"blocked_since": None, "start_pending_since": "no", "stop_asked": False},
        {},
        {
            "blocked_since": "2026-09-26T20:00:00",
            "start_pending_since": None,
            "stop_asked": False,
        },
        {"blocked_since": None, "start_pending_since": None, "stop_asked": "yes"},
    ],
)
async def test_wrong_shape_store_blocks(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    client: AsyncMock,
    hass_storage: dict[str, Any],
    data: dict[str, Any],
) -> None:
    """A stored file of the wrong shape blocks starts, with the store issue."""
    hass_storage[STORE_KEY.format(entry.entry_id)] = {
        "version": 1,
        "key": STORE_KEY.format(entry.entry_id),
        "data": data,
    }
    control = ChargeControl(
        hass, entry, client, on_change=MagicMock(), request_refresh=AsyncMock()
    )
    await control.async_load()
    assert control.state == BLOCKED
    issue = _issue(hass, entry)
    assert issue is not None
    assert issue.translation_key == "start_blocked_store"


async def test_corrupt_store_blocks(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    client: AsyncMock,
    hass_storage: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A store file that was there and loads as nothing blocks starts, and the block is saved (#26)."""
    control = ChargeControl(
        hass, entry, client, on_change=MagicMock(), request_refresh=AsyncMock()
    )
    with patch(
        "custom_components.nortec_go.charge_control_store._file_exists",
        return_value=True,
    ):
        await control.async_load()
    assert control.state == BLOCKED
    issue = _issue(hass, entry)
    assert issue is not None
    assert issue.translation_key == "start_blocked_store"
    assert "The saved start guard couldn't be read" in caplog.text
    async_fire_time_changed(hass)  # the delayed save's timer
    await hass.async_block_till_done()
    saved = hass_storage[STORE_KEY.format(entry.entry_id)]["data"]
    assert saved["block_reason"] == "start_blocked_store"
    with pytest.raises(ServiceValidationError):
        await control.async_start()
    client.start_charge.assert_not_awaited()


async def test_missing_store_does_not_block(
    hass: HomeAssistant, entry: MockConfigEntry, client: AsyncMock
) -> None:
    """No store file is a first setup: nothing is blocked."""
    control = ChargeControl(
        hass, entry, client, on_change=MagicMock(), request_refresh=AsyncMock()
    )
    await control.async_load()
    assert control.state == IDLE
    assert _issue(hass, entry) is None


@pytest.mark.parametrize("reason", ["start_blocked", "start_blocked_store"])
async def test_block_reason_survives_a_reload(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    client: AsyncMock,
    hass_storage: dict[str, Any],
    reason: str,
) -> None:
    """The repair issue comes back with the text of the block's own reason (#26)."""
    key = STORE_KEY.format(entry.entry_id)
    hass_storage[key] = {
        "version": 1,
        "minor_version": 2,
        "key": key,
        "data": {
            "blocked_since": "2026-09-26T20:00:00+00:00",
            "block_reason": reason,
            "start_pending_since": None,
            "stop_asked_since": None,
            "stop_tries": 0,
            "stop_tried_at": None,
        },
    }
    control = ChargeControl(
        hass, entry, client, on_change=MagicMock(), request_refresh=AsyncMock()
    )
    await control.async_load()
    assert control.state == BLOCKED
    issue = _issue(hass, entry)
    assert issue is not None
    assert issue.translation_key == reason
    await control.async_shutdown()
    assert hass_storage[key]["data"]["block_reason"] == reason


async def test_unexpected_start_error_is_translated_without_a_block(
    control: ChargeControl,
    client: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An exception that isn't the client's own is logged, raised as start_failed, and sets no block (#26)."""
    client.start_charge.side_effect = RuntimeError("boom")
    with pytest.raises(HomeAssistantError) as exc_info:
        await control.async_start()
    assert exc_info.value.translation_key == "start_failed"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__
    assert control.state == IDLE
    assert "Unexpected error while starting a charge" in caplog.text
    client.start_charge.assert_awaited_once()


async def test_remove_charge_control(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    client: AsyncMock,
    hass_storage: dict[str, Any],
) -> None:
    """Removal deletes the store and the issue."""
    client.start_charge.side_effect = ChargeStartError(ChargeStartStep.CONFIRM, True)
    with pytest.raises(HomeAssistantError):
        await control.async_start()
    async_fire_time_changed(hass)  # the delayed save's timer
    await hass.async_block_till_done()
    assert STORE_KEY.format(entry.entry_id) in hass_storage
    await async_remove_charge_control(hass, entry.entry_id)
    assert STORE_KEY.format(entry.entry_id) not in hass_storage
    assert _issue(hass, entry) is None


async def test_cancel_while_waiting_for_the_lock_doesnt_block(
    hass: HomeAssistant, control: ChargeControl, client: AsyncMock
) -> None:
    """A start cancelled while queued behind a stop made no API call: no block."""
    control.on_charger_read(CHARGING, control.start_attempts)
    release = asyncio.Event()

    async def slow_stop() -> None:
        await release.wait()

    client.stop_charge.side_effect = slow_stop
    stop = hass.async_create_task(control.async_stop())
    await asyncio.sleep(0)
    start = hass.async_create_task(control.async_start())
    await asyncio.sleep(0)
    start.cancel()
    release.set()
    await stop
    with pytest.raises(asyncio.CancelledError):
        await start
    assert not control.state.blocked
    client.start_charge.assert_not_awaited()


async def test_shutdown_waits_and_refuses(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    client: AsyncMock,
    hass_storage: dict[str, Any],
) -> None:
    """Shutdown lets a start in flight finish and save its block, then refuses new calls."""
    release = asyncio.Event()

    async def slow_start() -> None:
        await release.wait()
        raise ChargeStartError(ChargeStartStep.CONFIRM, True)

    client.start_charge.side_effect = slow_start
    start = hass.async_create_task(control.async_start())
    await asyncio.sleep(0)
    shutdown = hass.async_create_task(control.async_shutdown())
    await asyncio.sleep(0)
    assert not shutdown.done()
    release.set()
    with pytest.raises(HomeAssistantError):
        await start
    await shutdown
    saved = hass_storage[STORE_KEY.format(entry.entry_id)]["data"]
    assert saved["blocked_since"] is not None
    with pytest.raises(HomeAssistantError) as exc_info:
        await control.async_start()
    assert exc_info.value.translation_key == "unloading"
    with pytest.raises(HomeAssistantError):
        await control.async_stop()


async def test_background_stop_after_shutdown_does_nothing(
    control: ChargeControl, client: AsyncMock
) -> None:
    """A background stop that gets the lock after the unload makes no API call."""
    await control.async_shutdown()
    await control._async_background_stop()  # noqa: SLF001
    client.stop_charge.assert_not_awaited()


async def test_read_after_shutdown_changes_nothing(
    control: ChargeControl, client: AsyncMock
) -> None:
    """After the unload, a read keeps the block: the reloaded control owns the store."""
    client.start_charge.side_effect = ChargeStartError(ChargeStartStep.CONFIRM, True)
    with pytest.raises(HomeAssistantError):
        await control.async_start()
    await control.async_shutdown()
    control.on_charger_read(make_charger(is_connected=False), control.start_attempts)
    assert control.state == BLOCKED


async def test_clear_block_when_not_blocked(
    control: ChargeControl, on_change: MagicMock
) -> None:
    """clear_block without a block does nothing."""
    control.clear_block()
    assert control.state == IDLE
    on_change.assert_not_called()


async def test_stop_without_an_open_charge_calls_stop_charge(
    control: ChargeControl, client: AsyncMock
) -> None:
    """A read charger with no open charge: the stop is still sent; the client decides."""
    control.on_charger_read(CONNECTED, control.start_attempts)
    await control.async_stop()
    client.stop_charge.assert_awaited_once()


@pytest.mark.parametrize(
    ("control", "expected"), [(PENDING, "starting"), (STOP_ASKED, "stopping")]
)
def test_charge_status_pending_start_before_unknown_charger_state(
    control: ChargeControlState, expected: str
) -> None:
    """A pending start with no charge seen shows before the charger's unknown state."""
    charger = make_charger(is_connected=True, state=ChargerState.UNKNOWN)
    assert charge_status(charger, control) == expected


@pytest.mark.parametrize(
    ("charger", "stoppable", "off"),
    [
        (CHARGING, True, False),
        (make_charger(is_connected=True, charge_state=ChargeState.PAUSED), True, False),
        (
            make_charger(is_connected=True, charge_state=ChargeState.UNKNOWN),
            True,
            False,
        ),
        (NOT_STOPPABLE, False, False),
        (BUSY_NO_CHARGE_STATE, False, False),
        (
            make_charger(is_connected=True, charge_state=ChargeState.STOPPING),
            False,
            True,
        ),
        (
            make_charger(is_connected=True, charge_state=ChargeState.COMPLETED),
            False,
            True,
        ),
        (CONNECTED, False, True),
        (make_charger(is_connected=False), False, True),
        (
            make_charger(is_connected=True, state=ChargerState.BUSY_NON_RELEASED),
            False,
            True,
        ),
        (make_charger(is_connected=True, state=ChargerState.UNKNOWN), False, False),
    ],
)
def test_stoppable_and_off(charger: Any, stoppable: bool, off: bool) -> None:
    """Stoppable needs a charge that can be stopped and isn't ending; off needs a known charger state."""
    assert is_stoppable(charger) is stoppable
    assert is_charge_off(charger) is off


async def test_stop_during_pending_start(
    hass: HomeAssistant, control: ChargeControl, client: AsyncMock
) -> None:
    """Stop asked during a pending start: no call until a read sees the charge, then one."""
    await control.async_start()
    await control.async_stop()
    client.stop_charge.assert_not_awaited()
    assert control.state == STOP_ASKED
    control.on_charger_read(CHARGING, control.start_attempts)
    await hass.async_block_till_done(wait_background_tasks=True)
    client.stop_charge.assert_awaited_once()
    assert control.state == STOP_PENDING


async def test_no_call_while_a_start_is_pending(
    hass: HomeAssistant, control: ChargeControl, client: AsyncMock
) -> None:
    """A turn-off during a pending start makes no call, also when the last (stale) read shows a charge."""
    attempts_before = control.start_attempts
    await control.async_start()
    control.on_charger_read(CHARGING, attempts_before)  # stale: the start stays pending
    assert control.state == PENDING
    await control.async_stop()
    client.stop_charge.assert_not_awaited()
    assert control.state == STOP_ASKED
    control.on_charger_read(CHARGING, control.start_attempts)
    await hass.async_block_till_done(wait_background_tasks=True)
    client.stop_charge.assert_awaited_once()


async def test_open_charger_without_a_charge_gets_no_call(
    hass: HomeAssistant, control: ChargeControl, client: AsyncMock
) -> None:
    """An open charger with no charge object ends the pending start, but the stop waits (D50)."""
    await control.async_start()
    await control.async_stop()
    control.on_charger_read(BUSY_NO_CHARGE_STATE, control.start_attempts)
    await hass.async_block_till_done(wait_background_tasks=True)
    client.stop_charge.assert_not_awaited()
    assert control.state == STOP_ASKED_ONLY
    control.on_charger_read(CHARGING, control.start_attempts)
    await hass.async_block_till_done(wait_background_tasks=True)
    client.stop_charge.assert_awaited_once()


async def test_stop_outlives_the_start_deadline(
    hass: HomeAssistant,
    control: ChargeControl,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The start deadline blocks, as before, and no longer drops the stop (#85, case 2)."""
    await control.async_start()
    await control.async_stop()
    await _fire(hass, freezer, START_CONFIRM_TIMEOUT)
    assert control.state == ChargeControlState(blocked=True, stop_asked=True)
    control.on_charger_read(CHARGING, control.start_attempts)
    await hass.async_block_till_done(wait_background_tasks=True)
    client.stop_charge.assert_awaited_once()
    assert control.state == STOP_PENDING  # the charge seen cleared the block (D26)
    client.start_charge.assert_awaited_once()


async def test_stop_ends_when_no_charge_came(
    hass: HomeAssistant,
    control: ChargeControl,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """After the deadline, a read that shows no charge ends the stop without a call."""
    await control.async_start()
    await control.async_stop()
    await _fire(hass, freezer, START_CONFIRM_TIMEOUT)
    control.on_charger_read(CONNECTED, control.start_attempts)
    assert control.state == BLOCKED
    client.stop_charge.assert_not_awaited()


@pytest.mark.parametrize(
    "error",
    [
        ChargeNotStoppableError("x"),
        NortecGoConnectionError("x"),
        ApiError("POST /example", 500),
    ],
)
async def test_failed_stop_is_tried_again_after_the_wait(
    hass: HomeAssistant,
    control: ChargeControl,
    client: AsyncMock,
    request_refresh: AsyncMock,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
) -> None:
    """A failed call raises nothing, logs its number, keeps the stop and asks for a read; the next call waits 2 minutes."""
    control.on_charger_read(CHARGING, control.start_attempts)
    client.stop_charge.side_effect = error
    await control.async_stop()
    await hass.async_block_till_done()
    client.stop_charge.assert_awaited_once()
    assert control.state == STOP_ASKED_ONLY
    assert (
        f"Stopping the charge failed (try 1 of 10): {type(error).__name__}"
        in caplog.text
    )
    # The read starts the 30 s reads: a new interval only applies from the next read.
    request_refresh.assert_awaited_once()

    client.stop_charge.side_effect = None
    await _fire(hass, freezer, STOP_CONFIRM_TIMEOUT - timedelta(seconds=1))
    control.on_charger_read(CHARGING, control.start_attempts)
    await hass.async_block_till_done(wait_background_tasks=True)
    client.stop_charge.assert_awaited_once()  # the reads work, but the wait runs

    await _fire(hass, freezer, timedelta(seconds=1))
    control.on_charger_read(CHARGING, control.start_attempts)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert client.stop_charge.await_count == 2
    assert control.state == STOP_PENDING


async def test_no_active_charge_does_not_end_the_stop(
    hass: HomeAssistant,
    control: ChargeControl,
    client: AsyncMock,
    request_refresh: AsyncMock,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The answer "no active charge" is no evidence: the stop stays until a read decides (D50)."""
    client.stop_charge.side_effect = NoActiveChargeError("x")
    await control.async_stop()  # the last read shows an idle charger: the call is made
    await hass.async_block_till_done()
    client.stop_charge.assert_awaited_once()
    assert control.state == STOP_ASKED_ONLY
    request_refresh.assert_awaited()
    assert "Stopping the charge failed" not in caplog.text

    control.on_charger_read(BUSY_NO_CHARGE_STATE, control.start_attempts)
    assert control.state == STOP_ASKED_ONLY  # a charge is opening: the stop waits

    client.stop_charge.side_effect = None
    await _fire(hass, freezer, STOP_CONFIRM_TIMEOUT)
    control.on_charger_read(CHARGING, control.start_attempts)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert client.stop_charge.await_count == 2


async def test_no_active_charge_then_a_read_without_a_charge_ends_the_stop(
    hass: HomeAssistant, control: ChargeControl, client: AsyncMock
) -> None:
    """A turn-off on an idle charger: one call, and the read that shows no charge ends the stop."""
    client.stop_charge.side_effect = NoActiveChargeError("x")
    await control.async_stop()
    control.on_charger_read(CONNECTED, control.start_attempts)
    assert control.state == IDLE
    client.stop_charge.assert_awaited_once()


async def test_charge_the_read_says_cant_be_stopped_gets_no_call(
    hass: HomeAssistant,
    control: ChargeControl,
    client: AsyncMock,
    request_refresh: AsyncMock,
) -> None:
    """A charge that can't be stopped yet: stored, a read asked for, no call until a read says it can (#32)."""
    control.on_charger_read(NOT_STOPPABLE, control.start_attempts)
    await control.async_stop()
    await hass.async_block_till_done()
    client.stop_charge.assert_not_awaited()
    assert control.state == STOP_ASKED_ONLY
    request_refresh.assert_awaited()
    control.on_charger_read(NOT_STOPPABLE, control.start_attempts)
    await hass.async_block_till_done(wait_background_tasks=True)
    client.stop_charge.assert_not_awaited()
    control.on_charger_read(CHARGING, control.start_attempts)
    await hass.async_block_till_done(wait_background_tasks=True)
    client.stop_charge.assert_awaited_once()


async def test_stale_read_changes_nothing_about_the_stop(
    hass: HomeAssistant, control: ChargeControl, client: AsyncMock
) -> None:
    """A stale read neither ends a pending stop nor sends a stored stop (D26, D50)."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    control.on_charger_read(
        make_charger(is_connected=True, charge_state=ChargeState.STOPPING),
        control.start_attempts - 1,
    )
    assert control.state == STOP_PENDING


async def test_stale_read_sends_no_stop(
    hass: HomeAssistant, control: ChargeControl, client: AsyncMock
) -> None:
    """A stored stop waiting for its charge isn't sent by a stale read."""
    control.on_charger_read(NOT_STOPPABLE, control.start_attempts)
    await control.async_stop()
    control.on_charger_read(CHARGING, control.start_attempts - 1)
    await hass.async_block_till_done(wait_background_tasks=True)
    client.stop_charge.assert_not_awaited()


async def test_accepted_stop_without_effect_has_failed(
    hass: HomeAssistant,
    control: ChargeControl,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    on_change: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """2 minutes after an accepted stop with the charge still on, the try has failed and the next read tries again."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    await _fire(hass, freezer, STOP_CONFIRM_TIMEOUT - timedelta(seconds=1))
    control.on_charger_read(CHARGING, control.start_attempts)
    assert control.state == STOP_PENDING
    on_change.reset_mock()
    await _fire(hass, freezer, timedelta(seconds=1))
    assert control.state == STOP_ASKED_ONLY
    assert (
        "Stopping the charge failed (try 1 of 10): the charge was still on"
        in caplog.text
    )
    on_change.assert_called()
    control.on_charger_read(CHARGING, control.start_attempts)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert client.stop_charge.await_count == 2
    assert control.state == STOP_PENDING


async def test_try_in_flight_shows_off_and_the_charges_own_state(
    hass: HomeAssistant, control: ChargeControl, client: AsyncMock
) -> None:
    """While a queued try is in flight the switch is off and the status is the charge's own; Stopping once accepted."""
    release = asyncio.Event()

    async def slow_stop() -> None:
        await release.wait()

    client.stop_charge.side_effect = slow_stop
    await control.async_start()
    await control.async_stop()
    control.on_charger_read(CHARGING, control.start_attempts)
    assert control.state == STOP_ASKED_ONLY
    assert not is_charge_on(CHARGING, control.state)
    assert charge_status(CHARGING, control.state) == "charging"
    release.set()
    await hass.async_block_till_done(wait_background_tasks=True)
    client.stop_charge.assert_awaited_once()
    assert control.state == STOP_PENDING
    assert charge_status(CHARGING, control.state) == "stopping"


@pytest.mark.parametrize(
    "error",
    [
        NoActiveChargeError("x"),
        ChargeNotStoppableError("x"),
        AuthError("x"),
        NortecGoConnectionError("x"),
    ],
)
async def test_queued_try_without_success_keeps_the_stop(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    client: AsyncMock,
    error: Exception,
) -> None:
    """A try queued by a read that fails raises nowhere and keeps the stop; a rejected session starts reauth."""
    client.stop_charge.side_effect = error
    with patch.object(entry, "async_start_reauth", MagicMock()) as reauth:
        await control.async_start()
        await control.async_stop()
        control.on_charger_read(CHARGING, control.start_attempts)
        await hass.async_block_till_done(wait_background_tasks=True)
    client.stop_charge.assert_awaited_once()
    assert control.state == STOP_ASKED_ONLY
    assert reauth.called is isinstance(error, AuthError)


async def test_auth_error_logs_no_error_text(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    client: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A rejected session is logged by what it is, not by the client's text."""
    control.on_charger_read(CHARGING, control.start_attempts)
    client.stop_charge.side_effect = AuthError("some text from the service")
    with (
        patch.object(entry, "async_start_reauth", MagicMock()),
        pytest.raises(HomeAssistantError),
    ):
        await control.async_stop()
    assert "(try 1 of 10): the session was rejected" in caplog.text
    assert "some text from the service" not in caplog.text


async def test_two_reads_make_one_call(
    hass: HomeAssistant, control: ChargeControl, client: AsyncMock
) -> None:
    """A second read while a try is in flight queues nothing."""
    release = asyncio.Event()

    async def slow_stop() -> None:
        await release.wait()

    client.stop_charge.side_effect = slow_stop
    await control.async_start()
    await control.async_stop()
    control.on_charger_read(CHARGING, control.start_attempts)
    control.on_charger_read(CHARGING, control.start_attempts)
    release.set()
    await hass.async_block_till_done(wait_background_tasks=True)
    client.stop_charge.assert_awaited_once()


async def test_turn_off_then_a_read_make_one_call(
    hass: HomeAssistant, control: ChargeControl, client: AsyncMock
) -> None:
    """A read while a turn-off's call is in flight queues nothing, and none follows the accepted call."""
    control.on_charger_read(CHARGING, control.start_attempts)
    release = asyncio.Event()

    async def slow_stop() -> None:
        await release.wait()

    client.stop_charge.side_effect = slow_stop
    stop = hass.async_create_task(control.async_stop())
    await asyncio.sleep(0)
    control.on_charger_read(CHARGING, control.start_attempts)
    release.set()
    await stop
    control.on_charger_read(CHARGING, control.start_attempts)
    await hass.async_block_till_done(wait_background_tasks=True)
    client.stop_charge.assert_awaited_once()


async def test_repeated_turn_off_keeps_the_time_and_the_count(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    hass_storage: dict[str, Any],
) -> None:
    """A turn-off while a stop is stored doesn't start it again, and makes no call inside the wait."""
    control.on_charger_read(CHARGING, control.start_attempts)
    client.stop_charge.side_effect = ChargeNotStoppableError("x")
    await control.async_stop()
    first = await _saved(hass, entry, hass_storage)
    assert first["stop_tries"] == 1
    freezer.tick(timedelta(seconds=30))
    await control.async_stop()
    again = await _saved(hass, entry, hass_storage)
    assert again == first
    client.stop_charge.assert_awaited_once()


async def test_turn_on_clears_a_stored_stop(
    hass: HomeAssistant, control: ChargeControl, client: AsyncMock
) -> None:
    """A turn-on with a stop stored and a charge open clears the stop and starts nothing."""
    control.on_charger_read(CHARGING, control.start_attempts)
    client.stop_charge.side_effect = ChargeNotStoppableError("x")
    await control.async_stop()
    assert control.state == STOP_ASKED_ONLY
    await control.async_start()
    assert control.state == IDLE
    client.start_charge.assert_not_awaited()


async def test_turn_on_clears_a_stored_stop_before_a_refused_start(
    hass: HomeAssistant,
    control: ChargeControl,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The stop is cleared whatever the start then does: here starts are blocked."""
    await control.async_start()
    await control.async_stop()
    await _fire(hass, freezer, START_CONFIRM_TIMEOUT)
    assert control.state == ChargeControlState(blocked=True, stop_asked=True)
    with pytest.raises(ServiceValidationError):
        await control.async_start()
    assert control.state == BLOCKED
    client.start_charge.assert_awaited_once()


async def test_wait_holds_from_one_stop_to_the_next(
    hass: HomeAssistant,
    control: ChargeControl,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A new stop right after a failed call waits out what is left of the 2 minutes (D50)."""
    control.on_charger_read(CHARGING, control.start_attempts)
    client.stop_charge.side_effect = ChargeNotStoppableError("x")
    await control.async_stop()
    await control.async_start()  # clears the stop; the charge is open, so no start
    client.stop_charge.side_effect = None
    await control.async_stop()
    client.stop_charge.assert_awaited_once()
    assert control.state == STOP_ASKED_ONLY
    await _fire(hass, freezer, STOP_CONFIRM_TIMEOUT)
    control.on_charger_read(CHARGING, control.start_attempts)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert client.stop_charge.await_count == 2


async def test_reload_right_after_a_call_waits_and_keeps_the_count(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    hass_storage: dict[str, Any],
) -> None:
    """A reloaded control has the stop, its count and what is left of the wait; the pending stop isn't stored."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    await control.async_shutdown()
    saved = hass_storage[STORE_KEY.format(entry.entry_id)]["data"]
    assert saved["stop_asked_since"] is not None
    assert saved["stop_tries"] == 1
    assert saved["stop_tried_at"] is not None

    again = ChargeControl(
        hass, entry, client, on_change=MagicMock(), request_refresh=AsyncMock()
    )
    await again.async_load()
    assert again.state == STOP_ASKED_ONLY
    again.on_charger_read(CHARGING, again.start_attempts)
    await hass.async_block_till_done(wait_background_tasks=True)
    client.stop_charge.assert_awaited_once()  # the charger lags: no second call yet

    await _fire(hass, freezer, STOP_CONFIRM_TIMEOUT)
    again.on_charger_read(CHARGING, again.start_attempts)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert client.stop_charge.await_count == 2
    await again.async_shutdown()
    assert hass_storage[STORE_KEY.format(entry.entry_id)]["data"]["stop_tries"] == 2


async def test_wait_at_load_is_never_more_than_2_minutes(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    hass_storage: dict[str, Any],
) -> None:
    """A stored try time in the future (a clock change) gives a wait of 2 minutes, not more."""
    key = STORE_KEY.format(entry.entry_id)
    now = dt_util.utcnow()
    hass_storage[key] = {
        "version": 1,
        "minor_version": 2,
        "key": key,
        "data": {
            "blocked_since": None,
            "block_reason": None,
            "start_pending_since": None,
            "stop_asked_since": now.isoformat(),
            "stop_tries": 1,
            "stop_tried_at": (now + timedelta(hours=3)).isoformat(),
        },
    }
    control = ChargeControl(
        hass, entry, client, on_change=MagicMock(), request_refresh=AsyncMock()
    )
    await control.async_load()
    await _fire(hass, freezer, STOP_CONFIRM_TIMEOUT)
    control.on_charger_read(CHARGING, control.start_attempts)
    await hass.async_block_till_done(wait_background_tasks=True)
    client.stop_charge.assert_awaited_once()
    await control.async_shutdown()


async def test_queued_try_that_makes_no_call_starts_no_wait(
    hass: HomeAssistant, control: ChargeControl, client: AsyncMock
) -> None:
    """A try queued by a read, then overtaken by a turn-on, makes no call and blocks no later one."""
    await control.async_start()
    await control.async_stop()
    await control._lock.acquire()  # noqa: SLF001
    start = hass.async_create_task(control.async_start())
    await asyncio.sleep(0)  # the turn-on queues for the lock first
    control.on_charger_read(CHARGING, control.start_attempts)  # the try second
    control._lock.release()  # noqa: SLF001
    await start
    await hass.async_block_till_done(wait_background_tasks=True)
    client.stop_charge.assert_not_awaited()
    assert control.state == IDLE
    await control.async_stop()
    client.stop_charge.assert_awaited_once()


async def test_slow_call_waits_from_its_answer(
    hass: HomeAssistant,
    control: ChargeControl,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The 2 minutes run from the charger's answer: a call that took 3 minutes isn't judged at once."""
    control.on_charger_read(CHARGING, control.start_attempts)
    release = asyncio.Event()

    async def slow_stop() -> None:
        await release.wait()

    client.stop_charge.side_effect = slow_stop
    stop = hass.async_create_task(control.async_stop())
    await asyncio.sleep(0)
    freezer.tick(timedelta(minutes=3))
    async_fire_time_changed(hass)
    release.set()
    await stop
    assert control.state == STOP_PENDING
    await _fire(hass, freezer, STOP_CONFIRM_TIMEOUT - timedelta(seconds=1))
    assert control.state == STOP_PENDING
    assert "Stopping the charge failed" not in caplog.text
    await _fire(hass, freezer, timedelta(seconds=1))
    assert control.state == STOP_ASKED_ONLY


async def test_cancelled_call_keeps_the_stop_and_counts(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    client: AsyncMock,
    hass_storage: dict[str, Any],
) -> None:
    """A cancelled call was made: the stop stays, the try counts, and the wait runs."""
    control.on_charger_read(CHARGING, control.start_attempts)
    release = asyncio.Event()

    async def slow_stop() -> None:
        await release.wait()

    client.stop_charge.side_effect = slow_stop
    stop = hass.async_create_task(control.async_stop())
    await asyncio.sleep(0)
    stop.cancel()
    with pytest.raises(asyncio.CancelledError):
        await stop
    assert control.state == STOP_ASKED_ONLY
    saved = await _saved(hass, entry, hass_storage)
    assert saved["stop_tries"] == 1
    client.stop_charge.side_effect = None
    control.on_charger_read(CHARGING, control.start_attempts)
    await hass.async_block_till_done(wait_background_tasks=True)
    client.stop_charge.assert_awaited_once()


async def test_call_cancelled_with_a_failed_setup_arms_no_timer(
    hass: HomeAssistant, control: ChargeControl, client: AsyncMock
) -> None:
    """A failed setup closes the control before it cancels the call: no timer is left on a dead control."""
    control.on_charger_read(CHARGING, control.start_attempts)
    release = asyncio.Event()

    async def slow_stop() -> None:
        await release.wait()

    client.stop_charge.side_effect = slow_stop
    stop = hass.async_create_task(control.async_stop())
    await asyncio.sleep(0)
    control._async_close()  # noqa: SLF001  (what the entry runs when a setup fails)
    stop.cancel()
    with pytest.raises(asyncio.CancelledError):
        await stop
    assert _timers(hass, f"{DOMAIN} stop wait") == 0
    assert control.state == STOP_ASKED_ONLY


async def test_completed_charge_gets_no_call(
    hass: HomeAssistant,
    control: ChargeControl,
    client: AsyncMock,
    request_refresh: AsyncMock,
) -> None:
    """A last read with a completed charge: the turn-off calls nothing, asks for a read, and that read ends the stop."""
    completed = make_charger(is_connected=True, charge_state=ChargeState.COMPLETED)
    control.on_charger_read(completed, control.start_attempts)
    await control.async_stop()
    await hass.async_block_till_done()
    client.stop_charge.assert_not_awaited()
    assert control.state == STOP_ASKED_ONLY
    request_refresh.assert_awaited()
    control.on_charger_read(completed, control.start_attempts)
    assert control.state == IDLE
    client.stop_charge.assert_not_awaited()


async def test_read_that_ends_the_stop_during_a_call(
    hass: HomeAssistant, control: ChargeControl, client: AsyncMock
) -> None:
    """A read shows the charge off while the call is in flight: the accepted call leaves no pending stop behind."""
    control.on_charger_read(CHARGING, control.start_attempts)
    release = asyncio.Event()

    async def slow_stop() -> None:
        await release.wait()

    client.stop_charge.side_effect = slow_stop
    stop = hass.async_create_task(control.async_stop())
    await asyncio.sleep(0)
    control.on_charger_read(CONNECTED, control.start_attempts)
    assert control.state == IDLE
    release.set()
    await stop
    assert control.state == IDLE
    await control.async_start()  # not refused: no pending stop is under way
    client.start_charge.assert_awaited_once()


async def test_try_skipped_at_a_reload_is_sent_by_the_new_control(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    client: AsyncMock,
    hass_storage: dict[str, Any],
) -> None:
    """A reload between the read and the stop: the try is skipped, the stop is saved, and the reloaded control sends it (#26)."""
    await control.async_start()
    await control.async_stop()
    await control._lock.acquire()  # noqa: SLF001
    shutdown = hass.async_create_task(control.async_shutdown())
    await asyncio.sleep(0)  # the unload queues for the lock first
    control.on_charger_read(CHARGING, control.start_attempts)  # the try second
    control._lock.release()  # noqa: SLF001
    await shutdown
    await hass.async_block_till_done(wait_background_tasks=True)
    client.stop_charge.assert_not_awaited()
    saved = hass_storage[STORE_KEY.format(entry.entry_id)]["data"]
    assert saved["stop_asked_since"] is not None
    assert saved["start_pending_since"] is None
    assert saved["stop_tries"] == 0

    again = ChargeControl(
        hass, entry, client, on_change=MagicMock(), request_refresh=AsyncMock()
    )
    await again.async_load()
    assert again.state == STOP_ASKED_ONLY
    again.on_charger_read(CHARGING, again.start_attempts)
    await hass.async_block_till_done(wait_background_tasks=True)
    client.stop_charge.assert_awaited_once()
    client.start_charge.assert_awaited_once()
    await again.async_shutdown()


async def test_wait_timer_does_nothing_on_a_closed_control(
    hass: HomeAssistant,
    control: ChargeControl,
    freezer: FrozenDateTimeFactory,
    on_change: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A wait timer whose work waits for the lock while the entry closes judges nothing."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    async with control._lock:  # noqa: SLF001
        freezer.tick(STOP_CONFIRM_TIMEOUT)
        async_fire_time_changed(hass)
        await asyncio.sleep(0)
        control._async_close()  # noqa: SLF001
        on_change.reset_mock()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert control.state == STOP_PENDING
    assert "Stopping the charge failed" not in caplog.text
    on_change.assert_not_called()


async def test_unknown_charger_state_keeps_the_stop(
    hass: HomeAssistant, control: ChargeControl, client: AsyncMock
) -> None:
    """A charger in an unknown state with no charge isn't "off": the stop waits."""
    control.on_charger_read(CHARGING, control.start_attempts)
    client.stop_charge.side_effect = ChargeNotStoppableError("x")
    await control.async_stop()
    control.on_charger_read(
        make_charger(is_connected=True, state=ChargerState.UNKNOWN),
        control.start_attempts,
    )
    assert control.state == STOP_ASKED_ONLY


async def test_wait_over_at_load_sends_the_stop_at_once(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    client: AsyncMock,
    hass_storage: dict[str, Any],
) -> None:
    """A stored try time more than 2 minutes old leaves no wait: the first read sends the stop."""
    key = STORE_KEY.format(entry.entry_id)
    now = dt_util.utcnow()
    hass_storage[key] = {
        "version": 1,
        "minor_version": 2,
        "key": key,
        "data": {
            "blocked_since": None,
            "block_reason": None,
            "start_pending_since": None,
            "stop_asked_since": (now - timedelta(minutes=5)).isoformat(),
            "stop_tries": 1,
            "stop_tried_at": (now - timedelta(minutes=3)).isoformat(),
        },
    }
    control = ChargeControl(
        hass, entry, client, on_change=MagicMock(), request_refresh=AsyncMock()
    )
    await control.async_load()
    assert control.state == STOP_ASKED_ONLY
    assert _timers(hass, f"{DOMAIN} stop wait") == 0
    control.on_charger_read(CHARGING, control.start_attempts)
    await hass.async_block_till_done(wait_background_tasks=True)
    client.stop_charge.assert_awaited_once()
    client.start_charge.assert_not_awaited()
    await control.async_shutdown()
    assert hass_storage[key]["data"]["stop_tries"] == 2


async def test_failed_call_after_a_read_ended_the_stop_logs_no_warning(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    client: AsyncMock,
    caplog: pytest.LogCaptureFixture,
    hass_storage: dict[str, Any],
) -> None:
    """A read shows the charge off while a call that then fails is in flight: no stop is left to warn about."""
    control.on_charger_read(CHARGING, control.start_attempts)
    release = asyncio.Event()

    async def slow_stop() -> None:
        await release.wait()
        raise ChargeNotStoppableError("x")

    client.stop_charge.side_effect = slow_stop
    stop = hass.async_create_task(control.async_stop())
    await asyncio.sleep(0)
    control.on_charger_read(CONNECTED, control.start_attempts)
    release.set()
    await stop
    assert control.state == IDLE
    assert "Stopping the charge failed" not in caplog.text
    saved = await _saved(hass, entry, hass_storage)
    assert saved["stop_asked_since"] is None
    assert saved["stop_tries"] == 0  # no tries are stored without a stop


async def test_background_stop_with_a_rejected_session_raises_nothing(
    entry: MockConfigEntry, control: ChargeControl, client: AsyncMock
) -> None:
    """A read's try whose session is rejected starts reauth and raises nothing: nobody awaits a background task."""
    control.on_charger_read(NOT_STOPPABLE, control.start_attempts)
    await control.async_stop()  # stored without a call, so no wait runs
    client.stop_charge.side_effect = AuthError("x")
    with (
        patch.object(entry, "async_start_reauth", MagicMock()) as reauth,
        patch.object(entry, "async_create_background_task", MagicMock()) as queued,
    ):
        control.on_charger_read(CHARGING, control.start_attempts)
        queued.assert_called_once()
        # The read's own try, awaited here: in a background task its exception would be lost.
        await queued.call_args.args[1]
    client.stop_charge.assert_awaited_once()
    reauth.assert_called_once()
    assert control.state == STOP_ASKED_ONLY


async def test_try_is_saved_while_its_call_is_in_flight(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    client: AsyncMock,
    hass_storage: dict[str, Any],
) -> None:
    """The try is counted and saved when the call is made: a restart during the call doesn't lose it."""
    control.on_charger_read(NOT_STOPPABLE, control.start_attempts)
    await control.async_stop()
    saved = await _saved(hass, entry, hass_storage)  # no save is left waiting
    assert saved["stop_tries"] == 0
    assert saved["stop_tried_at"] is None
    release = asyncio.Event()

    async def slow_stop() -> None:
        await release.wait()

    client.stop_charge.side_effect = slow_stop
    control.on_charger_read(CHARGING, control.start_attempts)
    try:
        await asyncio.sleep(0)
        client.stop_charge.assert_awaited_once()  # in flight, not answered
        saved = await _saved(hass, entry, hass_storage)
        assert saved["stop_tries"] == 1
        assert saved["stop_tried_at"] is not None
    finally:
        # Also when an assert fails: the fixture's shutdown waits for the call's lock.
        release.set()
        await hass.async_block_till_done(wait_background_tasks=True)


def _stop_issue(hass: HomeAssistant, entry: MockConfigEntry) -> ir.IssueEntry | None:
    return ir.async_get(hass).async_get_issue(DOMAIN, f"stop_failed_{entry.entry_id}")


def _store_a_stop(
    hass_storage: dict[str, Any],
    entry: MockConfigEntry,
    *,
    asked_ago: timedelta,
    tries: int = 0,
    tried_ago: timedelta | None = None,
) -> None:
    """Put a stored stop in place, asked and last tried this long ago."""
    key = STORE_KEY.format(entry.entry_id)
    now = dt_util.utcnow()
    hass_storage[key] = {
        "version": 1,
        "minor_version": 2,
        "key": key,
        "data": {
            "blocked_since": None,
            "block_reason": None,
            "start_pending_since": None,
            "stop_asked_since": (now - asked_ago).isoformat(),
            "stop_tries": tries,
            "stop_tried_at": None
            if tried_ago is None
            else (now - tried_ago).isoformat(),
        },
    }


async def _fail_10_times(
    hass: HomeAssistant,
    control: ChargeControl,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    *,
    last: Exception | None,
) -> None:
    """A turn-off whose first 9 calls fail; the 10th fails with `last`, or is accepted for None."""
    control.on_charger_read(CHARGING, control.start_attempts)
    client.stop_charge.side_effect = ChargeNotStoppableError("x")
    await control.async_stop()
    for number in range(2, STOP_MAX_TRIES + 1):
        assert control.state == STOP_ASKED_ONLY
        if number == STOP_MAX_TRIES:
            client.stop_charge.side_effect = last
        await _fire(hass, freezer, STOP_CONFIRM_TIMEOUT)
        control.on_charger_read(CHARGING, control.start_attempts)
        await hass.async_block_till_done(wait_background_tasks=True)
    assert client.stop_charge.await_count == STOP_MAX_TRIES


async def test_gives_up_after_the_10th_failed_call(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    on_change: MagicMock,
    hass_storage: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The 10th failed call gives up: an error, the persistent issue, and the switch shows the charge again."""
    await _fail_10_times(
        hass, control, client, freezer, last=NortecGoConnectionError("x")
    )
    assert control.state == IDLE
    assert is_charge_on(CHARGING, control.state)
    assert any(
        record.levelno == logging.ERROR
        and "Giving up on the stop asked for: no stop seen after 10 tries"
        in record.getMessage()
        for record in caplog.records
    )
    issue = _stop_issue(hass, entry)
    assert issue is not None
    assert issue.translation_key == "stop_failed"
    assert issue.is_persistent
    assert issue.is_fixable
    assert issue.severity is ir.IssueSeverity.ERROR
    assert issue.translation_placeholders == {"name": entry.title}
    on_change.assert_called()
    saved = await _saved(hass, entry, hass_storage)
    assert saved["stop_asked_since"] is None
    assert saved["stop_tries"] == 0
    assert saved["stop_tried_at"] is not None  # the wait between calls runs on
    client.start_charge.assert_not_awaited()


async def test_failed_10th_call_gives_up_before_it_asks_for_its_read(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The read asked for after the 10th failed call comes after the give-up: one that shows the charge off removes the notice."""
    made: list[ChargeControl] = []

    async def read_now() -> None:
        # The read after each failed call: the charge is on, until the 10th call has been made.
        made_all = client.stop_charge.await_count >= STOP_MAX_TRIES
        made[0].on_charger_read(
            CONNECTED if made_all else CHARGING, made[0].start_attempts
        )

    control = ChargeControl(
        hass, entry, client, on_change=MagicMock(), request_refresh=read_now
    )
    made.append(control)
    await control.async_load()
    await _fail_10_times(
        hass, control, client, freezer, last=NortecGoConnectionError("x")
    )
    await hass.async_block_till_done()
    assert "Giving up on the stop asked for" in caplog.text
    assert control.state == IDLE
    assert _stop_issue(hass, entry) is None  # the read saw the charge off
    await control.async_shutdown()


@pytest.mark.parametrize("last", [None, NoActiveChargeError("x")])
async def test_gives_up_when_the_wait_after_the_10th_try_has_passed(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    on_change: MagicMock,
    last: Exception | None,
) -> None:
    """A 10th try that was accepted, or answered "no active charge", gives up 2 minutes later if the charge is still on."""
    await _fail_10_times(hass, control, client, freezer, last=last)
    assert control.state.stop_asked
    assert _stop_issue(hass, entry) is None
    on_change.reset_mock()
    await _fire(hass, freezer, STOP_CONFIRM_TIMEOUT)
    assert control.state == IDLE
    assert _stop_issue(hass, entry) is not None
    # After "no active charge" no pending stop ends here: only the give-up tells the coordinator.
    on_change.assert_called()


async def test_10th_try_that_works_gives_up_nothing(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """An accepted 10th try followed by a read that shows the charge off is a done stop."""
    await _fail_10_times(hass, control, client, freezer, last=None)
    control.on_charger_read(CONNECTED, control.start_attempts)
    await _fire(hass, freezer, STOP_CONFIRM_TIMEOUT)
    assert control.state == IDLE
    assert _stop_issue(hass, entry) is None


async def test_gives_up_after_30_minutes_without_a_call(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    on_change: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The 30 minutes hold with no read and no call: the charge never became stoppable."""
    control.on_charger_read(NOT_STOPPABLE, control.start_attempts)
    await control.async_stop()
    assert _timers(hass, f"{DOMAIN} stop limit") == 1
    await _fire(hass, freezer, STOP_ASKED_MAX_AGE - timedelta(seconds=1))
    assert control.state == STOP_ASKED_ONLY
    on_change.reset_mock()
    await _fire(hass, freezer, timedelta(seconds=1))
    assert control.state == IDLE
    assert (
        "Giving up on the stop asked for: it was asked for more than 0:30:00 ago"
        in caplog.text
    )
    assert _stop_issue(hass, entry) is not None
    on_change.assert_called()  # the switch shows the charger's state again
    client.stop_charge.assert_not_awaited()


async def test_limit_timer_does_nothing_on_a_closed_control(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    freezer: FrozenDateTimeFactory,
    on_change: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A limit timer whose work waits for the lock while the entry closes gives up nothing."""
    control.on_charger_read(NOT_STOPPABLE, control.start_attempts)
    await control.async_stop()  # stored without a call
    async with control._lock:  # noqa: SLF001
        freezer.tick(STOP_ASKED_MAX_AGE)
        async_fire_time_changed(hass)
        await asyncio.sleep(0)
        control._async_close()  # noqa: SLF001
        on_change.reset_mock()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert control.state == STOP_ASKED_ONLY
    assert _stop_issue(hass, entry) is None
    assert "Giving up" not in caplog.text
    on_change.assert_not_called()


async def test_done_stop_cancels_the_limit_timer(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A stop that is done leaves no 30-minute timer behind."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    control.on_charger_read(CONNECTED, control.start_attempts)
    assert _timers(hass, f"{DOMAIN} stop limit") == 0
    await _fire(hass, freezer, STOP_ASKED_MAX_AGE)
    assert _stop_issue(hass, entry) is None


async def test_limit_timer_of_an_older_stop_does_nothing(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A limit timer whose work waits for the lock while a read ends its stop gives up nothing."""
    control.on_charger_read(NOT_STOPPABLE, control.start_attempts)
    await control.async_stop()
    async with control._lock:  # noqa: SLF001
        freezer.tick(STOP_ASKED_MAX_AGE)
        async_fire_time_changed(hass)
        await asyncio.sleep(0)
        control.on_charger_read(CONNECTED, control.start_attempts)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert control.state == IDLE
    assert _stop_issue(hass, entry) is None


@pytest.mark.parametrize("failed_setup", [False, True])
async def test_closing_cancels_the_stop_timers(
    hass: HomeAssistant, control: ChargeControl, client: AsyncMock, failed_setup: bool
) -> None:
    """An unload, and a failed setup's close, leave no stop timer behind."""
    control.on_charger_read(CHARGING, control.start_attempts)
    client.stop_charge.side_effect = ChargeNotStoppableError("x")
    await control.async_stop()
    assert _timers(hass, f"{DOMAIN} stop limit") == 1
    assert _timers(hass, f"{DOMAIN} stop wait") == 1
    if failed_setup:
        control._async_close()  # noqa: SLF001
    else:
        await control.async_shutdown()
    assert _timers(hass, f"{DOMAIN} stop limit") == 0
    assert _timers(hass, f"{DOMAIN} stop wait") == 0


async def test_gives_up_after_30_minutes_with_reads(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Reads that keep showing a charge that can't be stopped change nothing: no call, and the 30 minutes hold."""
    control.on_charger_read(NOT_STOPPABLE, control.start_attempts)
    await control.async_stop()
    for _ in range(5):
        await _fire(hass, freezer, timedelta(minutes=5))
        control.on_charger_read(NOT_STOPPABLE, control.start_attempts)
        assert control.state == STOP_ASKED_ONLY
    await _fire(hass, freezer, timedelta(minutes=5))
    assert control.state == IDLE
    assert _stop_issue(hass, entry) is not None
    client.stop_charge.assert_not_awaited()


async def test_failed_10th_call_after_a_read_ended_the_stop_gives_up_nothing(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A read shows the charge off while the 10th call is in flight: its failure raises no notice."""
    control.on_charger_read(CHARGING, control.start_attempts)
    client.stop_charge.side_effect = ChargeNotStoppableError("x")
    await control.async_stop()
    for _ in range(STOP_MAX_TRIES - 2):
        await _fire(hass, freezer, STOP_CONFIRM_TIMEOUT)
        control.on_charger_read(CHARGING, control.start_attempts)
        await hass.async_block_till_done(wait_background_tasks=True)
    assert client.stop_charge.await_count == STOP_MAX_TRIES - 1
    release = asyncio.Event()

    async def slow_failing_stop() -> None:
        await release.wait()
        raise NortecGoConnectionError("x")

    client.stop_charge.side_effect = slow_failing_stop
    await _fire(hass, freezer, STOP_CONFIRM_TIMEOUT)
    control.on_charger_read(CHARGING, control.start_attempts)  # the 10th try, in flight
    control.on_charger_read(CONNECTED, control.start_attempts)  # the charge is off
    assert control.state == IDLE
    release.set()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert client.stop_charge.await_count == STOP_MAX_TRIES
    assert control.state == IDLE
    assert _stop_issue(hass, entry) is None
    assert "Giving up" not in caplog.text


async def test_load_with_time_left(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    hass_storage: dict[str, Any],
) -> None:
    """A stop loaded 20 minutes after it was asked has 10 minutes left."""
    _store_a_stop(hass_storage, entry, asked_ago=timedelta(minutes=20))
    control = ChargeControl(
        hass, entry, client, on_change=MagicMock(), request_refresh=AsyncMock()
    )
    await control.async_load()
    assert control.state == STOP_ASKED_ONLY
    await _fire(hass, freezer, timedelta(minutes=10) - timedelta(seconds=1))
    assert control.state == STOP_ASKED_ONLY
    await _fire(hass, freezer, timedelta(seconds=1))
    assert control.state == IDLE
    assert _stop_issue(hass, entry) is not None
    await control.async_shutdown()


async def test_load_past_the_limit_gives_up_at_once(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    client: AsyncMock,
    hass_storage: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A stop from before a long outage is never sent: the owner is told instead."""
    _store_a_stop(hass_storage, entry, asked_ago=timedelta(minutes=31))
    control = ChargeControl(
        hass, entry, client, on_change=MagicMock(), request_refresh=AsyncMock()
    )
    await control.async_load()
    assert control.state == IDLE
    assert _stop_issue(hass, entry) is not None
    assert "it was asked for more than 0:30:00 ago" in caplog.text
    control.on_charger_read(CHARGING, control.start_attempts)
    await hass.async_block_till_done(wait_background_tasks=True)
    client.stop_charge.assert_not_awaited()
    assert _stop_issue(hass, entry) is not None  # the charge is on: the notice stays
    saved = await _saved(hass, entry, hass_storage)
    assert saved["stop_asked_since"] is None
    await control.async_shutdown()


async def test_load_with_a_time_in_the_future_gets_30_minutes(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    hass_storage: dict[str, Any],
) -> None:
    """A stored time in the future (a clock change) gives 30 minutes, not more."""
    _store_a_stop(hass_storage, entry, asked_ago=timedelta(hours=-3))
    control = ChargeControl(
        hass, entry, client, on_change=MagicMock(), request_refresh=AsyncMock()
    )
    await control.async_load()
    await _fire(hass, freezer, STOP_ASKED_MAX_AGE - timedelta(seconds=1))
    assert control.state == STOP_ASKED_ONLY
    await _fire(hass, freezer, timedelta(seconds=1))
    assert control.state == IDLE
    await control.async_shutdown()


@pytest.mark.parametrize(
    ("tried_ago", "left"),
    [
        (timedelta(minutes=3), timedelta(0)),
        (timedelta(seconds=30), timedelta(seconds=90)),
    ],
)
async def test_load_with_10_tries_made(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    hass_storage: dict[str, Any],
    tried_ago: timedelta,
    left: timedelta,
) -> None:
    """A stop loaded with its 10 tries used gives up when what is left of the wait has passed."""
    _store_a_stop(
        hass_storage,
        entry,
        asked_ago=timedelta(minutes=25),
        tries=STOP_MAX_TRIES,
        tried_ago=tried_ago,
    )
    control = ChargeControl(
        hass, entry, client, on_change=MagicMock(), request_refresh=AsyncMock()
    )
    await control.async_load()
    if left:
        assert control.state == STOP_ASKED_ONLY
        assert _stop_issue(hass, entry) is None
        control.on_charger_read(CHARGING, control.start_attempts)
        await _fire(hass, freezer, left)
    assert control.state == IDLE
    assert _stop_issue(hass, entry) is not None
    client.stop_charge.assert_not_awaited()
    await control.async_shutdown()


async def test_turn_off_after_giving_up_keeps_the_issue_and_waits(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A new turn-off is a new stop, but it doesn't hide the notice or call inside the 2 minutes (D50)."""
    await _fail_10_times(
        hass, control, client, freezer, last=ChargeNotStoppableError("x")
    )
    assert _stop_issue(hass, entry) is not None
    await control.async_stop()
    assert _stop_issue(hass, entry) is not None
    assert control.state == STOP_ASKED_ONLY
    assert client.stop_charge.await_count == STOP_MAX_TRIES
    client.stop_charge.side_effect = None
    await _fire(hass, freezer, STOP_CONFIRM_TIMEOUT)
    control.on_charger_read(CHARGING, control.start_attempts)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert client.stop_charge.await_count == STOP_MAX_TRIES + 1


@pytest.mark.parametrize("stale", [False, True])
async def test_read_that_shows_the_charge_off_deletes_the_issue(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    stale: bool,
) -> None:
    """With no stop stored, a read that shows the charge off removes the notice; a stale read doesn't."""
    await _fail_10_times(
        hass, control, client, freezer, last=ChargeNotStoppableError("x")
    )
    attempts = control.start_attempts - 1 if stale else control.start_attempts
    control.on_charger_read(CONNECTED, attempts)
    assert (_stop_issue(hass, entry) is not None) is stale


async def test_turn_on_deletes_the_issue(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The owner asks for a charge: the notice about the stop goes."""
    await _fail_10_times(
        hass, control, client, freezer, last=ChargeNotStoppableError("x")
    )
    await control.async_start()
    assert _stop_issue(hass, entry) is None
    client.start_charge.assert_not_awaited()  # the charge is open


async def test_turn_on_refused_by_a_pending_stop_keeps_the_issue(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A turn-on refused while a new stop is under way changes nothing: the notice stays."""
    await _fail_10_times(
        hass, control, client, freezer, last=ChargeNotStoppableError("x")
    )
    await control.async_stop()  # a new stop, which waits out the 2 minutes
    client.stop_charge.side_effect = None
    await _fire(hass, freezer, STOP_CONFIRM_TIMEOUT)
    control.on_charger_read(CHARGING, control.start_attempts)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert control.state == STOP_PENDING  # the charger accepted this one
    with pytest.raises(ServiceValidationError) as exc_info:
        await control.async_start()
    assert exc_info.value.translation_key == "stop_pending"
    assert _stop_issue(hass, entry) is not None
    client.start_charge.assert_not_awaited()


async def test_removal_deletes_the_stop_issue(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Removing the entry removes the notice with the store."""
    await _fail_10_times(
        hass, control, client, freezer, last=ChargeNotStoppableError("x")
    )
    await async_remove_charge_control(hass, entry.entry_id)
    assert _stop_issue(hass, entry) is None
