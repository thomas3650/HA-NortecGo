"""Tests for the Nortec Go charge control: start, stop, pending start and the start guard."""

import asyncio
import contextlib
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import issue_registry as ir
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
    is_charge_on,
)
from custom_components.nortec_go.const import (
    DOMAIN,
    START_CONFIRM_TIMEOUT,
    STOP_CONFIRM_TIMEOUT,
)

from .conftest import make_charger

IDLE = ChargeControlState()
PENDING = ChargeControlState(start_pending=True)
STOP_ASKED = ChargeControlState(start_pending=True, stop_asked=True)
STOP_PENDING = ChargeControlState(stop_pending=True)
BLOCKED = ChargeControlState(blocked=True)
CONNECTED = make_charger(is_connected=True)
CHARGING = make_charger(
    is_connected=True,
    charge_state=ChargeState.CHARGING,
    state=ChargerState.BUSY_CHARGING,
)
STORE_KEY = "nortec_go.{}.charge_control"


@pytest.mark.parametrize(
    ("charger", "expected"),
    [
        (CONNECTED, False),
        (make_charger(is_connected=True, state=ChargerState.BUSY), True),
        (make_charger(is_connected=True, state=ChargerState.BUSY_CHARGING), True),
        (make_charger(is_connected=True, charge_state=ChargeState.PAUSED), True),
        (make_charger(is_connected=True, state=ChargerState.BUSY_NON_RELEASED), False),
    ],
)
def test_charge_is_open(charger: Any, expected: bool) -> None:
    """A charge is open on a charge state, BUSY or BUSY_CHARGING."""
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
) -> ChargeControl:
    """A loaded control that has seen one connected, idle read."""
    control = ChargeControl(
        hass, entry, client, on_change=on_change, request_refresh=request_refresh
    )
    await control.async_load()
    control.on_charger_read(CONNECTED, control.start_attempts)
    return control


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


@pytest.mark.parametrize(
    ("error", "key"),
    [
        (CableNotConnectedError("x"), "cable_not_connected"),
        (ChargerNotReleasedError("x"), "charger_not_released"),
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
        make_charger(is_connected=True, state=ChargerState.BUSY_NON_RELEASED),
        make_charger(is_connected=False),
    ],
)
async def test_pending_start_ends_without_block(
    control: ChargeControl, charger: Any
) -> None:
    """A charge seen, BUSY_NON_RELEASED or the cable unplugged ends the pending start."""
    await control.async_start()
    control.on_charger_read(charger, control.start_attempts)
    assert control.state == IDLE


async def test_pending_start_times_out_into_block(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    freezer: FrozenDateTimeFactory,
) -> None:
    """No charge seen within 10 minutes: the start counts as failed with a hold."""
    await control.async_start()
    freezer.tick(START_CONFIRM_TIMEOUT - timedelta(seconds=1))
    control.on_charger_read(CONNECTED, control.start_attempts)
    assert control.state == PENDING
    freezer.tick(timedelta(seconds=1))
    control.on_charger_read(CONNECTED, control.start_attempts)
    assert control.state == BLOCKED
    assert _issue(hass, entry) is not None


async def test_timeout_on_unplugged_read_ends_without_block(
    control: ChargeControl, freezer: FrozenDateTimeFactory
) -> None:
    """A read past the timeout that sees the cable unplugged ends the pending start, no block."""
    await control.async_start()
    freezer.tick(START_CONFIRM_TIMEOUT)
    control.on_charger_read(make_charger(is_connected=False), control.start_attempts)
    assert control.state == IDLE


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
    [make_charger(is_connected=False), CHARGING],
)
async def test_block_cleared_by_a_fresh_read(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    client: AsyncMock,
    charger: Any,
) -> None:
    """The cable unplugged or a charge open clears the block and the issue."""
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


async def test_stop_during_pending_start(
    hass: HomeAssistant, control: ChargeControl, client: AsyncMock
) -> None:
    """Stop asked, no API call; the charge is stopped once when a read sees it."""
    await control.async_start()
    await control.async_stop()
    client.stop_charge.assert_not_awaited()
    assert control.state == STOP_ASKED
    control.on_charger_read(CHARGING, control.start_attempts)
    await hass.async_block_till_done(wait_background_tasks=True)
    client.stop_charge.assert_awaited_once()
    assert control.state == STOP_PENDING


