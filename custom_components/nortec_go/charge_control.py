"""The Nortec Go charge control: start and stop, the pending start and stop, and the start guard (D26, D29)."""

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from pynortecgo import (
    AuthError,
    CableNotConnectedError,
    ChargeAlreadyActiveError,
    ChargeNotStoppableError,
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
    VehicleNotFoundError,
)

from .const import (
    CHARGE_CONTROL_STORE_KEY,
    CHARGE_CONTROL_STORE_VERSION,
    DOMAIN,
    START_BLOCKED_ISSUE_ID,
    START_CONFIRM_TIMEOUT,
    STOP_CONFIRM_TIMEOUT,
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


def charge_is_open(charger: Charger) -> bool:
    """A charge is open: the same test pynortecgo uses for ChargeAlreadyActiveError."""
    return charger.charge_state is not None or charger.state in (
        ChargerState.BUSY,
        ChargerState.BUSY_CHARGING,
    )


def _charge_happened(charger: Charger) -> bool:
    """A charge is open, or opened and closed between reads."""
    return charge_is_open(charger) or charger.state is ChargerState.BUSY_NON_RELEASED


def is_charge_on(charger: Charger, control: ChargeControlState) -> bool:
    """The Charge switch's state (§2.1; the pending stop, D29)."""
    if control.stop_pending or control.stop_asked:
        return False
    return control.start_pending or charger.charge_state in _CHARGE_ON


def charge_status(charger: Charger, control: ChargeControlState) -> str | None:
    """The Charge status sensor's value (§2.2); None is Home Assistant's unknown."""
    if control.blocked:
        return "start_blocked"
    if control.stop_pending:
        return "stopping"
    if control.start_pending and not charge_is_open(charger):
        return "stopping" if control.stop_asked else "starting"
    if (
        charger.state is ChargerState.UNKNOWN
        or charger.charge_state is ChargeState.UNKNOWN
    ):
        return None
    if charger.charge_state in _STATUS_FROM_CHARGE:
        return charger.charge_state.value
    if charger.state is ChargerState.BUSY_NON_RELEASED:
        return "not_released"
    if not charger.is_connected:
        return "unplugged"
    return "idle"


def _parse_time(value: object) -> datetime | None:
    """A stored ISO time, or None; raises TypeError or ValueError on a wrong shape."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("not a string")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("no time zone")
    return parsed


def _parse_bool(value: object) -> bool:
    """A stored bool; raises TypeError on a wrong shape."""
    if not isinstance(value, bool):
        raise TypeError("not a bool")
    return value


def _store(hass: HomeAssistant, entry_id: str) -> Store[dict[str, Any]]:
    return Store(
        hass,
        CHARGE_CONTROL_STORE_VERSION,
        CHARGE_CONTROL_STORE_KEY.format(entry_id=entry_id),
    )


async def async_remove_charge_control(hass: HomeAssistant, entry_id: str) -> None:
    """Delete an entry's stored charge control and its repair issue."""
    await _store(hass, entry_id).async_remove()
    ir.async_delete_issue(
        hass, DOMAIN, START_BLOCKED_ISSUE_ID.format(entry_id=entry_id)
    )


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
        self._store = _store(hass, entry.entry_id)
        self._lock = asyncio.Lock()
        self._blocked_since: datetime | None = None
        self._pending_since: datetime | None = None
        self._stop_asked = False
        self._stop_pending_since: datetime | None = None
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
            stop_asked=self._stop_asked,
            stop_pending=self._stop_pending_since is not None,
        )

    @property
    def start_pending(self) -> bool:
        """A start is pending (the coordinator reads every 5 minutes then)."""
        return self._pending_since is not None

    async def async_load(self) -> None:
        """Load the stored state; a wrong shape blocks starts to be safe (§3.5)."""
        data = await self._store.async_load()
        if data is None:
            return
        try:
            blocked_since = _parse_time(data["blocked_since"])
            pending_since = _parse_time(data["start_pending_since"])
            stop_asked = _parse_bool(data["stop_asked"])
        except KeyError, TypeError, ValueError:
            _LOGGER.warning(
                "The saved start guard has an unexpected shape; blocking starts to be safe"
            )
            self._set_block("start_blocked_store")
            self._save()
            return
        self._blocked_since = blocked_since
        self._pending_since = pending_since
        self._stop_asked = stop_asked and pending_since is not None
        if blocked_since is not None:
            self._create_issue("start_blocked")

    async def async_start(self) -> None:
        """Start a charge once, unless one is on, pending or blocked (§3.1)."""
        async with self._lock:
            self._raise_if_closed()
            if self._expire_stop_pending():
                self._on_change()
            if self._stop_pending_since is not None:
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="stop_pending"
                )
            if self._pending_since is not None:
                if self._stop_asked:
                    self._stop_asked = False
                    self._changed()
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
            self._pending_since = dt_util.utcnow()
            self._stop_asked = False
            self._changed()
            self._request_read()

    async def async_stop(self) -> None:
        """Stop the charge, or ask for the stop while a start is pending (§3.3)."""
        async with self._lock:
            self._raise_if_closed()
            if self._expire_stop_pending():
                self._on_change()
            if self._stop_pending_since is not None:
                return
            charger = self._last_charger
            if self._pending_since is not None and (
                charger is None or not charge_is_open(charger)
            ):
                if not self._stop_asked:
                    self._stop_asked = True
                    self._changed()
                self._request_read()
                return
            if charger is not None and charger.charge_state is ChargeState.STOPPING:
                return
            await self._async_send_stop()

    async def _async_send_stop(self) -> None:
        """Call stop_charge() once, under the lock; raises translated errors.

        A successful stop is pending until a read sees the charge no longer on (D29).
        """
        try:
            await self._client.stop_charge()
        except NoActiveChargeError:
            stopped = False
        except ChargeNotStoppableError:
            self._clear_stop_pending()
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="charge_not_stoppable"
            ) from None
        except AuthError:
            self._clear_stop_pending()
            self._entry.async_start_reauth(self._hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="auth_failed"
            ) from None
        except NortecGoError as err:
            self._clear_stop_pending()
            _LOGGER.warning(
                "Stopping the charge failed: %s: %s", type(err).__name__, err
            )
            self._request_read()
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="stop_failed"
            ) from None
        else:
            stopped = True
        if self._pending_since is not None:
            self._pending_since = None
            self._stop_asked = False
            self._save()
        self._stop_pending_since = dt_util.utcnow() if stopped else None
        self._on_change()
        self._request_read()

    async def _async_background_stop(self) -> None:
        """The stop asked for during a pending start, now that the charge is open.

        It owns the pending stop set when it was queued, so it doesn't make the no-op check.
        """
        async with self._lock:
            if self._closed:
                _LOGGER.warning("Not stopping the charge: the integration is unloading")
                return
            try:
                await self._async_send_stop()
            except HomeAssistantError as err:
                _LOGGER.warning("Could not stop the charge asked to stop: %s", err)

    @callback
    def on_charger_read(self, charger: Charger, start_attempts: int) -> None:
        """Update the pending start and the block from a charger read (§3.4)."""
        self._last_charger = charger
        if self._closed:
            return  # unloaded: the reloaded control owns the store now
        # The pending stop (D29), before the stale-read check: that check is about start
        # attempts, and a read begun before the stop saw the charge on, so it can't end it early.
        if (
            self._stop_pending_since is not None
            and charger.charge_state not in _CHARGE_ON
        ):
            self._stop_pending_since = None
        else:
            self._expire_stop_pending()
        if start_attempts != self.start_attempts:
            return  # a stale read: it began before the latest start attempt
        changed = False
        if self._pending_since is not None:
            if self._stop_asked and charge_is_open(charger):
                self._pending_since = None
                self._stop_asked = False
                self._stop_pending_since = dt_util.utcnow()
                changed = True
                self._entry.async_create_background_task(
                    self._hass, self._async_background_stop(), f"{DOMAIN} stop"
                )
            elif _charge_happened(charger) or not charger.is_connected:
                self._pending_since = None
                self._stop_asked = False
                changed = True
            elif dt_util.utcnow() - self._pending_since >= START_CONFIRM_TIMEOUT:
                _LOGGER.warning(
                    "No charge seen within %s of the start; blocking starts",
                    START_CONFIRM_TIMEOUT,
                )
                self._pending_since = None
                self._stop_asked = False
                self._set_block("start_blocked")
                changed = True
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
            await self._store.async_save(self._data_to_save())

    def _raise_if_closed(self) -> None:
        if self._closed:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="unloading"
            )

    def _expire_stop_pending(self) -> bool:
        """Clear a pending stop older than STOP_CONFIRM_TIMEOUT; True when it was cleared."""
        if (
            self._stop_pending_since is None
            or dt_util.utcnow() - self._stop_pending_since < STOP_CONFIRM_TIMEOUT
        ):
            return False
        _LOGGER.warning(
            "No stop seen within %s; showing the charger's state again",
            STOP_CONFIRM_TIMEOUT,
        )
        self._stop_pending_since = None
        return True

    def _clear_stop_pending(self) -> None:
        """End a pending stop outside a read; it isn't stored, so only tell the coordinator."""
        if self._stop_pending_since is not None:
            self._stop_pending_since = None
            self._on_change()

    def _set_block(self, issue_key: str) -> None:
        self._blocked_since = dt_util.utcnow()
        self._remembered = None
        self._create_issue(issue_key)

    def _clear_block(self) -> None:
        self._blocked_since = None
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
        self._store.async_delay_save(self._data_to_save, 0)

    def _data_to_save(self) -> dict[str, Any]:
        return {
            "blocked_since": None
            if self._blocked_since is None
            else self._blocked_since.isoformat(),
            "start_pending_since": None
            if self._pending_since is None
            else self._pending_since.isoformat(),
            "stop_asked": self._stop_asked,
        }

    def _request_read(self) -> None:
        self._entry.async_create_task(
            self._hass, self._request_refresh(), f"{DOMAIN} read after start or stop"
        )
