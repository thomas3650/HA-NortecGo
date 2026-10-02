"""The Nortec Go charge control: start and stop, the pending start, the stored stop, and the start guard (D26, D29, D31, D50)."""

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HassJob, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util
from pynortecgo import (
    AuthError,
    CableNotConnectedError,
    ChargeAlreadyActiveError,
    Charger,
    ChargerNotReleasedError,
    ChargerState,
    ChargeStartError,
    ChargeState,
    MultiplePaymentSourcesError,
    MultipleVehiclesError,
    NoActiveChargeError,
    NortecGoClient,
    NortecGoError,
    PaymentSourceNotFoundError,
    UnknownChargerStateError,
    VehicleNotFoundError,
)

from .charge_control_store import (
    ChargeControlStore,
    StoredControl,
    UnreadableStoreError,
)
from .const import (
    DOMAIN,
    START_BLOCKED_ISSUE_ID,
    START_CONFIRM_TIMEOUT,
    START_LOAD_GRACE,
    STOP_ASKED_MAX_AGE,
    STOP_CONFIRM_TIMEOUT,
    STOP_FAILED_ISSUE_ID,
    STOP_MAX_TRIES,
)
from .entry import NortecGoConfigEntry

_LOGGER = logging.getLogger(__name__)

_CHARGE_ON = (ChargeState.STARTING, ChargeState.CHARGING, ChargeState.PAUSED)
_STATUS_FROM_CHARGE = (
    ChargeState.STARTING,
    ChargeState.CHARGING,
    ChargeState.PAUSED,
    ChargeState.STOPPING,
)
CHARGE_STATUS_OPTIONS = [
    "start_blocked",
    "starting",
    "charging",
    "paused",
    "stopping",
    "not_released",
    "unplugged",
    "idle",
]

# Pre-check errors: no payment request was sent, so no hold (§3.1).
_PRE_CHECK_ERRORS: dict[type[NortecGoError], str] = {
    CableNotConnectedError: "cable_not_connected",
    ChargerNotReleasedError: "charger_not_released",
    UnknownChargerStateError: "charger_state_unknown",
    PaymentSourceNotFoundError: "no_payment_source",
    MultiplePaymentSourcesError: "multiple_payment_sources",
    VehicleNotFoundError: "no_vehicle",
    MultipleVehiclesError: "multiple_vehicles",
}


@dataclass(frozen=True)
class ChargeControlState:
    """A snapshot of the charge control, carried in the coordinator's data."""

    blocked: bool = False
    start_pending: bool = False
    stop_asked: bool = False
    stop_pending: bool = False


def charge_state(charger: Charger) -> ChargeState | None:
    """The open charge's state, or None when no charge is open."""
    active = charger.active_charge
    return None if active is None else active.state


def charge_is_open(charger: Charger) -> bool:
    """A charge is open: the same test pynortecgo uses for ChargeAlreadyActiveError."""
    return charge_state(charger) is not None or charger.state in (
        ChargerState.BUSY,
        ChargerState.BUSY_CHARGING,
        ChargerState.BUSY_NON_CHARGING,
    )


def _charge_happened(charger: Charger) -> bool:
    """A charge is open, or opened and closed between reads."""
    return charge_is_open(charger) or charger.state is ChargerState.BUSY_NON_RELEASED


_CHARGE_OVER = (ChargeState.STOPPING, ChargeState.COMPLETED)

# Why the control gave up on a stop, for the log.
_NO_STOP_SEEN = f"no stop seen after {STOP_MAX_TRIES} tries"
_TOO_OLD = f"it was asked for more than {STOP_ASKED_MAX_AGE} ago"


def is_stoppable(charger: Charger) -> bool:
    """A charge the read says can be stopped, and that isn't ending already (D50).

    An open charger without a charge object, as seen right after a start, isn't.
    """
    active = charger.active_charge
    return active is not None and active.can_stop and active.state not in _CHARGE_OVER


def is_charge_off(charger: Charger) -> bool:
    """The charge is ending or over, or none is open on a charger whose state is known (D50)."""
    if charge_state(charger) in _CHARGE_OVER:
        return True
    return not charge_is_open(charger) and charger.state is not ChargerState.UNKNOWN