async def test_turn_on_after_turn_off_clears_stop_asked(
    control: ChargeControl, client: AsyncMock
) -> None:
    """turn_on during a pending start with a stop asked clears it, no API call."""
    await control.async_start()
    await control.async_stop()
    await control.async_start()
    assert control.state == PENDING
    client.start_charge.assert_awaited_once()


async def test_stop_asked_ends_with_the_timeout(
    control: ChargeControl, freezer: FrozenDateTimeFactory
) -> None:
    """The stop request ends with the pending start's timeout, which blocks."""
    await control.async_start()
    await control.async_stop()
    freezer.tick(START_CONFIRM_TIMEOUT)
    control.on_charger_read(CONNECTED, control.start_attempts)
    assert control.state == BLOCKED


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


async def test_stop_not_stoppable_error(
    control: ChargeControl, client: AsyncMock
) -> None:
    """ChargeNotStoppableError: charge_not_stoppable, raised from None."""
    control.on_charger_read(CHARGING, control.start_attempts)
    client.stop_charge.side_effect = ChargeNotStoppableError("x")
    with pytest.raises(HomeAssistantError) as exc_info:
        await control.async_stop()
    assert exc_info.value.translation_key == "charge_not_stoppable"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__
    client.stop_charge.assert_awaited_once()


async def test_stop_auth_error_starts_reauth(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    client: AsyncMock,
) -> None:
    """AuthError starts reauth and raises auth_failed, from None."""
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


async def test_stop_connection_error_asks_for_a_read(
    hass: HomeAssistant,
    control: ChargeControl,
    client: AsyncMock,
    request_refresh: AsyncMock,
) -> None:
    """A connection error: stop_failed, raised from None, but a read is asked for."""
    control.on_charger_read(CHARGING, control.start_attempts)
    client.stop_charge.side_effect = NortecGoConnectionError("x")
    with pytest.raises(HomeAssistantError) as exc_info:
        await control.async_stop()
    assert exc_info.value.translation_key == "stop_failed"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__
    client.stop_charge.assert_awaited_once()
    await hass.async_block_till_done()
    request_refresh.assert_awaited()


async def test_stop_sets_pending_stop(
    control: ChargeControl, client: AsyncMock, on_change: MagicMock
) -> None:
    """A successful stop is pending: the switch shows off until the charger follows."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    client.stop_charge.assert_awaited_once()
    assert control.state == STOP_PENDING
    on_change.assert_called()


@pytest.mark.parametrize(
    "error",
    [
        NoActiveChargeError("x"),
        ChargeNotStoppableError("x"),
        NortecGoConnectionError("x"),
    ],
)
async def test_stop_without_success_sets_no_pending_stop(
    control: ChargeControl, client: AsyncMock, error: Exception
) -> None:
    """No charge to stop, or a failed stop: nothing to wait for."""
    control.on_charger_read(CHARGING, control.start_attempts)
    client.stop_charge.side_effect = error
    with contextlib.suppress(HomeAssistantError):
        await control.async_stop()
    assert control.state == IDLE


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


@pytest.mark.parametrize("charge_state", [ChargeState.CHARGING, ChargeState.PAUSED])
async def test_pending_stop_stays_while_the_charge_is_on(
    control: ChargeControl, charge_state: ChargeState
) -> None:
    """A read that still shows the charge on (the charger lags) keeps the pending stop."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    control.on_charger_read(
        make_charger(is_connected=True, charge_state=charge_state),
        control.start_attempts,
    )
    assert control.state == STOP_PENDING


async def test_pending_stop_stays_on_a_stale_read(control: ChargeControl) -> None:
    """A stale read (begun before the latest start attempt) still showing CHARGING keeps it."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    control.on_charger_read(CHARGING, control.start_attempts - 1)
    assert control.state == STOP_PENDING


async def test_pending_stop_times_out_on_a_read(
    control: ChargeControl,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """After 2 minutes a read ends the pending stop, with a warning."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    freezer.tick(STOP_CONFIRM_TIMEOUT - timedelta(seconds=1))
    control.on_charger_read(CHARGING, control.start_attempts)
    assert control.state == STOP_PENDING
    freezer.tick(timedelta(seconds=1))
    control.on_charger_read(CHARGING, control.start_attempts)
    assert control.state == IDLE
    assert "No stop seen within" in caplog.text


