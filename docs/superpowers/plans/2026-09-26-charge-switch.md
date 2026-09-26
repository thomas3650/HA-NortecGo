# Charge switch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A guarded *Charge* switch, a *Charge status* sensor and a start-blocked repair issue, so EV Smart
Charging can start and stop charges through Nortec Go (issue #9).

**Architecture:** A new `ChargeControl` (in `charge_control.py`) owns every start and stop call, the pending
start, the start block, its `Store` and the repair issue; it has no entity code and is tested on its own.
The coordinator owns one `ChargeControl`, passes each charger read to it and carries a frozen snapshot of its
state in `NortecGoData.control`. The switch, the status sensor and the repair fix flow are thin layers on it.

**Tech Stack:** Home Assistant 2026.9 custom integration, `pynortecgo==0.2.0`, pytest with
`pytest-homeassistant-custom-component`, `freezegun`.

**Spec:** [`docs/superpowers/specs/2026-09-26-charge-switch-design.md`](../specs/2026-09-26-charge-switch-design.md)

## Global Constraints

- Hard rule 2: no test and no dev run starts or stops a real charge; `pynortecgo` is always mocked.
- Hard rule 6: `start_charge()` is called at most once per `turn_on`, never retried, by us or by HA.
- Hard rule 7: fixtures are `pynortecgo` model objects (`make_charger`, `make_vehicle`), never raw JSON.
- Hard rule 3 and 5: no IDs, tokens or emails in logs, store or issue text; errors raised `from None`.
- Every raised exception is translated: `translation_domain=DOMAIN`, `translation_key=<key>`.
- `START_CONFIRM_TIMEOUT = timedelta(minutes=10)`; pending interval is `INTERVAL_CHARGING` (5 min).
- Store: version 1, key `nortec_go.{entry_id}.charge_control`, data
  `{"blocked_since": str | None, "start_pending_since": str | None, "stop_asked": bool}`; saved with
  `Store.async_delay_save`.
- Repair issue ID `start_blocked_{entry_id}`; translation keys `start_blocked` and `start_blocked_store`;
  placeholder `name` = `entry.title`; `data={"entry_id": entry.entry_id}`.
- Entity keys: switch `charge`; sensor `charge_status` with options `start_blocked`, `starting`,
  `charging`, `paused`, `stopping`, `not_released`, `unplugged`, `idle`.
- Changes outside a read: `coordinator.data = replace(coordinator.data, control=...)` then
  `async_update_listeners()`. Never `async_set_updated_data()`.
- Gates (`CLAUDE.md` → Commands), coverage ≥ 95%, before every commit.
- Subagents write commit messages with the Write tool to a file outside the repo and commit with
  `git commit -F <file>` (the guard refuses heredocs). Every commit message ends with the co-author trailer
  the dispatch gives.

## Review Focus

1. A read in flight while `start_charge()` runs (stale read) must not end the pending start or clear the
   block — pinned in Task 1 (`test_stale_read_changes_nothing`) and Task 2 (`test_read_counter_handoff`).
2. EVSC's repeated `turn_on` right after a successful start must not call `start_charge()` again — Task 1
   (`test_second_start_is_noop`) and Task 3 (`test_turn_on_twice_starts_once`).
3. A block set by a timeout on a read identical to the previous one must still reach the entities — Task 2
   (`test_timeout_on_unchanged_read_updates_entities`).
4. A stop after a failed read must reach `stop_charge()` without making other entities available — Task 2
   (`test_stop_after_failed_read_keeps_others_unavailable`) and Task 3 (`test_switch_available_after_failed_read`).
5. A restart with a stored block must keep blocking and show the issue — Task 2
   (`test_stored_block_survives_restart`).

## Files

| File | Task |
|---|---|
| `custom_components/nortec_go/const.py` | 1 |
| `custom_components/nortec_go/charge_control.py` (new) | 1 |
| `tests/conftest.py` (`make_charger` gains `state`) | 1 |
| `tests/test_charge_control.py` (new) | 1 |
| `custom_components/nortec_go/coordinator.py` | 2 |
| `custom_components/nortec_go/__init__.py` | 2 (setup, removal), 3 (`Platform.SWITCH`) |
| `custom_components/nortec_go/strings.json`, `translations/en.json` | 2 |
| `tests/test_coordinator.py`, `tests/test_init.py` | 2 |
| `custom_components/nortec_go/switch.py` (new), `tests/test_switch.py` (new) | 3 |
| `custom_components/nortec_go/sensor.py`, `tests/test_sensor.py` | 4 |
| `custom_components/nortec_go/repairs.py` (new), `tests/test_repairs.py` (new) | 5 |
| `docs/user/nortec_go.md`, `CHANGELOG.md`, `quality_scale.yaml`, `docs/decisions.md` | 6 |

Waves: 1 → Task 1; 2 → Task 2; 3 → Tasks 3, 4, 5, 6 in parallel (disjoint files). No guarded files.

---

### Task 1: Charge control

**Model:** opus (charge start/stop, reauth, the start guard) · **Wave:** 1

**Files:**
- Modify: `custom_components/nortec_go/const.py`
- Create: `custom_components/nortec_go/charge_control.py`
- Modify: `tests/conftest.py` (`make_charger`)
- Create: `tests/test_charge_control.py`

**Interfaces:**
- Consumes: `pynortecgo` 0.2.0 public API; `NortecGoConfigEntry` from `entry.py`.
- Produces (later tasks rely on these exact names):
  - `const.py`: `START_CONFIRM_TIMEOUT`, `CHARGE_CONTROL_STORE_VERSION`, `CHARGE_CONTROL_STORE_KEY`,
    `START_BLOCKED_ISSUE_ID`.
  - `charge_control.py`:
    - `@dataclass(frozen=True) class ChargeControlState: blocked: bool = False; start_pending: bool = False; stop_asked: bool = False`
    - `CHARGE_STATUS_OPTIONS: list[str]`
    - `def charge_is_open(charger: Charger) -> bool`
    - `def is_charge_on(charger: Charger, control: ChargeControlState) -> bool`
    - `def charge_status(charger: Charger, control: ChargeControlState) -> str | None`
    - `class ChargeControl:`
      - `__init__(self, hass: HomeAssistant, entry: NortecGoConfigEntry, client: NortecGoClient, *, on_change: Callable[[], None], request_refresh: Callable[[], Coroutine[Any, Any, None]]) -> None`
      - `start_attempts: int` (attribute)
      - `state -> ChargeControlState` (property)
      - `start_pending -> bool` (property)
      - `async def async_load(self) -> None`
      - `async def async_start(self) -> None`
      - `async def async_stop(self) -> None`
      - `@callback def on_charger_read(self, charger: Charger, start_attempts: int) -> None`
      - `@callback def clear_block(self) -> None`
      - `async def async_shutdown(self) -> None`
    - `async def async_remove_charge_control(hass: HomeAssistant, entry_id: str) -> None`
  - `tests/conftest.py`: `make_charger(..., state: ChargerState = ChargerState.AVAILABLE)`.

- [ ] **Step 1: Constants**

Append to `custom_components/nortec_go/const.py`:

```python
# The charge switch's start guard (D26).
START_CONFIRM_TIMEOUT: Final = timedelta(minutes=10)
CHARGE_CONTROL_STORE_VERSION: Final = 1
CHARGE_CONTROL_STORE_KEY: Final = "nortec_go.{entry_id}.charge_control"
START_BLOCKED_ISSUE_ID: Final = "start_blocked_{entry_id}"
```

- [ ] **Step 2: `make_charger` gains `state`**

In `tests/conftest.py`, add `ChargerState` handling to `make_charger`:

```python
def make_charger(
    charger_id: int = FAKE_CHARGER_ID,
    name: str = FAKE_CHARGER_NAME,
    *,
    is_connected: bool = False,
    charge_state: ChargeState | None = None,
    state: ChargerState = ChargerState.AVAILABLE,
) -> Charger:
    """Return a charger; idle and unplugged unless told otherwise."""
    return Charger(
        id=charger_id,
        name=name,
        max_kw=11.0,
        state=state,
        state_raw=state.value,
        is_connected=is_connected,
        charge_state=charge_state,
        charge_state_raw=None if charge_state is None else charge_state.value,
        charge_id=None if charge_state is None else "fake-charge-id",
        can_stop=None if charge_state is None else True,
    )
```

Run `uv run pytest -q`: all existing tests still pass.

- [ ] **Step 3: Write the failing tests for the pure functions**

Create `tests/test_charge_control.py`:

```python
"""Tests for the Nortec Go charge control: start, stop, pending start and the start guard."""

import asyncio
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
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nortec_go.charge_control import (
    ChargeControl,
    ChargeControlState,
    async_remove_charge_control,
    charge_is_open,
    charge_status,
    is_charge_on,
)
from custom_components.nortec_go.const import DOMAIN, START_CONFIRM_TIMEOUT

from .conftest import make_charger

IDLE = ChargeControlState()
PENDING = ChargeControlState(start_pending=True)
PENDING_STOP = ChargeControlState(start_pending=True, stop_asked=True)
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
        (None, PENDING_STOP, False),
        (ChargeState.CHARGING, PENDING_STOP, False),
    ],
)
def test_is_charge_on(
    charge_state: ChargeState | None, control: ChargeControlState, expected: bool
) -> None:
    """On for an open, not ending charge, or a pending start without a stop asked."""
    charger = make_charger(is_connected=True, charge_state=charge_state)
    assert is_charge_on(charger, control) is expected


@pytest.mark.parametrize(
    ("charger", "control", "expected"),
    [
        (CHARGING, BLOCKED, "start_blocked"),
        (CONNECTED, PENDING, "starting"),
        (CONNECTED, PENDING_STOP, "stopping"),
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
    ],
)
def test_charge_status(
    charger: Any, control: ChargeControlState, expected: str | None
) -> None:
    """The status follows the spec's table, first match wins."""
    assert charge_status(charger, control) == expected
```

Run: `uv run pytest tests/test_charge_control.py -q` — FAIL (module missing).

- [ ] **Step 4: Implement the pure functions**

The block below is the whole of `charge_control.py`. **In this step write only** the imports, the
constants, `ChargeControlState`, `charge_is_open`, `_charge_happened`, `is_charge_on` and `charge_status`
(everything above `_parse_time`). The rest is written in Step 6, after Step 5's tests fail.

Create `custom_components/nortec_go/charge_control.py`:

```python
"""The Nortec Go charge control: start and stop, the pending start and the start guard (D26)."""

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
    """The Charge switch's state (§2.1)."""
    if control.stop_asked:
        return False
    return control.start_pending or charger.charge_state in _CHARGE_ON


def charge_status(charger: Charger, control: ChargeControlState) -> str | None:
    """The Charge status sensor's value (§2.2); None is Home Assistant's unknown."""
    if control.blocked:
        return "start_blocked"
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
            stop_asked = data["stop_asked"]
            if not isinstance(stop_asked, bool):
                raise TypeError("stop_asked is not a bool")
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
        """Call stop_charge() once, under the lock; raises translated errors."""
        try:
            await self._client.stop_charge()
        except NoActiveChargeError:
            pass
        except ChargeNotStoppableError:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="charge_not_stoppable"
            ) from None
        except AuthError:
            self._entry.async_start_reauth(self._hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="auth_failed"
            ) from None
        except NortecGoError as err:
            _LOGGER.warning(
                "Stopping the charge failed: %s: %s", type(err).__name__, err
            )
            self._request_read()
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="stop_failed"
            ) from None
        if self._pending_since is not None:
            self._pending_since = None
            self._stop_asked = False
            self._changed()
        self._request_read()

    async def _async_background_stop(self) -> None:
        """The stop asked for during a pending start, now that the charge is open."""
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
        if start_attempts != self.start_attempts:
            return  # a stale read: it began before the latest start attempt
        changed = False
        if self._pending_since is not None:
            if self._stop_asked and charge_is_open(charger):
                self._pending_since = None
                self._stop_asked = False
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
```

Run: `uv run pytest tests/test_charge_control.py -q` — the pure-function tests PASS (only the Step 3 tests exist yet).

- [ ] **Step 5: Write the failing `ChargeControl` tests**

Append to `tests/test_charge_control.py`. The fixture builds a control against a real `hass`, a
`MockConfigEntry` and a mocked client, with no coordinator:

```python
@pytest.fixture
def entry(hass: HomeAssistant, mock_config_entry: MockConfigEntry) -> MockConfigEntry:
    """conftest's entry (with email, device ID and tokens, so reauth can run), added to hass."""
    mock_config_entry.add_to_hass(hass)
    return mock_config_entry


@pytest.fixture
def client() -> AsyncMock:
    """A mocked client; nothing here reaches the real API."""
    return AsyncMock(spec=NortecGoClient)


@pytest.fixture
async def control(
    hass: HomeAssistant, entry: MockConfigEntry, client: AsyncMock
) -> ChargeControl:
    """A loaded control that has seen one connected, idle read."""
    control = ChargeControl(
        hass, entry, client, on_change=MagicMock(), request_refresh=AsyncMock()
    )
    await control.async_load()
    control.on_charger_read(CONNECTED, control.start_attempts)
    return control


def _issue(hass: HomeAssistant, entry: MockConfigEntry) -> ir.IssueEntry | None:
    return ir.async_get(hass).async_get_issue(DOMAIN, f"start_blocked_{entry.entry_id}")


async def test_start_sets_pending_and_asks_for_a_read(
    hass: HomeAssistant, control: ChargeControl, client: AsyncMock
) -> None:
    """A successful start is pending, tells the coordinator and asks for a read."""
    await control.async_start()
    await hass.async_block_till_done()
    client.start_charge.assert_awaited_once()
    assert control.state == PENDING
    control._on_change.assert_called()  # type: ignore[attr-defined]
    control._request_refresh.assert_awaited()  # type: ignore[attr-defined]


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
    assert control.state == IDLE


async def test_start_hold_error_blocks(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    client: AsyncMock,
) -> None:
    """A ChargeStartError with a hold blocks, raises the issue and asks for a read."""
    client.start_charge.side_effect = ChargeStartError(ChargeStartStep.CONFIRM, True)
    with pytest.raises(HomeAssistantError) as exc_info:
        await control.async_start()
    await hass.async_block_till_done()
    assert exc_info.value.translation_key == "start_failed_hold"
    assert exc_info.value.__cause__ is None
    assert control.state == BLOCKED
    issue = _issue(hass, entry)
    assert issue is not None
    assert issue.translation_key == "start_blocked"
    assert issue.is_fixable
    assert issue.translation_placeholders == {"name": "Garage charger"}
    assert issue.data == {"entry_id": entry.entry_id}
    control._request_refresh.assert_awaited()  # type: ignore[attr-defined]
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
    assert control.state == IDLE


async def test_start_already_active(control: ChargeControl, client: AsyncMock) -> None:
    """ChargeAlreadyActiveError: no error, a read asked for, no pending start."""
    client.start_charge.side_effect = ChargeAlreadyActiveError("x")
    await control.async_start()
    assert control.state == IDLE


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
    assert control.state == PENDING_STOP
    control.on_charger_read(CHARGING, control.start_attempts)
    await hass.async_block_till_done(wait_background_tasks=True)
    client.stop_charge.assert_awaited_once()
    assert control.state == IDLE


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


@pytest.mark.parametrize(
    ("error", "key"),
    [
        (NoActiveChargeError("x"), None),
        (ChargeNotStoppableError("x"), "charge_not_stoppable"),
        (AuthError("x"), "auth_failed"),
        (NortecGoConnectionError("x"), "stop_failed"),
    ],
)
async def test_stop_errors(
    control: ChargeControl, client: AsyncMock, error: Exception, key: str | None
) -> None:
    """Stop errors map to translated errors; no active charge is not an error."""
    control.on_charger_read(CHARGING, control.start_attempts)
    client.stop_charge.side_effect = error
    if key is None:
        await control.async_stop()
    else:
        with pytest.raises(HomeAssistantError) as exc_info:
            await control.async_stop()
        assert exc_info.value.translation_key == key
    client.stop_charge.assert_awaited_once()


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
    await hass.async_block_till_done()
    await async_remove_charge_control(hass, entry.entry_id)
    assert STORE_KEY.format(entry.entry_id) not in hass_storage
    assert _issue(hass, entry) is None
```

```python
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
```

Also add `{"blocked_since": "2026-09-26T20:00:00", "start_pending_since": None, "stop_asked": False}` (a
naive time) to `test_wrong_shape_store_blocks`' parameters.

- [ ] **Step 6: Implement `ChargeControl`**

Run: `uv run pytest tests/test_charge_control.py -q` — the Step 5 tests FAIL (no `ChargeControl` yet).
Now write the rest of the Step 4 block (from `_parse_time` to the end) into `charge_control.py`.

Notes for the implementer:
- `async_delay_save(..., 0)` writes on the next loop turn; `await hass.async_block_till_done()` before
  reading `hass_storage`. If a test needs the write sooner, that's a test issue, not a reason to use
  `async_save`.
- `test_stale_read_changes_nothing` and `test_second_start_is_noop` are Review Focus 1 and 2: keep them.
- Wrap long lines with `ruff format`; fix any test that doesn't match the code above by fixing the code, not
  by weakening the assertion.

Run: `uv run pytest tests/test_charge_control.py -q` — fix until PASS.

- [ ] **Step 7: Gates and commit**

Run the gates (`CLAUDE.md` → Commands). Coverage of `charge_control.py` should be 100%; add a test for any
missed line. Commit `feat: charge control with the start guard (#9)`.

---

### Task 2: Coordinator, setup, removal and translations

**Model:** opus (charge start/stop wiring, the stale-read counter, coordinator semantics) · **Wave:** 2

**Files:**
- Modify: `custom_components/nortec_go/coordinator.py`
- Modify: `custom_components/nortec_go/__init__.py`
- Modify: `custom_components/nortec_go/strings.json`, `custom_components/nortec_go/translations/en.json`
- Modify: `tests/test_coordinator.py`, `tests/test_init.py`

**Interfaces:**
- Consumes: Task 1's `ChargeControl`, `ChargeControlState`, `async_remove_charge_control`.
- Produces:
  - `NortecGoData(charger: Charger, vehicle: Vehicle | None, control: ChargeControlState)`.
  - `NortecGoCoordinator.charge_control: ChargeControl`.
  - Translations for every key Tasks 3–5 use (below).

- [ ] **Step 1: Write the failing coordinator tests**

Add to `tests/test_coordinator.py` (reuse its `_coordinator` helper and `copenhagen` fixture):

```python
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
    """A pending start reads every 5 minutes."""
    mock_client.get_charger.return_value = make_charger(is_connected=True)
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    await coordinator.charge_control.async_start()
    await hass.async_block_till_done()
    assert coordinator.update_interval == INTERVAL_CHARGING
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
    """A timeout on a read equal to the last one still reaches listeners (Review Focus 3)."""
    mock_client.get_charger.return_value = make_charger(is_connected=True)
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    await coordinator.charge_control.async_start()
    await hass.async_block_till_done()
    listener = MagicMock()
    coordinator.async_add_listener(listener)
    freezer.tick(START_CONFIRM_TIMEOUT)
    await coordinator.async_refresh()
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
    await coordinator.charge_control.async_stop()
    await hass.async_block_till_done()
    mock_client.stop_charge.assert_awaited_once()
    assert not coordinator.last_update_success
    state = hass.states.get("binary_sensor.garage_charger_charging")
    assert state is not None
    assert state.state == "unavailable"


async def test_start_soon_after_a_refresh_gets_its_read(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A read asked for inside the debouncer's 10 s cooldown isn't dropped by a later change."""
    mock_client.get_charger.return_value = make_charger(is_connected=True)
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    control = coordinator.charge_control
    await control.async_start()  # asks for a read at once; the cooldown begins
    await hass.async_block_till_done()
    await control.async_stop()  # stop asked; its read is deferred by the cooldown
    await control.async_start()  # clears stop asked: a change with no new read asked
    calls = mock_client.get_charger.await_count
    freezer.tick(timedelta(seconds=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_client.get_charger.await_count > calls
```

Imports to add: `asyncio`, `MagicMock`, `ChargeControlState` from `charge_control`,
`START_CONFIRM_TIMEOUT` from `const`, `NortecGoConnectionError` (already imported).

Add to `tests/test_init.py`:

```python
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
```

```python
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
    unload = hass.async_create_task(
        hass.config_entries.async_unload(mock_config_entry.entry_id)
    )
    await asyncio.sleep(0)
    release.set()
    with pytest.raises(HomeAssistantError):
        await start
    assert await unload
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.runtime_data.data.control.blocked
```

Imports to add in `test_init.py`: `make_charger` from `.conftest`; `ChargeStartError`, `ChargeStartStep` from
`pynortecgo`; `HomeAssistantError` from `homeassistant.exceptions` (`asyncio`, `ir` and `Any` are already
imported).

Run: `uv run pytest tests/test_coordinator.py tests/test_init.py -q` — FAIL.

- [ ] **Step 2: Coordinator**

In `custom_components/nortec_go/coordinator.py`:

```python
from dataclasses import dataclass, replace

from .charge_control import ChargeControl, ChargeControlState


@dataclass(frozen=True)
class NortecGoData:
    """One read of the charger and the car, with the charge control's state."""

    charger: Charger
    vehicle: Vehicle | None
    control: ChargeControlState
```

In `NortecGoCoordinator.__init__`, after `self.client = client`:

```python
        self.charge_control = ChargeControl(
            hass,
            entry,
            client,
            on_change=self._async_control_changed,
            request_refresh=self.async_request_refresh,
        )
```

In `_async_update_data`:

```python
        start_attempts = self.charge_control.start_attempts
        try:
            charger = await self.client.get_charger()
        except ...  # unchanged
        self.charge_control.on_charger_read(charger, start_attempts)
        vehicle = await self._async_read_vehicle()
        self.update_interval = (
            INTERVAL_CHARGING
            if self.charge_control.start_pending
            else interval_for(charger)
        )
        return NortecGoData(
            charger=charger, vehicle=vehicle, control=self.charge_control.state
        )
```

And the change-outside-a-read callback:

```python
    @callback
    def _async_control_changed(self) -> None:
        """Carry a control change made outside a read to the entities.

        Not async_set_updated_data: it would mark a failed coordinator as successful and
        cancel a requested read.
        """
        if self.data is None:
            return
        self.data = replace(self.data, control=self.charge_control.state)
        self.async_update_listeners()
```

Update every existing `NortecGoData(...)` construction in tests, if any, to pass `control=ChargeControlState()`.

- [ ] **Step 3: Setup and removal**

In `custom_components/nortec_go/__init__.py`:
- after `coordinator = NortecGoCoordinator(hass, entry, client)`: `await coordinator.charge_control.async_load()`
  (before the first refresh);
- `async_remove_entry`: also `await async_remove_charge_control(hass, entry.entry_id)` (import from
  `.charge_control`);
- `async_unload_entry`:

```python
async def async_unload_entry(hass: HomeAssistant, entry: NortecGoConfigEntry) -> bool:
    """Unload a config entry; the charge control saves and stops taking calls."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.charge_control.async_shutdown()
    return unloaded
```

- [ ] **Step 4: Translations**

Add to `strings.json` and the identical `translations/en.json` (merge into the existing `entity` block):

```json
  "entity": {
    "sensor": {
      "charge_status": {
        "name": "Charge status",
        "state": {
          "start_blocked": "Start blocked",
          "starting": "Starting",
          "charging": "Charging",
          "paused": "Paused",
          "stopping": "Stopping",
          "not_released": "Waiting for replug",
          "unplugged": "Unplugged",
          "idle": "Idle"
        }
      }
    },
    "switch": {
      "charge": {
        "name": "Charge"
      }
    }
  },
  "exceptions": {
    "start_blocked": {
      "message": "Starts are blocked after a failed start that may have placed a card hold. Unplug and replug the cable, or confirm in the repair issue."
    },
    "charger_state_unknown": {
      "message": "The charger reports a state this integration doesn't know, so it won't start a charge."
    },
    "cable_not_connected": {
      "message": "No cable is connected to the charger."
    },
    "charger_not_released": {
      "message": "The charger still holds the last charge. Unplug and replug the cable, then start again."
    },
    "no_payment_source": {
      "message": "The Nortec Go account has no saved card to pay for a charge."
    },
    "multiple_payment_sources": {
      "message": "The Nortec Go account has more than one saved card. Only one card is supported."
    },
    "no_vehicle": {
      "message": "The Nortec Go account has no car."
    },
    "multiple_vehicles": {
      "message": "The Nortec Go account has more than one car. Only one car is supported."
    },
    "start_failed_hold": {
      "message": "Starting the charge failed after a card hold may have been placed. Starts are blocked; see the repair issue."
    },
    "start_failed": {
      "message": "Starting the charge failed. No card hold was placed. Check the Home Assistant logs."
    },
    "auth_failed": {
      "message": "The Nortec Go session was rejected. Sign in again from the repair notice."
    },
    "charge_not_stoppable": {
      "message": "The charge can't be stopped right now."
    },
    "stop_failed": {
      "message": "Stopping the charge failed; it may have stopped anyway. Check the charger."
    },
    "unloading": {
      "message": "The Nortec Go integration is reloading. Try again in a moment."
    }
  },
  "issues": {
    "start_blocked": {
      "title": "Charge starts are blocked on {name}",
      "fix_flow": {
        "step": {
          "confirm": {
            "title": "Allow charge starts again on {name}",
            "description": "A charge start failed after a card hold may have been placed, so starts are blocked to avoid another hold. A hold that led to no charge is expected to expire by itself.\n\nCheck the charger in the Nortec Go app. Then unplug and replug the cable, or select **Submit** to allow starts again."
          }
        },
        "abort": {
          "not_loaded": "The Nortec Go integration isn't loaded. Reload it and try again."
        }
      }
    },
    "start_blocked_store": {
      "title": "Charge starts are blocked on {name}",
      "fix_flow": {
        "step": {
          "confirm": {
            "title": "Allow charge starts again on {name}",
            "description": "The saved start guard couldn't be read, so starts are blocked to be safe.\n\nCheck the charger in the Nortec Go app. Then unplug and replug the cable, or select **Submit** to allow starts again."
          }
        },
        "abort": {
          "not_loaded": "The Nortec Go integration isn't loaded. Reload it and try again."
        }
      }
    }
  }
```

The `auth_failed` text says "repair notice" because HA shows reauth as a notice under Settings.

- [ ] **Step 5: Run tests, gates, commit**

`uv run pytest -q` — PASS. Gates. Commit `feat: wire the charge control into the coordinator (#9)`.

---

### Task 3: Charge switch

**Model:** opus (charge start/stop) · **Wave:** 3

**Files:**
- Create: `custom_components/nortec_go/switch.py`
- Modify: `custom_components/nortec_go/__init__.py` (`PLATFORMS` only)
- Create: `tests/test_switch.py`

**Interfaces:**
- Consumes: `is_charge_on`, `NortecGoCoordinator.charge_control` (`async_start`, `async_stop`),
  `NortecGoData.control`, `NortecGoChargerEntity`.
- Produces: `switch.<charger>_charge` (`switch.garage_charger_charge` in tests).

- [ ] **Step 1: Failing tests** — create `tests/test_switch.py`:

```python
"""Tests for the Nortec Go Charge switch."""

from unittest.mock import AsyncMock

from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
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
from pynortecgo import CableNotConnectedError, ChargeState, NortecGoConnectionError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import make_charger, setup_integration

ENTITY_ID = "switch.garage_charger_charge"


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
    assert hass.states.get(ENTITY_ID).state == STATE_ON
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
    assert hass.states.get(ENTITY_ID).state == STATE_OFF
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
    assert hass.states.get(ENTITY_ID).state != STATE_UNAVAILABLE
    assert (
        hass.states.get("binary_sensor.garage_charger_charging").state
        == STATE_UNAVAILABLE
    )
    await _call(hass, SERVICE_TURN_OFF)
    mock_client.stop_charge.assert_awaited_once()
```

If `match=` can't see the translated text (HA formats it from the loaded translations), assert
`exc_info.value.translation_key == "cable_not_connected"` instead and say so in the report.

Run — FAIL.

- [ ] **Step 2: Implement** `custom_components/nortec_go/switch.py`:

```python
"""The Nortec Go Charge switch: starts and stops a charge (§2.1)."""

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .charge_control import is_charge_on
from .coordinator import NortecGoCoordinator
from .entity import NortecGoChargerEntity
from .entry import NortecGoConfigEntry

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NortecGoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the Charge switch."""
    async_add_entities([NortecGoChargeSwitch(entry.runtime_data)])


class NortecGoChargeSwitch(NortecGoChargerEntity, SwitchEntity):
    """Starts and stops a charge through the charge control."""

    def __init__(self, coordinator: NortecGoCoordinator) -> None:
        """Name the switch Charge."""
        super().__init__(coordinator, "charge")

    @property
    def available(self) -> bool:
        """Available after a failed read too, so turn_off still reaches stop_charge (§2.1)."""
        return True

    @property
    def is_on(self) -> bool:
        """On for an open, not ending charge, or our pending start."""
        data = self.coordinator.data
        return is_charge_on(data.charger, data.control)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start a charge (guarded; never retried)."""
        await self.coordinator.charge_control.async_start()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop the charge."""
        await self.coordinator.charge_control.async_stop()
```

In `__init__.py`: `PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR, Platform.SWITCH]`.

- [ ] **Step 3: Run tests, gates, commit** `feat: Charge switch (#9)`.

---

### Task 4: Charge status sensor

**Model:** sonnet · **Wave:** 3

**Files:**
- Modify: `custom_components/nortec_go/sensor.py`
- Modify: `tests/test_sensor.py`

**Interfaces:**
- Consumes: `charge_status`, `CHARGE_STATUS_OPTIONS`, `NortecGoData.control`, translations from Task 2.
- Produces: `sensor.<charger>_charge_status` (`sensor.garage_charger_charge_status` in tests).

- [ ] **Step 1: Failing tests** — add to `tests/test_sensor.py`:

```python
@pytest.mark.parametrize(
    ("charger", "expected"),
    [
        (make_charger(is_connected=False), "unplugged"),
        (make_charger(is_connected=True), "idle"),
        (
            make_charger(is_connected=True, charge_state=ChargeState.CHARGING),
            "charging",
        ),
        (
            make_charger(is_connected=True, state=ChargerState.BUSY_NON_RELEASED),
            "not_released",
        ),
        (make_charger(is_connected=True, state=ChargerState.UNKNOWN), STATE_UNKNOWN),
    ],
)
async def test_charge_status_sensor(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    charger: Charger,
    expected: str,
) -> None:
    """Charge status is an enum sensor with the spec's options."""
    mock_client.get_charger.return_value = charger
    await setup_integration(hass, mock_config_entry)
    state = hass.states.get("sensor.garage_charger_charge_status")
    assert state is not None
    assert state.state == expected
    assert state.attributes[ATTR_DEVICE_CLASS] == SensorDeviceClass.ENUM
    assert state.attributes["options"] == CHARGE_STATUS_OPTIONS


async def test_charge_status_follows_the_control(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A pending start shows starting at once, without a read."""
    mock_client.get_charger.return_value = make_charger(is_connected=True)
    await setup_integration(hass, mock_config_entry)
    await mock_config_entry.runtime_data.charge_control.async_start()
    assert hass.states.get("sensor.garage_charger_charge_status").state == "starting"
```

Imports to add where missing: `ATTR_DEVICE_CLASS`, `STATE_UNKNOWN`, `SensorDeviceClass`, `Charger`, `ChargerState`,
`ChargeState`, `CHARGE_STATUS_OPTIONS`.
(Every row of the spec's §2.2 table is covered by Task 1's `test_charge_status`; these tests check the
entity wiring.) Run — FAIL.

- [ ] **Step 2: Implement** in `sensor.py`: import `charge_status`, `CHARGE_STATUS_OPTIONS`; add
`NortecGoChargeStatusSensor(coordinator)` to `entities` right after the price sensor:

```python
class NortecGoChargeStatusSensor(NortecGoChargerEntity, SensorEntity):
    """The charge's phase and the start guard (§2.2)."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = CHARGE_STATUS_OPTIONS

    def __init__(self, coordinator: NortecGoCoordinator) -> None:
        """Name the sensor Charge status."""
        super().__init__(coordinator, "charge_status")

    @property
    def native_value(self) -> str | None:
        """The status, or None (unknown) for an unknown charger state."""
        data = self.coordinator.data
        return charge_status(data.charger, data.control)
```

- [ ] **Step 3: Run tests, gates, commit** `feat: Charge status sensor (#9)`.

---

### Task 5: Repair fix flow

**Model:** sonnet · **Wave:** 3

**Files:**
- Create: `custom_components/nortec_go/repairs.py`
- Create: `tests/test_repairs.py`

**Interfaces:**
- Consumes: `ChargeControl.clear_block`, the issue from Task 1 (`data={"entry_id": …}`), translations
  from Task 2.

- [ ] **Step 1: Failing tests** — create `tests/test_repairs.py`, driving the flow through HA's repairs
HTTP API (the same way core tests do):

```python
"""Tests for the Nortec Go repair fix flow."""

from http import HTTPStatus
from typing import Any
from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.nortec_go.const import DOMAIN

from .conftest import make_charger, setup_integration


def _blocked(hass_storage: dict[str, Any], entry: MockConfigEntry) -> None:
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


async def _start_fix(client: Any, issue_id: str) -> dict[str, Any]:
    resp = await client.post(
        "/api/repairs/issues/fix", json={"handler": DOMAIN, "issue_id": issue_id}
    )
    assert resp.status == HTTPStatus.OK
    return await resp.json()


async def test_fix_flow_clears_the_block(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    hass_storage: dict[str, Any],
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
) -> None:
    """Confirming clears the block; the issue is gone."""
    _blocked(hass_storage, mock_config_entry)
    mock_client.get_charger.return_value = make_charger(is_connected=True)
    await setup_integration(hass, mock_config_entry)
    assert await async_setup_component(hass, "repairs", {})
    issue_id = f"start_blocked_{mock_config_entry.entry_id}"
    client = await hass_client()
    flow = await _start_fix(client, issue_id)
    assert flow["step_id"] == "confirm"
    resp = await client.post(f"/api/repairs/issues/fix/{flow['flow_id']}", json={})
    assert (await resp.json())["type"] == "create_entry"
    await hass.async_block_till_done()
    assert not mock_config_entry.runtime_data.data.control.blocked
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


async def test_fix_flow_aborts_when_not_loaded(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    hass_storage: dict[str, Any],
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
) -> None:
    """With the entry unloaded, the flow aborts with not_loaded."""
    _blocked(hass_storage, mock_config_entry)
    mock_client.get_charger.return_value = make_charger(is_connected=True)
    await setup_integration(hass, mock_config_entry)
    assert await async_setup_component(hass, "repairs", {})
    await hass.config_entries.async_unload(mock_config_entry.entry_id)
    client = await hass_client()
    flow = await _start_fix(client, f"start_blocked_{mock_config_entry.entry_id}")
    assert flow["type"] == "abort"
    assert flow["reason"] == "not_loaded"
```

Run — FAIL.

- [ ] **Step 2: Implement** `custom_components/nortec_go/repairs.py`:

```python
"""The Nortec Go repair fix flow: allow charge starts again (§3.5)."""

from typing import Any

from homeassistant.components.repairs import RepairsFlow, RepairsFlowResult
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant


class StartBlockedRepairFlow(RepairsFlow):
    """One confirm step that clears the start block."""

    def __init__(self, entry_id: str) -> None:
        """Remember the entry the issue belongs to."""
        self._entry_id = entry_id

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> RepairsFlowResult:
        """Go to the confirm step."""
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> RepairsFlowResult:
        """Clear the block when the owner confirms."""
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if entry is None or entry.state is not ConfigEntryState.LOADED:
            return self.async_abort(reason="not_loaded")
        if user_input is not None:
            entry.runtime_data.charge_control.clear_block()
            return self.async_create_entry(data={})
        return self.async_show_form(
            step_id="confirm", description_placeholders={"name": entry.title}
        )


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None
) -> RepairsFlow:
    """Create the fix flow for a start_blocked issue."""
    assert data is not None  # the issue is always created with its entry ID
    return StartBlockedRepairFlow(str(data["entry_id"]))
```

- [ ] **Step 3: Run tests, gates, commit** `feat: repair fix flow for blocked starts (#9)`. hassfest runs in
CI only; if it asks for `repairs` in `manifest.json` `dependencies`, that fix goes in the branch review round.

---

### Task 6: Docs, changelog, quality scale, decision

**Model:** sonnet · **Wave:** 3 (docs, against the names this plan fixes)

**Files:**
- Modify: `docs/user/nortec_go.md`, `CHANGELOG.md`, `custom_components/nortec_go/quality_scale.yaml`,
  `docs/decisions.md`

- [ ] **Step 1: User docs** — per the spec's §7, in `docs/user/nortec_go.md`:
  - *Supported functionality → Charger* table: add rows
    `| Charge | Switch | Starts and stops a charge. On while a charge is starting, charging or paused, and right after a start until the charger shows it |`
    and `| Charge status | Sensor | Start blocked, Starting, Charging, Paused, Stopping, Waiting for replug, Unplugged or Idle |`.
  - *Use cases → EV Smart Charging*: add rows *Charger control entity* → *Charge*; *Charging state entity* →
    *Charging* (or empty); the paragraph on why not the *Charge* switch; keep *Continuous charging preferred*
    on, because the charger needs a replug after a stop.
  - New section *Starting a charge* (after *Use cases*): card holds, never retried, the block and how it
    clears (the cable unplugged, a charge seen, or the repair issue), a pending start shows on for up to 10
    minutes, replug after a stop.
  - *Data updates*: add "every 5 minutes while a start is pending".
  - *Troubleshooting* (add the section if missing): "Starts are blocked" → see *Starting a charge*.
  - *Known limitations*: the five bullets of spec §7.
- [ ] **Step 2: `CHANGELOG.md`** *Unreleased → Added*: "A *Charge* switch that starts and stops charging,
  guarded against repeated starts that could place extra card holds, a *Charge status* sensor, and a repair
  issue to allow starts again after a failed start."
- [ ] **Step 3: `quality_scale.yaml`**: `action-exceptions: done`; `repair-issues: done`;
  `entity-unavailable` as `{status: done, comment: "The Charge switch stays available after a failed read on purpose, so turn_off still reaches the charger; the other entities follow the rule."}`;
  `exception-translations` as `{status: todo, comment: "The switch's exceptions are translated; the coordinator's UpdateFailed and ConfigEntryError texts aren't yet."}`.
  Run `uv run pytest tests/test_quality_scale.py -q`.
- [ ] **Step 4: `docs/decisions.md`**: append D26 with the text of the spec's §8, in the log's format
  (Date 2026-09-26, Status active, Source: link to the spec, *Decisions* and §3).
- [ ] **Step 5: Gates, commit** `docs: charge switch user docs, changelog, quality scale, D26 (#9)`.

---

## After the tasks

- Branch review (`full-reviewer`), learnings (way-of-working step 8), PR description with rulings.
- The owner's live test: one start and one stop, **only with the owner's explicit OK**.