def is_charge_on(charger: Charger, control: ChargeControlState) -> bool:
    """The Charge switch's state (§2.1; the pending stop, D29)."""
    if control.stop_pending or control.stop_asked:
        return False
    return control.start_pending or charge_state(charger) in _CHARGE_ON


def charge_status(charger: Charger, control: ChargeControlState) -> str | None:
    """The Charge status sensor's value (§2.2); None is Home Assistant's unknown."""
    if control.blocked:
        return "start_blocked"
    if control.stop_pending:
        return "stopping"
    if control.start_pending and not charge_is_open(charger):
        return "stopping" if control.stop_asked else "starting"
    of_charge = charge_state(charger)
    if charger.state is ChargerState.UNKNOWN or of_charge is ChargeState.UNKNOWN:
        return None
    if of_charge in _STATUS_FROM_CHARGE:
        return of_charge.value
    if charger.state is ChargerState.BUSY_NON_RELEASED:
        return "not_released"
    if not charger.is_connected:
        return "unplugged"
    return "idle"


async def async_remove_charge_control(hass: HomeAssistant, entry_id: str) -> None:
    """Delete an entry's stored charge control and its repair issues."""
    await ChargeControlStore(hass, entry_id).async_remove()
    ir.async_delete_issue(
        hass, DOMAIN, START_BLOCKED_ISSUE_ID.format(entry_id=entry_id)
    )
    ir.async_delete_issue(hass, DOMAIN, STOP_FAILED_ISSUE_ID.format(entry_id=entry_id))