async def test_stop_after_the_timeout_without_a_read(
    control: ChargeControl,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """With no read for 2 minutes, turn_off counts the pending stop as ended and stops again."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    freezer.tick(STOP_CONFIRM_TIMEOUT)
    await control.async_stop()
    assert client.stop_charge.await_count == 2
    assert "No stop seen within" in caplog.text


async def test_start_after_the_timeout_takes_the_normal_checks(
    control: ChargeControl, client: AsyncMock, freezer: FrozenDateTimeFactory
) -> None:
    """With no read for 2 minutes, turn_on isn't refused; the open charge makes it a no-op."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    freezer.tick(STOP_CONFIRM_TIMEOUT)
    await control.async_start()
    client.start_charge.assert_not_awaited()
    assert control.state == IDLE


async def test_background_stop_shows_off_at_once(
    hass: HomeAssistant, control: ChargeControl, client: AsyncMock
) -> None:
    """While the background stop is in flight the switch is off and Stopping.

    The background task starts eagerly, so stop_charge waits on an event to keep it in flight.
    """
    release = asyncio.Event()

    async def slow_stop() -> None:
        await release.wait()

    client.stop_charge.side_effect = slow_stop
    await control.async_start()
    await control.async_stop()
    control.on_charger_read(CHARGING, control.start_attempts)
    assert control.state == STOP_PENDING
    assert not is_charge_on(CHARGING, control.state)
    assert charge_status(CHARGING, control.state) == "stopping"
    release.set()
    await hass.async_block_till_done(wait_background_tasks=True)
    client.stop_charge.assert_awaited_once()
    assert control.state == STOP_PENDING


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


@pytest.mark.parametrize(
    "error", [NoActiveChargeError("x"), ChargeNotStoppableError("x")]
)
async def test_background_stop_without_success_ends_pending_stop(
    hass: HomeAssistant, control: ChargeControl, client: AsyncMock, error: Exception
) -> None:
    """The background stop finds no charge or fails: the pending stop it queued ends."""
    release = asyncio.Event()

    async def slow_stop() -> None:
        await release.wait()
        raise error

    client.stop_charge.side_effect = slow_stop
    await control.async_start()
    await control.async_stop()
    control.on_charger_read(CHARGING, control.start_attempts)
    assert control.state == STOP_PENDING
    release.set()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert control.state == IDLE


async def test_pending_stop_is_not_stored(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    hass_storage: dict[str, Any],
) -> None:
    """The stored shape keeps its three keys; the pending stop never reaches it (Review Focus 5)."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    async_fire_time_changed(hass)  # any delayed save's timer
    await hass.async_block_till_done()
    assert STORE_KEY.format(entry.entry_id) not in hass_storage
    await control.async_shutdown()
    saved = hass_storage[STORE_KEY.format(entry.entry_id)]["data"]
    assert saved == {
        "blocked_since": None,
        "start_pending_since": None,
        "stop_asked": False,
    }
    again = ChargeControl(
        hass, entry, AsyncMock(), on_change=MagicMock(), request_refresh=AsyncMock()
    )
    await again.async_load()
    assert again.state == IDLE


async def test_clear_block(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    client: AsyncMock,
) -> None:
    """clear_block (the fix flow) clears the block and deletes the issue."""
    client.start_charge.side_effect = ChargeStartError(ChargeStartStep.CONFIRM, True)
    with pytest.raises(HomeAssistantError):
        await control.async_start()
    control.clear_block()
    assert control.state == IDLE
    assert _issue(hass, entry) is None


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


async def test_start_pending_property(control: ChargeControl) -> None:
    """start_pending follows the pending start."""
    assert not control.start_pending
    await control.async_start()
    assert control.start_pending


async def test_stop_with_a_pending_start_and_a_charge_seen(
    control: ChargeControl, client: AsyncMock
) -> None:
    """A pending start whose charge the last read saw: stop_charge once, pending ends."""
    attempts_before = control.start_attempts
    await control.async_start()
    control.on_charger_read(CHARGING, attempts_before)  # stale: pending stays
    assert control.state == PENDING
    await control.async_stop()
    client.stop_charge.assert_awaited_once()
    assert control.state == STOP_PENDING


async def test_background_stop_error_is_logged(
    hass: HomeAssistant,
    control: ChargeControl,
    client: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The stop asked during a pending start fails: logged, not raised."""
    client.stop_charge.side_effect = ChargeNotStoppableError("x")
    await control.async_start()
    await control.async_stop()
    control.on_charger_read(CHARGING, control.start_attempts)
    await hass.async_block_till_done(wait_background_tasks=True)
    client.stop_charge.assert_awaited_once()
    assert "Could not stop the charge asked to stop" in caplog.text
    assert control.state == IDLE


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