class ChargeControl:
    """Starts and stops charges for one entry, and guards against repeated starts (§3)."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: NortecGoConfigEntry,
        client: NortecGoClient,
        *,
        on_change: Callable[[], None],
        request_refresh: Callable[[], Coroutine[Any, Any, None]],
    ) -> None:
        """Set up the control; call async_load before the first read."""
        self._hass = hass
        self._entry = entry
        self._client = client
        self._on_change = on_change
        self._request_refresh = request_refresh
        self._store = ChargeControlStore(hass, entry.entry_id)
        self._lock = asyncio.Lock()
        self._blocked_since: datetime | None = None
        self._block_reason: str | None = None
        self._pending_since: datetime | None = None
        self._stop_asked_since: datetime | None = None
        # The stop_charge() calls made for the stop asked, and the last call's time (D50).
        self._stop_tries = 0
        self._stop_tried_at: datetime | None = None
        # A try is queued or in flight: no second one (D50).
        self._try_queued = False
        self._stop_pending_since: datetime | None = None
        self._start_timer: CALLBACK_TYPE | None = None
        self._wait_timer: CALLBACK_TYPE | None = None
        self._limit_timer: CALLBACK_TYPE | None = None
        entry.async_on_unload(self._async_close)
        self._remembered: ChargerState | None = None
        self._last_charger: Charger | None = None
        self._closed = False
        self.start_attempts = 0

    @property
    def state(self) -> ChargeControlState:
        """The current snapshot."""
        return ChargeControlState(
            blocked=self._blocked_since is not None,
            start_pending=self._pending_since is not None,
            stop_asked=self._stop_asked_since is not None,
            stop_pending=self._stop_pending_since is not None,
        )

    async def async_load(self) -> None:
        """Load the stored state; a store that can't be read blocks starts to be safe (§3.5)."""
        try:
            stored = await self._store.async_load()
        except UnreadableStoreError:
            _LOGGER.warning(
                "The saved start guard couldn't be read; blocking starts to be safe"
            )
            self._set_block("start_blocked_store")
            self._save()
            return
        if stored is None:
            return
        self._blocked_since = stored.blocked_since
        self._block_reason = stored.block_reason
        self._stop_tries = stored.stop_tries
        self._stop_tried_at = stored.stop_tried_at
        if stored.stop_tried_at is not None:
            left = STOP_CONFIRM_TIMEOUT - (dt_util.utcnow() - stored.stop_tried_at)
            if left > timedelta(0):
                # Never more than the full wait: a stored time in the future is a clock change.
                self._set_wait(min(left, STOP_CONFIRM_TIMEOUT))
        asked = stored.stop_asked_since
        if asked is not None:
            left = STOP_ASKED_MAX_AGE - (dt_util.utcnow() - asked)
            if left <= timedelta(0):
                # No grace here, unlike the start's: a stop this old can't be trusted to
                # belong to the charge that is open now (D50).
                self._give_up(_TOO_OLD)
            elif self._stop_tries >= STOP_MAX_TRIES and self._wait_timer is None:
                self._give_up(_NO_STOP_SEEN)
            else:
                self._set_stop_asked(asked, min(left, STOP_ASKED_MAX_AGE))
        pending_since = stored.start_pending_since
        if pending_since is not None:
            left = START_CONFIRM_TIMEOUT - (dt_util.utcnow() - pending_since)
            self._set_start_pending(
                pending_since, min(max(left, START_LOAD_GRACE), START_CONFIRM_TIMEOUT)
            )
        if stored.block_reason is not None:
            self._create_issue(stored.block_reason)

    async def async_start(self) -> None:
        """Start a charge once, unless one is on, pending or blocked (§3.1)."""
        async with self._lock:
            self._raise_if_closed()
            if self._stop_pending_since is not None:
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="stop_pending"
                )
            self._delete_stop_issue()
            if self._stop_asked_since is not None:
                # The owner asks for a charge: the stop is off, whatever the start then does (D50).
                self._clear_stop()
                self._changed()
            if self._pending_since is not None:
                return
            charger = self._last_charger
            if charger is not None and charge_is_open(charger):
                return
            if self._blocked_since is not None:
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="start_blocked"
                )
            if charger is not None and charger.state is ChargerState.UNKNOWN:
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="charger_state_unknown"
                )
            self.start_attempts += 1
            try:
                await self._client.start_charge()
            except asyncio.CancelledError:
                _LOGGER.warning("A charge start was cancelled; blocking starts")
                self._set_block("start_blocked")
                self._changed()
                raise
            except ChargeAlreadyActiveError:
                self._request_read()
                return
            except ChargeStartError as err:
                _LOGGER.warning(
                    "Starting a charge failed: %s: %s", type(err).__name__, err
                )
                if err.hold_may_be_placed:
                    self._set_block("start_blocked")
                    self._changed()
                    self._request_read()
                    raise HomeAssistantError(
                        translation_domain=DOMAIN, translation_key="start_failed_hold"
                    ) from None
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="start_failed"
                ) from None
            except AuthError:
                self._entry.async_start_reauth(self._hass)
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="auth_failed"
                ) from None
            except NortecGoError as err:
                key = _PRE_CHECK_ERRORS.get(type(err))
                if key is not None:
                    raise ServiceValidationError(
                        translation_domain=DOMAIN, translation_key=key
                    ) from None
                _LOGGER.warning(
                    "Starting a charge failed: %s: %s", type(err).__name__, err
                )
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="start_failed"
                ) from None
            except Exception:
                # Not the client's own error, so nothing after the payment request raised it:
                # the client wraps all of that in ChargeStartError. No hold, so no block.
                _LOGGER.exception("Unexpected error while starting a charge")
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="start_failed"
                ) from None
            self._set_start_pending(dt_util.utcnow())
            self._changed()
            self._request_read()

    async def async_stop(self) -> None:
        """Ask for the charge to be off: the stop is stored, and tried now when it may be (D50)."""
        async with self._lock:
            self._raise_if_closed()
            charger = self._last_charger
            if self._stop_pending_since is not None or (
                charger is not None and charge_state(charger) is ChargeState.STOPPING
            ):
                return
            if self._stop_asked_since is None:
                self._set_stop_asked(dt_util.utcnow())
                self._changed()
            # A last read without a charge, or no read, still gets a call: the read may be old.
            # An open charge that isn't stoppable (not yet, or completed) gets none: a read decides.
            waits_for_a_read = (
                charger is not None
                and charge_is_open(charger)
                and not is_stoppable(charger)
            )
            if waits_for_a_read or not self._may_try():
                self._request_read()
                return
            self._try_queued = True
            await self._async_try_stop(from_turn_off=True)

    def _may_try(self) -> bool:
        """Whether a stop_charge() call may be made now (D50)."""
        return (
            self._stop_asked_since is not None
            and not self._closed
            and self._pending_since is None
            and self._stop_pending_since is None
            and not self._try_queued
            and self._wait_timer is None
            and self._stop_tries < STOP_MAX_TRIES
        )

    async def _async_try_stop(self, *, from_turn_off: bool) -> None:
        """One stop_charge() call, under the lock, with the try already marked as queued.

        Only a read ends the stop as done: the call's answer never does (D50). An exception
        that isn't the client's own escapes untranslated, as it does today.
        """
        self._stop_tries += 1
        tries = self._stop_tries
        self._stop_tried_at = dt_util.utcnow()
        self._save()
        failed: str | None = None
        accepted = False
        rejected = False
        try:
            await self._client.stop_charge()
        except NoActiveChargeError:
            # Also the answer for an open charger without a charge yet: the read decides.
            _LOGGER.debug("The charger had no charge to stop")
        except AuthError:
            rejected = True
            failed = "the session was rejected"
        except NortecGoError as err:
            failed = f"{type(err).__name__}: {err}"
        else:
            accepted = True
        finally:
            # Also for a cancelled call: it was made, so the wait runs from here.
            self._try_queued = False
            self._stop_tried_at = dt_util.utcnow()
            self._set_wait()
            self._save()
        # A read isn't under the lock: it may have ended the stop while the call was in flight.
        # Then there is no stop to wait for, to warn about or to give up on.
        still_asked = self._stop_asked_since is not None
        if accepted and still_asked:
            self._stop_pending_since = self._stop_tried_at
        if rejected:
            self._entry.async_start_reauth(self._hass)
        if failed is None:
            self._request_read()
        elif still_asked:
            _LOGGER.warning(
                "Stopping the charge failed (try %d of %d): %s",
                tries,
                STOP_MAX_TRIES,
                failed,
            )
            if tries >= STOP_MAX_TRIES:
                self._give_up(_NO_STOP_SEEN)
        self._on_change()
        if rejected and from_turn_off:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="auth_failed"
            ) from None

    async def _async_background_stop(self) -> None:
        """A try queued by a read; it checks again under the lock (D50)."""
        try:
            async with self._lock:
                if (
                    self._closed
                    or self._stop_asked_since is None
                    or self._pending_since is not None
                    or self._wait_timer is not None
                    or self._stop_tries >= STOP_MAX_TRIES
                ):
                    return  # no call was made, so no wait starts
                await self._async_try_stop(from_turn_off=False)
        finally:
            self._try_queued = False

    @callback
    def on_charger_read(self, charger: Charger, start_attempts: int) -> None:
        """Update the pending start, the stop and the block from a charger read (§3.4, D50)."""
        self._last_charger = charger
        if self._closed:
            return  # unloaded: the reloaded control owns the store now
        if start_attempts != self.start_attempts:
            # A stale read: it began before the latest start attempt, and changes nothing (D26).
            return
        changed = False
        if self._pending_since is not None and (
            _charge_happened(charger) or not charger.is_connected
        ):
            self._end_start_pending()
            changed = True
        if self._pending_since is None and is_charge_off(charger):
            # Evidence the charge is off: the notice about a stop that failed goes too.
            self._delete_stop_issue()
            if self._stop_asked_since is not None:
                # Only a read ends a stop as done (D50).
                self._clear_stop()
                changed = True
        elif (
            self._stop_asked_since is not None
            and is_stoppable(charger)
            and self._may_try()
        ):
            self._try_queued = True
            self._entry.async_create_background_task(
                self._hass, self._async_background_stop(), f"{DOMAIN} stop"
            )
        if self._blocked_since is not None:
            released = (
                self._remembered is ChargerState.BUSY_NON_RELEASED
                and charger.state is ChargerState.AVAILABLE
            )
            if not charger.is_connected or charge_is_open(charger) or released:
                self._clear_block()
                changed = True
            else:
                self._remembered = charger.state
        if changed:
            self._save()

    @callback
    def clear_block(self) -> None:
        """Clear the block from the repair issue's fix flow."""
        if self._blocked_since is None:
            return
        self._clear_block()
        self._changed()

    async def async_shutdown(self) -> None:
        """At unload: let a start or stop in flight finish, refuse new ones, and save.

        A service call already running isn't cancelled by an unload, so without this a start
        finishing on the old control after a reload could set a block the new one never sees.
        """
        async with self._lock:
            self._closed = True
            self._cancel_timers()
            await self._store.async_save(self._stored())

    def _raise_if_closed(self) -> None:
        if self._closed:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="unloading"
            )

    def _set_start_pending(
        self, since: datetime, delay: timedelta = START_CONFIRM_TIMEOUT
    ) -> None:
        """Start pending since `since`; its timer ends it with a block after `delay` (D31)."""
        self._pending_since = since
        self._cancel_start_timer()

        @callback
        def _due(_now: datetime) -> None:
            self._start_timer = None
            self._entry.async_create_background_task(
                self._hass, self._async_start_due(since), f"{DOMAIN} start deadline"
            )

        self._start_timer = async_call_later(
            self._hass,
            delay,
            HassJob(_due, f"{DOMAIN} start deadline", cancel_on_shutdown=True),
        )

    def _end_start_pending(self) -> None:
        self._pending_since = None
        self._cancel_start_timer()

    async def _async_start_due(self, since: datetime) -> None:
        """The start timer's work, under the lock: no charge seen in time blocks starts (D26)."""
        async with self._lock:
            if self._closed or self._pending_since != since:
                return
            _LOGGER.warning(
                "No charge seen within %s of the start; blocking starts",
                START_CONFIRM_TIMEOUT,
            )
            self._end_start_pending()
            self._set_block("start_blocked")
            self._changed()

    def _set_stop_asked(
        self, since: datetime, delay: timedelta = STOP_ASKED_MAX_AGE
    ) -> None:
        """A stop asked for since `since`; its timer gives up after `delay`, read or no read (D31, D50)."""
        self._stop_asked_since = since
        self._cancel_limit_timer()

        @callback
        def _due(_now: datetime) -> None:
            self._limit_timer = None
            self._entry.async_create_background_task(
                self._hass, self._async_limit_due(since), f"{DOMAIN} stop limit"
            )

        self._limit_timer = async_call_later(
            self._hass,
            delay,
            HassJob(_due, f"{DOMAIN} stop limit", cancel_on_shutdown=True),
        )

    def _clear_stop(self) -> None:
        """End the stop asked for; the wait between two calls runs on (D50)."""
        self._stop_asked_since = None
        self._stop_tries = 0
        self._stop_pending_since = None
        self._cancel_limit_timer()

    async def _async_limit_due(self, since: datetime) -> None:
        """The 30 minutes' end, under the lock (D50)."""
        async with self._lock:
            if self._closed or self._stop_asked_since != since:
                return
            self._give_up(_TOO_OLD)

    def _set_wait(self, delay: timedelta = STOP_CONFIRM_TIMEOUT) -> None:
        """No stop call for `delay`; the timer then judges an accepted try (D29, D50)."""
        if self._closed:
            return
        tried_at = self._stop_tried_at
        self._cancel_wait_timer()

        @callback
        def _due(_now: datetime) -> None:
            self._wait_timer = None
            self._entry.async_create_background_task(
                self._hass, self._async_wait_due(tried_at), f"{DOMAIN} stop wait"
            )

        self._wait_timer = async_call_later(
            self._hass,
            delay,
            HassJob(_due, f"{DOMAIN} stop wait", cancel_on_shutdown=True),
        )

    async def _async_wait_due(self, tried_at: datetime | None) -> None:
        """The wait's end, under the lock: an accepted stop that didn't take has failed (D50)."""
        async with self._lock:
            if self._closed or self._stop_tried_at != tried_at:
                return
            if self._stop_pending_since is not None:
                self._stop_pending_since = None
                _LOGGER.warning(
                    "Stopping the charge failed (try %d of %d): %s",
                    self._stop_tries,
                    STOP_MAX_TRIES,
                    f"the charge was still on {STOP_CONFIRM_TIMEOUT} after the charger"
                    " accepted the stop",
                )
                self._on_change()
            if (
                self._stop_asked_since is not None
                and self._stop_tries >= STOP_MAX_TRIES
            ):
                self._give_up(_NO_STOP_SEEN)

    def _give_up(self, why: str) -> None:
        """Stop trying: tell the owner, and show the charger's state again (D50)."""
        _LOGGER.error("Giving up on the stop asked for: %s", why)
        self._clear_stop()
        ir.async_create_issue(
            self._hass,
            DOMAIN,
            STOP_FAILED_ISSUE_ID.format(entry_id=self._entry.entry_id),
            is_fixable=True,
            # The charge may still run after a restart, and nothing else brings the notice back.
            is_persistent=True,
            severity=ir.IssueSeverity.ERROR,
            translation_key="stop_failed",
            translation_placeholders={"name": self._entry.title},
            data={"entry_id": self._entry.entry_id},
        )
        self._changed()

    def _delete_stop_issue(self) -> None:
        ir.async_delete_issue(
            self._hass,
            DOMAIN,
            STOP_FAILED_ISSUE_ID.format(entry_id=self._entry.entry_id),
        )

    def _cancel_start_timer(self) -> None:
        if self._start_timer is not None:
            self._start_timer()
            self._start_timer = None

    def _cancel_wait_timer(self) -> None:
        if self._wait_timer is not None:
            self._wait_timer()
            self._wait_timer = None

    def _cancel_limit_timer(self) -> None:
        if self._limit_timer is not None:
            self._limit_timer()
            self._limit_timer = None

    @callback
    def _cancel_timers(self) -> None:
        self._cancel_start_timer()
        self._cancel_wait_timer()
        self._cancel_limit_timer()

    @callback
    def _async_close(self) -> None:
        """The entry is going: after an unload, or after a setup that failed.

        A setup that fails after async_load never calls async_shutdown, but runs this, and
        only then cancels a stop call in flight. Closing here keeps that call's end from
        arming a timer on a control the next setup has replaced (D50).
        """
        self._closed = True
        self._cancel_timers()

    def _set_block(self, issue_key: str) -> None:
        self._blocked_since = dt_util.utcnow()
        self._block_reason = issue_key
        self._remembered = None
        self._create_issue(issue_key)

    def _clear_block(self) -> None:
        self._blocked_since = None
        self._block_reason = None
        self._remembered = None
        ir.async_delete_issue(
            self._hass,
            DOMAIN,
            START_BLOCKED_ISSUE_ID.format(entry_id=self._entry.entry_id),
        )
        _LOGGER.info("Starts are allowed again")

    def _create_issue(self, translation_key: str) -> None:
        ir.async_create_issue(
            self._hass,
            DOMAIN,
            START_BLOCKED_ISSUE_ID.format(entry_id=self._entry.entry_id),
            is_fixable=True,
            is_persistent=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key=translation_key,
            translation_placeholders={"name": self._entry.title},
            data={"entry_id": self._entry.entry_id},
        )

    def _changed(self) -> None:
        """A change outside a read: save it and tell the coordinator."""
        self._save()
        self._on_change()

    def _save(self) -> None:
        self._store.async_delay_save(self._stored)

    def _stored(self) -> StoredControl:
        return StoredControl(
            blocked_since=self._blocked_since,
            block_reason=self._block_reason,
            start_pending_since=self._pending_since,
            stop_asked_since=self._stop_asked_since,
            stop_tries=self._stop_tries,
            stop_tried_at=self._stop_tried_at,
        )

    def _request_read(self) -> None:
        self._entry.async_create_task(
            self._hass, self._request_refresh(), f"{DOMAIN} read after start or stop"
        )
