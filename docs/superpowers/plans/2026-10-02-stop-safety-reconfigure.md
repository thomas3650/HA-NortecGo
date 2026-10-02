# A stop that holds, start guard hardening, and reconfigure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. In this repo the flow in `docs/way-of-working.md` §1–2 applies (implementer and task-reviewer agents, waves, worktrees).

**Goal:** Turning *Charge* off holds until the charge is seen off: the stop is stored, tried again at most 10 times and for at most 30 minutes, and ends in a repair issue when it can't be done (D50; #85, #32, #26). The start guard fails safe on a corrupt store, a lost block reason and an unexpected start exception (#26), and a reconfigure step changes the sign-in (#44).

**Architecture:** Six tasks. Task 1 adds the store module (`charge_control_store.py`: shape, migration, corrupt-file check) and the constants. Task 2 adds the reconfigure step; it shares no file with the charge control. Task 3 moves the control onto the store module and fixes the three hardening points, with the stop still behaving as today. Task 4 makes the stop a stored one: tried from a turn-off or a read, one call per 2 minutes, ended only by a read. Task 5 adds the limits, giving up, the repair issue and the read interval, and the setup-level tests for #85. Task 6 is the docs, D50, the CHANGELOG and the quality scale comments.

**Tech Stack:** Python 3.14, Home Assistant 2026.9 custom integration, `pynortecgo` 0.8.0, pytest with `pytest-homeassistant-custom-component`, mypy strict, ruff, uv.

**Spec:** `docs/superpowers/specs/2026-10-02-stop-safety-reconfigure-design.md` (issues #85, #32, #26, #44). Read its §1 before Tasks 4 and 5: the rules there are the contract, and this plan's code follows them.

## Global Constraints

- TDD: write the failing test, see it fail, then change the code.
- **Never auto-retry `start_charge`** (hard rule 6). Nothing in this plan adds a start call, and no test expects a second `start_charge()` call. Only the stop is tried again.
- **On `AuthError`, start reauth; never log in again** (hard rule 6). A turn-off that gets `AuthError` raises `auth_failed` from `None`, as today.
- No test and no code calls a real charger; tests mock `pynortecgo`. Fixtures are built with `make_charger` from `tests/conftest.py` (hard rule 7).
- Nothing private (hard rule 3): no IDs, tokens, emails, captures or raw endpoints. Logs never hold credentials (hard rule 5); the stop's warnings hold only the error's type and text, as the start's do today.
- The limits, exact: `STOP_MAX_TRIES = 10`, `STOP_ASKED_MAX_AGE = timedelta(minutes=30)`, and the existing `STOP_CONFIRM_TIMEOUT = timedelta(minutes=2)` is also the least time between two `stop_charge()` calls.
- Only a read ends a stop as done. A call's answer never does, not `NoActiveChargeError` either.
- No `stop_charge()` call while a start is pending, to a charge that is `STOPPING` or `COMPLETED`, or to an open charger without a charge object.
- Names this plan fixes:
  - the module `custom_components/nortec_go/charge_control_store.py` with `StoredControl`, `ChargeControlStore`, `UnreadableStoreError`, `BLOCK_REASONS`;
  - the constants `STOP_MAX_TRIES`, `STOP_ASKED_MAX_AGE`, `CHARGE_CONTROL_STORE_MINOR_VERSION = 2`, `STOP_FAILED_ISSUE_ID = "stop_failed_{entry_id}"`;
  - the stored keys `blocked_since`, `block_reason`, `start_pending_since`, `stop_asked_since`, `stop_tries`, `stop_tried_at`;
  - the issue translation key `stop_failed`, the config flow step `reconfigure` and its abort reason `reconfigure_successful`;
  - the decision D50.
- `ChargeControlState` keeps its four flags (`blocked`, `start_pending`, `stop_asked`, `stop_pending`), so `diagnostics.py`, `switch.py`, `sensor.py` and `__init__.py` are not edited.
- Texts, word for word. `translations/en.json` is an exact copy of `strings.json`:
  - `config.step.reconfigure.title`: `Change the Nortec Go sign-in`
  - `config.step.reconfigure.description`: `Sign in with the email and password of the Nortec Go account that has this charger. Signing in to an account with another charger is refused.`
  - `config.step.reconfigure.data` and `data_description`: the same four texts as `config.step.user`.
  - `config.abort.reconfigure_successful`: `The sign-in was changed.`
  - `issues.start_blocked_store.fix_flow.step.confirm.description`: `The saved start guard couldn't be read, so starts are blocked to be safe. A stop you asked for earlier may not have been sent.\n\nCheck the charger in the Nortec Go app. Then unplug and replug the cable, or select **Submit** to allow starts again.`
  - `issues.stop_failed.title`: `A charge stop on {name} couldn't be confirmed`
  - `issues.stop_failed.fix_flow.step.confirm.title`: `The charge on {name} may still be running`
  - `issues.stop_failed.fix_flow.step.confirm.description`: `You turned Charge off, but Home Assistant couldn't stop the charge or see it stop, and has stopped trying. The charge may still be running.\n\nCheck the charger in the Nortec Go app and stop the charge there if needed. Turning Charge off again makes Home Assistant try again. Select **Submit** to dismiss this notice.`
  - Removed: `exceptions.charge_not_stoppable` and `exceptions.stop_failed`.
- Log lines, word for word (tests match on them):
  - `Stopping the charge failed (try %d of %d): %s` (warning; the last argument is `"<ErrorType>: <text>"`, or `the charge was still on %s after the charger accepted the stop` filled with `STOP_CONFIRM_TIMEOUT`)
  - `Giving up on the stop asked for: %s` (error; the argument is `no stop seen after 10 tries` or `it was asked for more than 0:30:00 ago`, built from the constants)
  - `The saved start guard couldn't be read; blocking starts to be safe` (warning)
  - `Unexpected error while starting a charge` (`_LOGGER.exception`)
- Gates before every commit (`CLAUDE.md` → Commands, including the coverage gate): `uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95`, then `uv run ruff check && uv run ruff format --check && uv run mypy && uv run actionlint && uv run zizmor --offline .github/workflows`. The "Run:" lines in the steps are the quick checks on the way; these gates come on top, right before each commit. Every new module is above 95% on its own.
- Subagents write commit messages with the Write tool to a file outside the repo (a new file per commit, named in the step), and commit with `git commit -F <file>` (no heredocs). End the message with the co-author trailer given in the dispatch.
- Match the surrounding code: one-line docstrings ending in a period; comments say why, not what; `except A, B:` without parentheses, as the code base does on Python 3.14.
- The code blocks in this plan are the intended code. If a block doesn't pass the gates as written (a ruff rule, a mypy complaint, an import that moved), fix it in the block's spirit and say so in the report; don't change a rule from the spec to make a test pass.
- The version bump (`manifest.json`, the CHANGELOG's version heading) is not part of any task: the controller runs the bump step last.

## Review Focus

- **A stop asked for before a restart, with a setup that fails after the stop was queued** (#85, case 1): the stop must still be stored, and the next setup must send it. Pinned by `test_stop_survives_a_setup_that_fails_on_the_price_read` (Task 5).
- **A reload or restart right after a stop call:** the next call must wait out the 2 minutes, and the count must not start again. Pinned by `test_reload_right_after_a_call_waits_and_keeps_the_count` (Task 4).
- **A turn-off while the charger is busy but has no charge yet** (right after a start in the app): no call, and "no active charge" must not end the stop. Pinned by `test_no_active_charge_does_not_end_the_stop` and `test_open_charger_without_a_charge_gets_no_call` (Task 4).
- **An automation that keeps turning *Charge* off after the control gave up:** the notice must stay, and the first new call must wait out the 2 minutes. Pinned by `test_turn_off_after_giving_up_keeps_the_issue_and_waits` (Task 5).
- **An upgrade with a stop asked for in the old format:** it must migrate to a stored stop, not block starts. Pinned by `test_migrates_minor_1` (Task 1) and `test_old_format_stop_is_sent_after_the_upgrade` (Task 5).
- **Confirming the stop notice while starts are blocked:** the block must stay. Pinned by `test_stop_failed_fix_leaves_a_start_block` (Task 5).

---

### Task 1: The store module and the constants

**Model:** opus — the stored state behind charge start and stop, and its migration.
**Wave:** 1

**Files:**
- Create: `custom_components/nortec_go/charge_control_store.py`
- Create: `tests/test_charge_control_store.py`
- Modify: `custom_components/nortec_go/const.py` (the charge switch block at the end)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces, for Tasks 3 to 5:
  - `StoredControl(blocked_since: datetime | None = None, block_reason: str | None = None, start_pending_since: datetime | None = None, stop_asked_since: datetime | None = None, stop_tries: int = 0, stop_tried_at: datetime | None = None)`, a frozen dataclass.
  - `ChargeControlStore(hass: HomeAssistant, entry_id: str)` with `async_load() -> StoredControl | None` (raises `UnreadableStoreError`), `async_delay_save(state: Callable[[], StoredControl]) -> None` (a callback, not awaited), `async_save(state: StoredControl) -> None`, `async_remove() -> None`.
  - `UnreadableStoreError`, `BLOCK_REASONS = ("start_blocked", "start_blocked_store")`.
  - The constants in *Global Constraints*.

Facts you need:
- `Store.async_load()` returns `None` for a missing file and for a file with a JSON decode error, which it first renames. So the only way to tell the two apart is to look for the file before the load. `Store.path` is the file's path.
- A stored minor version other than the code's goes through `_async_migrate_func(old_major_version, old_minor_version, old_data)`; what it returns is saved straight back. `prices.py` has `_PriceData`, a `Store` subclass with that method: mirror its signature.
- A stored file without `minor_version` counts as minor 1. That is every file written before this change.
- In tests the `hass_storage` fixture replaces the store's file access: `hass_storage[key] = {"version": 1, "minor_version": 2, "key": key, "data": {...}}` is what a load reads, and a save lands in `hass_storage[key]["data"]`. No file is on disk, so the file check needs its own seam: the module-level function `_file_exists`, which tests patch.
- `Store.async_delay_save(func, 0)` writes on a timer: `async_fire_time_changed(hass)` and `await hass.async_block_till_done()` let it land.

- [ ] **Step 1: Add the constants**

In `custom_components/nortec_go/const.py`, replace the block from the `STOP_CONFIRM_TIMEOUT` comment to the `START_BLOCKED_ISSUE_ID` line with:

```python
# How long the switch shows off after an accepted stop while the charger still reports the charge
# (D29). Also the least time between two stop calls (D50).
STOP_CONFIRM_TIMEOUT: Final = timedelta(minutes=2)
# A stop asked for is tried at most this many times, and for at most this long from the ask (D50).
STOP_MAX_TRIES: Final = 10
STOP_ASKED_MAX_AGE: Final = timedelta(minutes=30)
# At a restart a pending start waits at least this long, so the setup's charger read and car read (D44)
# decide first (D31).
START_LOAD_GRACE: Final = timedelta(minutes=2)
CHARGE_CONTROL_STORE_VERSION: Final = 1
CHARGE_CONTROL_STORE_MINOR_VERSION: Final = 2
CHARGE_CONTROL_STORE_KEY: Final = "nortec_go.{entry_id}.charge_control"
START_BLOCKED_ISSUE_ID: Final = "start_blocked_{entry_id}"
# The repair issue for a stop the control gave up on (D50).
STOP_FAILED_ISSUE_ID: Final = "stop_failed_{entry_id}"
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_charge_control_store.py`:

```python
"""Tests for the Nortec Go charge control's stored state: shape, migration and the corrupt-file check."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.nortec_go.charge_control_store import (
    ChargeControlStore,
    StoredControl,
    UnreadableStoreError,
    _file_exists,
)

ENTRY_ID = "fake-entry-id"
KEY = f"nortec_go.{ENTRY_ID}.charge_control"
T1 = "2026-09-26T20:00:00+00:00"
T2 = "2026-09-26T20:05:00+00:00"
T3 = "2026-09-26T20:06:00+00:00"
EMPTY: dict[str, Any] = {
    "blocked_since": None,
    "block_reason": None,
    "start_pending_since": None,
    "stop_asked_since": None,
    "stop_tries": 0,
    "stop_tried_at": None,
}


def _time(text: str) -> datetime:
    return datetime.fromisoformat(text)


def _put(
    hass_storage: dict[str, Any], data: Any, *, minor_version: int | None = 2
) -> None:
    """Put a stored file in place; no minor version is a file from before the change."""
    stored: dict[str, Any] = {"version": 1, "key": KEY, "data": data}
    if minor_version is not None:
        stored["minor_version"] = minor_version
    hass_storage[KEY] = stored


async def test_nothing_stored(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """A first setup: no file, so nothing is loaded."""
    assert await ChargeControlStore(hass, ENTRY_ID).async_load() is None


async def test_round_trip(hass: HomeAssistant, hass_storage: dict[str, Any]) -> None:
    """What is saved is loaded again, key by key."""
    state = StoredControl(
        blocked_since=_time(T1),
        block_reason="start_blocked_store",
        start_pending_since=_time(T1),
        stop_asked_since=_time(T2),
        stop_tries=3,
        stop_tried_at=_time(T3),
    )
    await ChargeControlStore(hass, ENTRY_ID).async_save(state)
    assert hass_storage[KEY]["minor_version"] == 2
    assert hass_storage[KEY]["data"] == {
        "blocked_since": T1,
        "block_reason": "start_blocked_store",
        "start_pending_since": T1,
        "stop_asked_since": T2,
        "stop_tries": 3,
        "stop_tried_at": T3,
    }
    assert await ChargeControlStore(hass, ENTRY_ID).async_load() == state


async def test_a_try_time_stays_without_a_stop(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """The last call's time belongs to the control, not to one stop (D50)."""
    _put(hass_storage, {**EMPTY, "stop_tried_at": T3})
    loaded = await ChargeControlStore(hass, ENTRY_ID).async_load()
    assert loaded == StoredControl(stop_tried_at=_time(T3))


async def test_delayed_save_lands(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """The delayed save takes the state when it is written, not when it is asked for."""
    store = ChargeControlStore(hass, ENTRY_ID)
    states = [StoredControl(), StoredControl(stop_asked_since=_time(T2))]
    store.async_delay_save(lambda: states[-1])
    assert KEY not in hass_storage
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass_storage[KEY]["data"] == {**EMPTY, "stop_asked_since": T2}


async def test_remove(hass: HomeAssistant, hass_storage: dict[str, Any]) -> None:
    """Remove deletes the stored file."""
    store = ChargeControlStore(hass, ENTRY_ID)
    await store.async_save(StoredControl())
    await store.async_remove()
    assert KEY not in hass_storage


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (
            {"blocked_since": None, "start_pending_since": None, "stop_asked": False},
            EMPTY,
        ),
        (
            {"blocked_since": None, "start_pending_since": T1, "stop_asked": True},
            {**EMPTY, "start_pending_since": T1, "stop_asked_since": T1},
        ),
        (
            {"blocked_since": None, "start_pending_since": T1, "stop_asked": False},
            {**EMPTY, "start_pending_since": T1},
        ),
        (
            {"blocked_since": T1, "start_pending_since": None, "stop_asked": False},
            {**EMPTY, "blocked_since": T1, "block_reason": "start_blocked"},
        ),
        (
            # A flag without a pending start: today's load drops it, and so does the migration.
            {"blocked_since": None, "start_pending_since": None, "stop_asked": True},
            EMPTY,
        ),
    ],
)
async def test_migrates_minor_1(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    old: dict[str, Any],
    new: dict[str, Any],
) -> None:
    """A file from before the change loads in the new shape and is saved back in it."""
    _put(hass_storage, old, minor_version=None)
    loaded = await ChargeControlStore(hass, ENTRY_ID).async_load()
    assert loaded is not None
    assert hass_storage[KEY]["data"] == new
    assert hass_storage[KEY]["minor_version"] == 2
    assert loaded.stop_asked_since == (
        None if new["stop_asked_since"] is None else _time(new["stop_asked_since"])
    )
    assert loaded.block_reason == new["block_reason"]


@pytest.mark.parametrize(
    "old",
    [
        {"blocked_since": 5},
        {"blocked_since": None, "start_pending_since": "no", "stop_asked": False},
        {},
        {"blocked_since": T1[:19], "start_pending_since": None, "stop_asked": False},
        {"blocked_since": None, "start_pending_since": None, "stop_asked": "yes"},
        ["not", "an", "object"],
    ],
)
async def test_minor_1_of_a_wrong_shape_is_unreadable(
    hass: HomeAssistant, hass_storage: dict[str, Any], old: Any
) -> None:
    """Old data of a wrong shape is passed on by the migration and refused by the shape check."""
    _put(hass_storage, old, minor_version=None)
    with pytest.raises(UnreadableStoreError):
        await ChargeControlStore(hass, ENTRY_ID).async_load()


@pytest.mark.parametrize(
    "data",
    [
        {key: value for key, value in EMPTY.items() if key != "stop_tried_at"},
        {**EMPTY, "blocked_since": 5, "block_reason": "start_blocked"},
        {**EMPTY, "blocked_since": T1},
        {**EMPTY, "blocked_since": T1, "block_reason": "something_else"},
        {**EMPTY, "block_reason": "start_blocked"},
        {**EMPTY, "stop_asked_since": "no"},
        {**EMPTY, "stop_asked_since": T2[:19]},
        {**EMPTY, "stop_tries": "1"},
        {**EMPTY, "stop_tries": True},
        {**EMPTY, "stop_tries": -1},
        {**EMPTY, "stop_tries": 1, "stop_tried_at": T3},
        {**EMPTY, "stop_asked_since": T2, "stop_tries": 1},
        {**EMPTY, "stop_asked_since": T2, "stop_tries": 11, "stop_tried_at": T3},
    ],
)
async def test_wrong_shape_is_unreadable(
    hass: HomeAssistant, hass_storage: dict[str, Any], data: dict[str, Any]
) -> None:
    """Each wrong shape of spec §3: a missing key, a wrong type, a block and its reason apart, tries that don't fit."""
    _put(hass_storage, data)
    with pytest.raises(UnreadableStoreError):
        await ChargeControlStore(hass, ENTRY_ID).async_load()


async def test_newer_minor_version_is_passed_on(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Data of a minor version this code doesn't know is loaded as it is."""
    _put(hass_storage, {**EMPTY, "stop_asked_since": T2}, minor_version=3)
    loaded = await ChargeControlStore(hass, ENTRY_ID).async_load()
    assert loaded == StoredControl(stop_asked_since=_time(T2))


async def test_corrupt_file_is_unreadable(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """A file that was on disk and loads as nothing was corrupt: unreadable, not a first setup."""
    with (
        patch(
            "custom_components.nortec_go.charge_control_store._file_exists",
            return_value=True,
        ) as exists,
        pytest.raises(UnreadableStoreError),
    ):
        await ChargeControlStore(hass, ENTRY_ID).async_load()
    assert exists.call_args.args[0].endswith(KEY)


async def test_a_file_on_disk_that_loads_is_read(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """The file check changes nothing for a file that loads."""
    _put(hass_storage, {**EMPTY, "start_pending_since": T1})
    with patch(
        "custom_components.nortec_go.charge_control_store._file_exists",
        return_value=True,
    ):
        loaded = await ChargeControlStore(hass, ENTRY_ID).async_load()
    assert loaded == StoredControl(
        start_pending_since=datetime(2026, 9, 26, 20, tzinfo=UTC)
    )


def test_file_exists(tmp_path: Any) -> None:
    """The seam itself: true for a file that is there."""
    path = tmp_path / "store"
    assert not _file_exists(str(path))
    path.write_text("{}")
    assert _file_exists(str(path))
```

- [ ] **Step 3: Run the tests to see them fail**

Run: `uv run pytest tests/test_charge_control_store.py -q`
Expected: an import error, `No module named 'custom_components.nortec_go.charge_control_store'`.

- [ ] **Step 4: Write the module**

Create `custom_components/nortec_go/charge_control_store.py`:

```python
"""The Nortec Go charge control's stored state: its shape, its migration and its file (D50)."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Final

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .const import (
    CHARGE_CONTROL_STORE_KEY,
    CHARGE_CONTROL_STORE_MINOR_VERSION,
    CHARGE_CONTROL_STORE_VERSION,
    STOP_MAX_TRIES,
)

# A block's reason is its repair issue's translation key.
BLOCK_REASONS: Final = ("start_blocked", "start_blocked_store")


class UnreadableStoreError(Exception):
    """The stored state is corrupt or has a wrong shape, so what it held is unknown."""


@dataclass(frozen=True)
class StoredControl:
    """What the charge control keeps across a restart."""

    blocked_since: datetime | None = None
    block_reason: str | None = None
    start_pending_since: datetime | None = None
    stop_asked_since: datetime | None = None
    stop_tries: int = 0
    # The last stop call's time. It stays when its stop ends: the wait between calls goes on (D50).
    stop_tried_at: datetime | None = None


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


def _parse(data: object) -> StoredControl:
    """The stored state; raises KeyError, TypeError or ValueError on a wrong shape."""
    if not isinstance(data, dict):
        raise TypeError("not an object")
    state = StoredControl(
        blocked_since=_parse_time(data["blocked_since"]),
        block_reason=data["block_reason"],
        start_pending_since=_parse_time(data["start_pending_since"]),
        stop_asked_since=_parse_time(data["stop_asked_since"]),
        stop_tries=data["stop_tries"],
        stop_tried_at=_parse_time(data["stop_tried_at"]),
    )
    if state.blocked_since is None:
        if state.block_reason is not None:
            raise ValueError("a reason without a block")
    elif state.block_reason not in BLOCK_REASONS:
        raise ValueError("a block without a known reason")
    tries = state.stop_tries
    if isinstance(tries, bool) or not isinstance(tries, int):
        raise TypeError("the tries are not a whole number")
    if not 0 <= tries <= STOP_MAX_TRIES:
        raise ValueError("the tries are out of range")
    if tries and (state.stop_asked_since is None or state.stop_tried_at is None):
        raise ValueError("tries without a stop or a try's time")
    return state


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _to_data(state: StoredControl) -> dict[str, Any]:
    return {
        "blocked_since": _iso(state.blocked_since),
        "block_reason": state.block_reason,
        "start_pending_since": _iso(state.start_pending_since),
        "stop_asked_since": _iso(state.stop_asked_since),
        "stop_tries": state.stop_tries,
        "stop_tried_at": _iso(state.stop_tried_at),
    }


def _from_minor_1(data: Any) -> Any:
    """Minor 1 had a stop flag tied to the pending start, and no block reason.

    Data of another shape is passed on unchanged, so the shape check refuses it: the
    migration itself never fails a setup.
    """
    if (
        not isinstance(data, dict)
        or set(data) != {"blocked_since", "start_pending_since", "stop_asked"}
        or not isinstance(data["stop_asked"], bool)
    ):
        return data
    pending = data["start_pending_since"]
    return {
        "blocked_since": data["blocked_since"],
        "block_reason": None if data["blocked_since"] is None else "start_blocked",
        "start_pending_since": pending,
        # The flag was only ever set during a pending start. Its time is earlier than the
        # real one, so the stop only expires sooner.
        "stop_asked_since": pending if data["stop_asked"] else None,
        "stop_tries": 0,
        "stop_tried_at": None,
    }


def _file_exists(path: str) -> bool:
    """Whether the store's file is on disk; a function of its own so tests can stand in for it."""
    return Path(path).exists()


class _ControlData(Store[dict[str, Any]]):
    """The charge control's store file, with its migration."""

    async def _async_migrate_func(
        self,
        old_major_version: int,
        old_minor_version: int,
        old_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Minor 1 to 2; a newer minor version is passed on unchanged."""
        if old_minor_version < CHARGE_CONTROL_STORE_MINOR_VERSION:
            migrated: dict[str, Any] = _from_minor_1(old_data)
            return migrated
        return old_data


class ChargeControlStore:
    """The stored charge control of one config entry, in Home Assistant's storage."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Use the store file of this entry."""
        self._hass = hass
        self._store = _ControlData(
            hass,
            CHARGE_CONTROL_STORE_VERSION,
            CHARGE_CONTROL_STORE_KEY.format(entry_id=entry_id),
            minor_version=CHARGE_CONTROL_STORE_MINOR_VERSION,
        )

    async def async_load(self) -> StoredControl | None:
        """The stored state, or None on a first setup; raises UnreadableStoreError."""
        # Before the load: it renames a corrupt file, which then looks like no file at all.
        existed = await self._hass.async_add_executor_job(
            _file_exists, self._store.path
        )
        data = await self._store.async_load()
        if data is None:
            if existed:
                raise UnreadableStoreError
            return None
        try:
            return _parse(data)
        except KeyError, TypeError, ValueError:
            raise UnreadableStoreError from None

    @callback
    def async_delay_save(self, state: Callable[[], StoredControl]) -> None:
        """Save soon, from a callback; the state is taken when it is written."""
        self._store.async_delay_save(lambda: _to_data(state()), 0)

    async def async_save(self, state: StoredControl) -> None:
        """Save now."""
        await self._store.async_save(_to_data(state))

    async def async_remove(self) -> None:
        """Delete the stored file."""
        await self._store.async_remove()
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_charge_control_store.py -q`
Expected: all pass. Then `uv run pytest -q`: everything else still passes (`charge_control.py` doesn't use the module yet).

- [ ] **Step 6: Gates and commit**

Run the gates from *Global Constraints*. `charge_control_store.py` must show no missing lines in the coverage report.

Write the message to `/tmp/stop-safety-task-1-msg.txt`:

```text
feat: the charge control's store module and the stop limits (#85, #32, #26)

The stored shape, its migration from the old stop flag and the corrupt-file
check, in a module of their own. Nothing uses it yet.
```

```bash
git add custom_components/nortec_go/charge_control_store.py custom_components/nortec_go/const.py tests/test_charge_control_store.py
git commit -F /tmp/stop-safety-task-1-msg.txt
```

---

### Task 2: The reconfigure step

**Model:** opus — auth: a sign-in, tokens, and the rule that a login is never retried.
**Wave:** 1

**Files:**
- Modify: `custom_components/nortec_go/config_flow.py` (a new step after `async_step_user`)
- Modify: `custom_components/nortec_go/strings.json` and `custom_components/nortec_go/translations/en.json` (`config.step`, `config.abort`)
- Modify: `custom_components/nortec_go/quality_scale.yaml` (`reconfiguration-flow`)
- Modify: `tests/test_config_flow.py`
- Modify: `tests/test_quality_scale.py` (`CHECKED_STATUSES`)

**Interfaces:**
- Consumes: the existing `_async_sign_in`, `USER_SCHEMA`, `create_client`, `tokens_to_data`.
- Produces: the config flow step `reconfigure`, the abort reason `reconfigure_successful`. No other task uses them.

Facts you need:
- A config flow with `async_step_reconfigure` gets a **Reconfigure** entry on the integration's page. `self._get_reconfigure_entry()` gives the entry.
- `self.async_update_reload_and_abort(entry, data_updates=...)` updates the entry, reloads it and aborts; from a reconfigure flow its reason is `reconfigure_successful`.
- `MockConfigEntry.start_reconfigure_flow(hass)` starts the flow in tests, as `start_reauth_flow` does for reauth.
- Login is rate-limited: one `login` call per submit, never a retry (hard rule 6).

- [ ] **Step 1: Write the failing tests**

In `tests/test_config_flow.py`, add after the reauth tests. `NEW_EMAIL` goes next to `USER_INPUT`; everything else is already imported.

```python
NEW_EMAIL = "other@example.com"  # fake, like FAKE_EMAIL


async def test_reconfigure(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client_class: MagicMock,
    mock_client: AsyncMock,
) -> None:
    """Reconfigure signs in once with the new email and the stored device ID, and stores the new sign-in."""
    mock_config_entry.add_to_hass(hass)
    mock_client.tokens = NEW_TOKENS
    result = await mock_config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert _suggested(result, CONF_EMAIL) == FAKE_EMAIL
    assert _suggested(result, CONF_PASSWORD) is None

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: f"  {NEW_EMAIL} ", CONF_PASSWORD: FAKE_PASSWORD},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data[CONF_EMAIL] == NEW_EMAIL
    assert tokens_from_data(mock_config_entry.data) == NEW_TOKENS
    assert mock_config_entry.data[CONF_DEVICE_ID] == FAKE_DEVICE_ID
    assert CONF_PASSWORD not in mock_config_entry.data
    assert mock_config_entry.title == FAKE_CHARGER_NAME
    assert mock_config_entry.unique_id == str(FAKE_CHARGER_ID)
    assert mock_client_class.call_args_list[0].kwargs["device_id"] == FAKE_DEVICE_ID
    mock_client.login.assert_awaited_once_with(NEW_EMAIL, FAKE_PASSWORD)


async def test_reconfigure_wrong_account(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """Signing in to an account with another charger aborts and keeps the old sign-in."""
    mock_config_entry.add_to_hass(hass)
    mock_client.get_charger.return_value = make_charger(OTHER_CHARGER_ID)
    result = await mock_config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: NEW_EMAIL, CONF_PASSWORD: FAKE_PASSWORD}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_account"
    assert mock_config_entry.data[CONF_EMAIL] == FAKE_EMAIL
    assert tokens_from_data(mock_config_entry.data) == FAKE_TOKENS


@pytest.mark.parametrize(("method", "error", "key"), FLOW_ERRORS)
async def test_reconfigure_errors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    caplog: pytest.LogCaptureFixture,
    method: str,
    error: Exception,
    key: str,
) -> None:
    """Each error shows its key, keeps the typed email, logs in once and logs no credentials; a retry succeeds."""
    mock_config_entry.add_to_hass(hass)
    getattr(mock_client, method).side_effect = error
    result = await mock_config_entry.start_reconfigure_flow(hass)
    user_input = {CONF_EMAIL: NEW_EMAIL, CONF_PASSWORD: FAKE_PASSWORD}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert result["errors"] == {"base": key}
    assert _suggested(result, CONF_EMAIL) == NEW_EMAIL
    assert _suggested(result, CONF_PASSWORD) is None
    assert mock_client.login.await_count == 1
    assert mock_config_entry.data[CONF_EMAIL] == FAKE_EMAIL
    assert NEW_EMAIL not in caplog.text
    assert FAKE_PASSWORD not in caplog.text

    getattr(mock_client, method).side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_client.login.await_count == 2
    assert mock_config_entry.data[CONF_EMAIL] == NEW_EMAIL
```

In `tests/test_quality_scale.py`, remove the line `"reconfiguration-flow": "todo",` from `CHECKED_STATUSES`: the rule becomes a plain `done`, and that list holds only rules that carry a comment.

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/test_config_flow.py -q -k reconfigure`
Expected: FAIL. The flow manager refuses a `reconfigure` source for a handler without the step (an `UnknownStep` or abort), on all three tests.

- [ ] **Step 3: Add the step**

In `custom_components/nortec_go/config_flow.py`, add this method to `NortecGoConfigFlow`, between `async_step_user` and `async_step_reauth` (a `text` block, since it is a class method):

```text
    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the email and password again, and store the new sign-in for the same charger."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        suggested: dict[str, Any] = {CONF_EMAIL: entry.data[CONF_EMAIL]}
        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            client = create_client(self.hass, device_id=entry.data[CONF_DEVICE_ID])
            result = await _async_sign_in(client, email, user_input[CONF_PASSWORD])
            if isinstance(result, str):
                errors["base"] = result
                suggested = {CONF_EMAIL: email}
            else:
                charger, tokens = result
                await self.async_set_unique_id(str(charger.id))
                self._abort_if_unique_id_mismatch(reason="wrong_account")
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_EMAIL: email, **tokens_to_data(tokens)},
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, suggested),
            errors=errors,
        )
```

- [ ] **Step 4: Add the texts**

In `strings.json`, add under `config.step`, after `user`:

```json
"reconfigure": {
  "title": "Change the Nortec Go sign-in",
  "description": "Sign in with the email and password of the Nortec Go account that has this charger. Signing in to an account with another charger is refused.",
  "data": {
    "email": "Email",
    "password": "Password"
  },
  "data_description": {
    "email": "The email address of your Nortec Go account.",
    "password": "Your Nortec Go password. It is used once to sign in and is not stored."
  }
},
```

and under `config.abort`, after `reauth_successful`:

```json
"reconfigure_successful": "The sign-in was changed.",
```

Make the same two additions in `translations/en.json`, so the two files stay identical.

- [ ] **Step 5: Set the quality scale rule**

In `quality_scale.yaml`, replace the three lines of `reconfiguration-flow` (the key, `status: todo` and its comment) with:

```yaml
  reconfiguration-flow: done
```

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/test_config_flow.py tests/test_quality_scale.py -q`
Expected: all pass. Then `uv run pytest -q`: all pass (the tests that compare `strings.json` with `translations/en.json` included).

- [ ] **Step 7: Gates and commit**

Run the gates. Write the message to `/tmp/stop-safety-task-2-msg.txt`:

```text
feat: a reconfigure step changes the account's sign-in (#44)

It signs in once with the entry's device ID, refuses another charger, and
stores the new email and tokens. reconfiguration-flow is done.
```

```bash
git add custom_components/nortec_go/config_flow.py custom_components/nortec_go/strings.json custom_components/nortec_go/translations/en.json custom_components/nortec_go/quality_scale.yaml tests/test_config_flow.py tests/test_quality_scale.py
git commit -F /tmp/stop-safety-task-2-msg.txt
```

---

### Task 3: The control uses the store module; the three hardening points

**Model:** opus — the start guard: what blocks a start, and the start's own exception handling.
**Wave:** 2

**Files:**
- Modify: `custom_components/nortec_go/charge_control.py`
- Modify: `custom_components/nortec_go/strings.json` and `translations/en.json` (`issues.start_blocked_store`)
- Modify: `tests/test_charge_control.py`
- Modify: `tests/test_coordinator.py` (`test_failed_setup_car_read_keeps_a_stop_asked`: its stored data)

**Interfaces:**
- Consumes: Task 1's `ChargeControlStore`, `StoredControl`, `UnreadableStoreError`.
- Produces, for Tasks 4 and 5: `ChargeControl` holds `_store: ChargeControlStore`, `_block_reason: str | None`, `_stop_asked_since: datetime | None`, `_stop_tries: int`, `_stop_tried_at: datetime | None`, and the method `_stored() -> StoredControl`. `ChargeControlState.stop_asked` is `self._stop_asked_since is not None`.

**The stop keeps today's behaviour in this task.** `_stop_asked_since` replaces the `_stop_asked` flag one for one: it is set where the flag was set, cleared where the flag was cleared (also by `_end_start_pending`), and loaded only together with a pending start. `_stop_tries` and `_stop_tried_at` are only carried from the load to the save. Task 4 changes the rules.

- [ ] **Step 1: Write the failing tests**

In `tests/test_charge_control.py`:

Replace `test_pending_stop_is_not_stored` with:

```python
async def test_stored_shape(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    hass_storage: dict[str, Any],
) -> None:
    """The stored shape has the six keys of minor version 2; the pending stop never reaches it."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    await control.async_shutdown()
    stored = hass_storage[STORE_KEY.format(entry.entry_id)]
    assert stored["minor_version"] == 2
    assert stored["data"] == {
        "blocked_since": None,
        "block_reason": None,
        "start_pending_since": None,
        "stop_asked_since": None,
        "stop_tries": 0,
        "stop_tried_at": None,
    }
    again = ChargeControl(
        hass, entry, AsyncMock(), on_change=MagicMock(), request_refresh=AsyncMock()
    )
    await again.async_load()
    assert again.state == IDLE
```

Add after `test_wrong_shape_store_blocks`:

```python
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
```

In `test_store_round_trip`, add after the `saved["blocked_since"]` assertion:

```text
    assert saved["block_reason"] == "start_blocked"
```

If a test in the file matches on the old warning text `The saved start guard has an unexpected shape`, change it to `The saved start guard couldn't be read`.

In `tests/test_coordinator.py`, in `test_failed_setup_car_read_keeps_a_stop_asked`, the stored data is compared after a failed setup, so it must already be in the new shape (an old file is migrated and saved back). Replace the `stored = {...}` and `hass_storage[key] = ...` lines with:

```text
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
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/test_charge_control.py -q -k "stored_shape or corrupt or missing_store or block_reason or unexpected_start"`
Expected: FAIL. `test_stored_shape` fails on the missing `minor_version`, the block-reason tests on the old loader refusing the new keys' absence of `stop_asked` (the control blocks with `start_blocked_store`), `test_unexpected_start_error…` on `RuntimeError` escaping.

- [ ] **Step 3: Move the control onto the store module**

In `custom_components/nortec_go/charge_control.py`:

1. Imports: remove `from homeassistant.helpers.storage import Store`, and `CHARGE_CONTROL_STORE_KEY` and `CHARGE_CONTROL_STORE_VERSION` from the `.const` import. Add:

```python
from .charge_control_store import (
    ChargeControlStore,
    StoredControl,
    UnreadableStoreError,
)
```

2. Delete the module-level functions `_parse_time`, `_parse_bool` and `_store`.

3. Replace `async_remove_charge_control`'s first line with:

```text
    await ChargeControlStore(hass, entry_id).async_remove()
```

4. In `__init__`, replace `self._store = _store(hass, entry.entry_id)` and the `self._stop_asked = False` line with:

```text
        self._store = ChargeControlStore(hass, entry.entry_id)
```

```text
        self._block_reason: str | None = None
        self._stop_asked_since: datetime | None = None
        # Carried from the load to the save here; the stop's tries are Task 4's.
        self._stop_tries = 0
        self._stop_tried_at: datetime | None = None
```

5. In the `state` property: `stop_asked=self._stop_asked_since is not None,`.

6. Replace `async_load` with:

```text
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
        pending_since = stored.start_pending_since
        if pending_since is not None:
            self._stop_asked_since = stored.stop_asked_since
            left = START_CONFIRM_TIMEOUT - (dt_util.utcnow() - pending_since)
            self._set_start_pending(
                pending_since, min(max(left, START_LOAD_GRACE), START_CONFIRM_TIMEOUT)
            )
        if stored.block_reason is not None:
            self._create_issue(stored.block_reason)
```

7. Every other use of `self._stop_asked`, one for one:
   - `async_start`, during a pending start: `if self._stop_asked_since is not None:` then `self._stop_asked_since = None`.
   - `async_start`, after `self._set_start_pending(dt_util.utcnow())`: `self._stop_asked_since = None`.
   - `async_stop`: `if self._stop_asked_since is None:` then `self._stop_asked_since = dt_util.utcnow()`.
   - `on_charger_read`: `if self._stop_asked_since is not None and charge_is_open(charger):`.
   - `_end_start_pending`: `self._stop_asked_since = None`.

8. `_set_block` and `_clear_block` keep the reason:

```text
    def _set_block(self, issue_key: str) -> None:
        self._blocked_since = dt_util.utcnow()
        self._block_reason = issue_key
        self._remembered = None
        self._create_issue(issue_key)
```

In `_clear_block`, add `self._block_reason = None` after `self._blocked_since = None`.

9. Replace `_save` and `_data_to_save`, and the save in `async_shutdown`:

```text
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
```

In `async_shutdown`: `await self._store.async_save(self._stored())`.

- [ ] **Step 4: Translate an unexpected start exception**

In `async_start`, add a last `except` after the `except NortecGoError as err:` block. `asyncio.CancelledError` is not an `Exception`, so the cancellation branch above keeps its block:

```text
            except Exception:
                # Not the client's own error, so nothing after the payment request raised it:
                # the client wraps all of that in ChargeStartError. No hold, so no block.
                _LOGGER.exception("Unexpected error while starting a charge")
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="start_failed"
                ) from None
```

- [ ] **Step 5: The store issue's text**

In `strings.json` and `translations/en.json`, set `issues.start_blocked_store.fix_flow.step.confirm.description` to the text in *Global Constraints* (one sentence added: `A stop you asked for earlier may not have been sent.`).

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/test_charge_control.py tests/test_coordinator.py tests/test_init.py tests/test_repairs.py -q`
Expected: all pass. The tests that put an old-format file in `hass_storage` (no `minor_version`) still pass: the file is migrated on load.

Then `uv run pytest -q`: all pass.

- [ ] **Step 7: Gates and commit**

Run the gates. Write the message to `/tmp/stop-safety-task-3-msg.txt`:

```text
fix: the start guard fails safe on a corrupt store, keeps the block's reason, and translates an unexpected start error (#26)

The charge control now keeps its state through charge_control_store. A store
file that existed and loads as nothing blocks starts, the block's reason is
stored so the repair issue has the right text after a restart, and an
exception that isn't the client's own is raised as start_failed, without a
block. The stop behaves as before.
```

```bash
git add custom_components/nortec_go/charge_control.py custom_components/nortec_go/strings.json custom_components/nortec_go/translations/en.json tests/test_charge_control.py tests/test_coordinator.py
git commit -F /tmp/stop-safety-task-3-msg.txt
```

---

### Task 4: The stored stop: tried from a turn-off or a read, ended only by a read

**Model:** opus — charge stop: when `stop_charge()` is called, and what ends a stop.
**Wave:** 3

**Files:**
- Modify: `custom_components/nortec_go/charge_control.py`
- Modify: `tests/conftest.py` (`make_charger` gets `can_stop`)
- Modify: `tests/test_charge_control.py`
- Modify: `tests/test_coordinator.py` (`test_pending_stop_during_an_outage_ends_at_2_minutes`)

**Interfaces:**
- Consumes: Task 3's fields (`_stop_asked_since`, `_stop_tries`, `_stop_tried_at`, `_stored()`), Task 1's `STOP_MAX_TRIES`.
- Produces, for Task 5:
  - module functions `is_stoppable(charger: Charger) -> bool` and `is_charge_off(charger: Charger) -> bool`;
  - `ChargeControl._clear_stop() -> None`, `_may_try() -> bool`, `_set_wait(delay: timedelta = STOP_CONFIRM_TIMEOUT) -> None`, `_async_wait_due(tried_at: datetime | None) -> None`, `_async_try_stop(*, from_turn_off: bool) -> None`, the field `_wait_timer`;
  - the timer job name `nortec_go stop wait`;
  - `make_charger(..., can_stop: bool = True)`.

**What this task leaves to Task 5:** giving up. Here a stop that has used its 10 tries simply gets no more calls, and nothing ends a stop after 30 minutes. The repair issue, the 30-minute timer, the read interval and the removal of the two unused translations are Task 5's.

The rules, from spec §1 (read it):
- **Stored:** a turn-off stores the stop (`_stop_asked_since`), unless a pending stop is under way or the last read shows `STOPPING`. A stop that is already stored keeps its time and its count.
- **A try** is one `stop_charge()` call. It may be made only when a stop is stored, the control is open, no start is pending, no pending stop is under way, no try is queued or in flight, the wait is over, and fewer than 10 tries were made.
- **The wait** runs from when a try is queued until 2 minutes after its answer. It belongs to the control: it runs on when its stop is done or cleared, and it is restored at load from `stop_tried_at`.
- **Only a read ends a stop as done:** a read that isn't stale, with no start pending, that shows the charge off. `NoActiveChargeError` doesn't.
- **A stale read** changes nothing: not the stop, not the pending stop.
- **An accepted try** starts the pending stop (D29). If the wait's timer finds it still pending, the try has failed.
- **A turn-on** that isn't refused clears the stop.

Facts you need:
- `entry.async_create_background_task` starts its task eagerly: it runs inside `on_charger_read` up to its first real suspension. With the mocked client an `await client.stop_charge()` doesn't suspend, so in tests a queued try has usually finished when `on_charger_read` returns. Tests that need a try in flight give `stop_charge` a side effect that waits on an `asyncio.Event`.
- `_fire(hass, freezer, delta)` in the test file moves time on, fires the due timers and waits for their background work.
- A read is stale when its `start_attempts` argument differs from `control.start_attempts`; the tests pass `control.start_attempts - 1`.
- When a setup fails, Home Assistant first runs the entry's `async_on_unload` callbacks and then cancels the entry's background tasks. A stop call cancelled that way still runs its `finally`. So the callback must close the control, or that `finally` arms a wait timer on a control the next setup has replaced.

- [ ] **Step 1: `make_charger` gets `can_stop`**

In `tests/conftest.py`, add the keyword argument `can_stop: bool = True,` after `charge_id` in `make_charger`'s signature, and pass `can_stop=can_stop,` to `ActiveCharge` in place of `can_stop=True,`.

- [ ] **Step 2: Write the failing tests**

In `tests/test_charge_control.py`:

**Imports and constants.** `ApiError` is already imported. Add `STOP_MAX_TRIES` to the `.const` import, and `is_charge_off` and `is_stoppable` to the `charge_control` import. Replace the `STOP_PENDING` constant and add two:

```python
STOP_ASKED_ONLY = ChargeControlState(stop_asked=True)
STOP_PENDING = ChargeControlState(stop_asked=True, stop_pending=True)
NOT_STOPPABLE = make_charger(
    is_connected=True,
    charge_state=ChargeState.STARTING,
    state=ChargerState.BUSY,
    can_stop=False,
)
```

Add a helper next to `_fire`:

```python
async def _saved(
    hass: HomeAssistant, entry: MockConfigEntry, hass_storage: dict[str, Any]
) -> dict[str, Any]:
    """The stored data, once a delayed save has landed."""
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    data: dict[str, Any] = hass_storage[STORE_KEY.format(entry.entry_id)]["data"]
    return data
```

**Delete** these tests; the tests below replace them:
- `test_stop_during_pending_start`
- `test_stop_asked_ends_with_the_timeout`
- `test_stop_not_stoppable_error`
- `test_stop_connection_error_asks_for_a_read`
- `test_stop_without_success_sets_no_pending_stop`
- `test_pending_stop_ends_on_a_stale_read_without_the_charge_on`
- `test_pending_stop_times_out_without_a_read`
- `test_background_stop_shows_off_at_once`
- `test_background_stop_without_success_ends_pending_stop`
- `test_stored_shape` (from Task 3)
- `test_stop_with_a_pending_start_and_a_charge_seen`
- `test_background_stop_error_is_logged`
- `test_start_timer_waits_for_a_stop_in_flight`: it had a stop call in flight while a start was pending, which can't happen any more.

**Change** these tests:
- `test_stop_auth_error_starts_reauth`: add `assert control.state == STOP_ASKED_ONLY` at the end.
- `test_read_without_the_charge_ends_the_stop_timer`, `test_stop_timer_does_nothing_after_shutdown`, `test_stop_timer_after_the_stop_ended_does_nothing`: replace `"No stop seen within"` with `"Stopping the charge failed"`.
- `test_background_stop_leaves_one_stop_timer`: the timer's name is `f"{DOMAIN} stop wait"`, and the counted text is `"Stopping the charge failed"`.

**Add** these tests:

```python
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
    """A failed call raises nothing, logs its number, keeps the stop, and the next call waits 2 minutes."""
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
    request_refresh.assert_not_awaited()

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
    """ "No active charge" is no evidence: the stop stays until a read decides (D50)."""
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


async def test_no_call_after_10_tries(
    hass: HomeAssistant,
    control: ChargeControl,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The 10th call is the last one for a stop asked."""
    control.on_charger_read(CHARGING, control.start_attempts)
    client.stop_charge.side_effect = ChargeNotStoppableError("x")
    await control.async_stop()
    for _ in range(STOP_MAX_TRIES + 2):
        await _fire(hass, freezer, STOP_CONFIRM_TIMEOUT)
        control.on_charger_read(CHARGING, control.start_attempts)
        await hass.async_block_till_done(wait_background_tasks=True)
    assert client.stop_charge.await_count == STOP_MAX_TRIES
    client.start_charge.assert_not_awaited()
```

In `tests/test_coordinator.py`, in `test_pending_stop_during_an_outage_ends_at_2_minutes`, the stop is now still stored after the 2 minutes, so the switch stays off. Change the docstring's "the switch shows the last read" to "the switch stays off while the stop is stored", and `assert _switch(hass) == "on"` to `assert _switch(hass) == "off"`. The interval assertion stays.

- [ ] **Step 3: Run the tests to see them fail**

Run: `uv run pytest tests/test_charge_control.py -q`
Expected: an import error on `is_charge_off` and `is_stoppable`.

- [ ] **Step 4: The helpers, the fields and the load**

In `custom_components/nortec_go/charge_control.py`:

1. Imports: remove `ChargeNotStoppableError` from the `pynortecgo` import (nothing names it any more; it is a `NortecGoError`). Add `STOP_MAX_TRIES` to the `.const` import.

2. After `_charge_happened`, add:

```python
_CHARGE_OVER = (ChargeState.STOPPING, ChargeState.COMPLETED)


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
```

3. In `__init__`: rename `self._stop_timer` to `self._wait_timer`, replace the Task 3 comment above `self._stop_tries` with `# The stop_charge() calls made for the stop asked, and the last call's time (D50).`, and add:

```text
        # A try is queued or in flight: no second one (D50).
        self._try_queued = False
```

4. In `async_load`, the stop is no longer tied to the pending start, and the wait is restored. Replace the lines from `pending_since = stored.start_pending_since` to the end of the method with:

```text
        self._stop_asked_since = stored.stop_asked_since
        if stored.stop_tried_at is not None:
            left = STOP_CONFIRM_TIMEOUT - (dt_util.utcnow() - stored.stop_tried_at)
            if left > timedelta(0):
                # Never more than the full wait: a stored time in the future is a clock change.
                self._set_wait(min(left, STOP_CONFIRM_TIMEOUT))
        pending_since = stored.start_pending_since
        if pending_since is not None:
            left = START_CONFIRM_TIMEOUT - (dt_util.utcnow() - pending_since)
            self._set_start_pending(
                pending_since, min(max(left, START_LOAD_GRACE), START_CONFIRM_TIMEOUT)
            )
        if stored.block_reason is not None:
            self._create_issue(stored.block_reason)
```

- [ ] **Step 5: The turn-on, the turn-off and the try**

1. In `async_start`, replace the lines from `if self._pending_since is not None:` to its `return` with:

```text
            if self._stop_asked_since is not None:
                # The owner asks for a charge: the stop is off, whatever the start then does (D50).
                self._clear_stop()
                self._changed()
            if self._pending_since is not None:
                return
```

and delete the line `self._stop_asked_since = None` after `self._set_start_pending(dt_util.utcnow())`.

2. Replace `async_stop`, `_async_send_stop` and `_async_background_stop` with:

```text
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
                self._stop_asked_since = dt_util.utcnow()
                self._changed()
            # A last read without a charge, or no read, still gets a call: the read may be old.
            waits_for_a_read = (
                charger is not None
                and charge_is_open(charger)
                and not is_charge_off(charger)
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

        Only a read ends the stop as done: the call's answer never does (D50).
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
        if accepted:
            self._stop_pending_since = self._stop_tried_at
        if rejected:
            self._entry.async_start_reauth(self._hass)
        if failed is None:
            self._request_read()
        else:
            _LOGGER.warning(
                "Stopping the charge failed (try %d of %d): %s",
                tries,
                STOP_MAX_TRIES,
                failed,
            )
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
```

- [ ] **Step 6: The read**

Replace `on_charger_read` with:

```text
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
        if self._stop_asked_since is not None and self._pending_since is None:
            if is_charge_off(charger):
                # Only a read ends a stop as done (D50).
                self._clear_stop()
                changed = True
            elif is_stoppable(charger) and self._may_try():
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
```

- [ ] **Step 7: The stop's end and the wait**

1. In `_end_start_pending`, delete the line `self._stop_asked_since = None`.

2. Delete `_clear_stop_pending`, `_set_stop_pending`, `_end_stop_pending`, `_async_stop_due` and `_cancel_stop_timer`, and add:

```text
    def _clear_stop(self) -> None:
        """End the stop asked for; the wait between two calls runs on (D50)."""
        self._stop_asked_since = None
        self._stop_tries = 0
        self._stop_pending_since = None

    def _set_wait(self, delay: timedelta = STOP_CONFIRM_TIMEOUT) -> None:
        """No stop call for `delay`; the timer then judges an accepted try (D29, D50)."""
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
            if self._stop_pending_since is None:
                return  # its stop is done or cleared, or the call wasn't accepted
            self._stop_pending_since = None
            _LOGGER.warning(
                "Stopping the charge failed (try %d of %d): %s",
                self._stop_tries,
                STOP_MAX_TRIES,
                f"the charge was still on {STOP_CONFIRM_TIMEOUT} after the charger"
                " accepted the stop",
            )
            self._on_change()

    def _cancel_wait_timer(self) -> None:
        if self._wait_timer is not None:
            self._wait_timer()
            self._wait_timer = None
```

3. In `_cancel_timers`, call `self._cancel_wait_timer()` in place of `self._cancel_stop_timer()`.

   In `_set_wait`, a closed control arms nothing. Add as its first lines, after the docstring:

```text
        if self._closed:
            return
```

   and in `__init__`, replace the comment and the line `entry.async_on_unload(self._cancel_timers)` with `entry.async_on_unload(self._async_close)`, and add the method next to `_cancel_timers`:

```text
    @callback
    def _async_close(self) -> None:
        """The entry is going: after an unload, or after a setup that failed.

        A setup that fails after async_load never calls async_shutdown, but runs this, and
        only then cancels a stop call in flight. Closing here keeps that call's end from
        arming a timer on a control the next setup has replaced (D50).
        """
        self._closed = True
        self._cancel_timers()
```

4. Update the module docstring's first line to name D50, and the class docstring if it describes the stop.

- [ ] **Step 8: Run the tests**

Run: `uv run pytest tests/test_charge_control.py -q`
Expected: all pass. If one of the kept tests fails, check it against spec §1 before changing it: a kept test that fails on a rule the spec didn't change is a bug in the code, not in the test.

Run: `uv run pytest -q`
Expected: all pass, `tests/test_switch.py` and `tests/test_coordinator.py` included.

- [ ] **Step 9: Gates and commit**

Run the gates. Write the message to `/tmp/stop-safety-task-4-msg.txt`:

```text
fix: a stop asked for is stored until a read shows the charge off (#85, #32, #26)

Turning Charge off stores the stop on its own, no longer tied to the pending
start. It is sent from the turn-off or from a read that shows the charge
stoppable, never during a pending start, to a stopping charge or to a charger
without a charge yet, and at most once per 2 minutes. Only a read ends it. A
failed call logs a warning and is tried again; a turn-off no longer raises
for it. Giving up after 10 tries or 30 minutes follows in the next commit.
```

```bash
git add custom_components/nortec_go/charge_control.py tests/conftest.py tests/test_charge_control.py tests/test_coordinator.py
git commit -F /tmp/stop-safety-task-4-msg.txt
```

---

### Task 5: The limits, giving up, the repair issue, the read interval, and the setup cases

**Model:** opus — charge stop: when the control stops trying, and what the owner is told.
**Wave:** 4

**Files:**
- Modify: `custom_components/nortec_go/charge_control.py`
- Modify: `custom_components/nortec_go/coordinator.py` (`interval_for`, and the comment on the setup's car read in `_async_update_data`)
- Modify: `custom_components/nortec_go/repairs.py` (`async_create_fix_flow`)
- Modify: `custom_components/nortec_go/strings.json` and `translations/en.json` (`issues.stop_failed` added; `exceptions.charge_not_stoppable` and `exceptions.stop_failed` removed)
- Modify: `tests/test_charge_control.py`, `tests/test_coordinator.py`, `tests/test_repairs.py`, `tests/test_init.py`

**Interfaces:**
- Consumes: Task 4's `_clear_stop`, `_may_try`, `_set_wait`, `_async_wait_due`, `_async_try_stop`, `is_charge_off`, `is_stoppable`; Task 1's `STOP_ASKED_MAX_AGE`, `STOP_MAX_TRIES`, `STOP_FAILED_ISSUE_ID`.
- Produces: the repair issue `stop_failed_<entry id>` with the translation key `stop_failed`; the timer job name `nortec_go stop limit`. Task 6 describes them.

The rules, from spec §1 *The limits* and §4:
- **Giving up** clears the stop (the wait runs on), logs an error, raises the repair issue and tells the coordinator, so the switch shows the charger's state again.
- **10 tries:** a failed call that was the 10th gives up at once. Otherwise a stop with 10 tries made gives up when the wait after the 10th has passed and the stop is still stored: an accepted 10th try, one answered "no active charge", and a stop loaded with 10 tries made (at once, if nothing is left of its wait).
- **30 minutes:** a timer from when the stop was asked, which fires whether or not the charger is read. At load it is set for what is left, never for more than 30 minutes; a stop already past it gives up at once.
- **The issue** is persistent and fixable with Home Assistant's `ConfirmRepairFlow`. It is deleted by a read that isn't stale and shows the charge off with no start pending (whether or not a stop is stored), by a turn-on that isn't refused, and with the entry. A turn-off doesn't delete it.
- **The timers' work** runs under the lock and checks that it still belongs to the same stop or the same wait.
- **The reads:** a stored stop gives 30 s reads while a start or a stop is pending or the last good read is under 2 minutes old, 5 minutes after that.

Facts you need:
- `ConfirmRepairFlow` is in `homeassistant.components.repairs`. It shows one `confirm` step with the issue's placeholders and does nothing else; finishing a fix flow deletes the issue.
- A persistent issue keeps its `data` and placeholders across a restart, so the fix flow still gets `entry_id`.
- `str(STOP_ASKED_MAX_AGE)` is `0:30:00`.
- At a failed setup Home Assistant runs the entry's `async_on_unload` callbacks, among them the control's `_cancel_timers`, and cancels the entry's background tasks.
- `mock_client.get_price_forecast` is the setup's price read; an `AuthError` from it fails the setup with `SETUP_ERROR`.

- [ ] **Step 1: Write the failing control tests**

In `tests/test_charge_control.py`, add `import logging`, `STOP_ASKED_MAX_AGE` to the `.const` import, and:

```python
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


@pytest.mark.parametrize("last", [None, NoActiveChargeError("x")])
async def test_gives_up_when_the_wait_after_the_10th_try_has_passed(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    last: Exception | None,
) -> None:
    """A 10th try that was accepted, or answered "no active charge", gives up 2 minutes later if the charge is still on."""
    await _fail_10_times(hass, control, client, freezer, last=last)
    assert control.state.stop_asked
    assert _stop_issue(hass, entry) is None
    await _fire(hass, freezer, STOP_CONFIRM_TIMEOUT)
    assert control.state == IDLE
    assert _stop_issue(hass, entry) is not None


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
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The 30 minutes hold with no read and no call: the charge never became stoppable."""
    control.on_charger_read(NOT_STOPPABLE, control.start_attempts)
    await control.async_stop()
    assert _timers(hass, f"{DOMAIN} stop limit") == 1
    await _fire(hass, freezer, STOP_ASKED_MAX_AGE - timedelta(seconds=1))
    assert control.state == STOP_ASKED_ONLY
    await _fire(hass, freezer, timedelta(seconds=1))
    assert control.state == IDLE
    assert (
        "Giving up on the stop asked for: it was asked for more than 0:30:00 ago"
        in caplog.text
    )
    assert _stop_issue(hass, entry) is not None
    client.stop_charge.assert_not_awaited()


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
    """A limit timer whose work waits for the lock while its stop ends doesn't give up a later stop."""
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


async def test_shutdown_cancels_the_stop_timers(
    hass: HomeAssistant, control: ChargeControl, client: AsyncMock
) -> None:
    """Unload, and a failed setup through the same callback, leave no stop timer behind."""
    control.on_charger_read(CHARGING, control.start_attempts)
    client.stop_charge.side_effect = ChargeNotStoppableError("x")
    await control.async_stop()
    assert _timers(hass, f"{DOMAIN} stop limit") == 1
    assert _timers(hass, f"{DOMAIN} stop wait") == 1
    await control.async_shutdown()
    assert _timers(hass, f"{DOMAIN} stop limit") == 0
    assert _timers(hass, f"{DOMAIN} stop wait") == 0


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
```

Delete `test_no_call_after_10_tries` from Task 4: `test_gives_up_after_the_10th_failed_call` covers it now, and its loop would meet the give-up.

- [ ] **Step 2: Write the failing interval, repair and setup tests**

In `tests/test_coordinator.py`, add these rows to the parameters of `test_interval_for`:

```text
        (
            make_charger(is_connected=True, charge_state=ChargeState.CHARGING),
            ChargeControlState(stop_asked=True),
            INTERVAL_CHANGING,
        ),
        (
            make_charger(is_connected=True, charge_state=ChargeState.PAUSED),
            ChargeControlState(stop_asked=True),
            INTERVAL_CHANGING,
        ),
        (
            make_charger(is_connected=True),
            ChargeControlState(blocked=True, stop_asked=True),
            INTERVAL_CHANGING,
        ),
```

and these to the parameters of `test_interval_for_by_read_age`:

```text
        (
            make_charger(is_connected=True, charge_state=ChargeState.CHARGING),
            ChargeControlState(stop_asked=True),
            timedelta(minutes=1, seconds=50),
            INTERVAL_CHANGING,
        ),
        (
            make_charger(is_connected=True, charge_state=ChargeState.CHARGING),
            ChargeControlState(stop_asked=True),
            timedelta(minutes=2),
            INTERVAL_CHARGING,
        ),
        (
            make_charger(is_connected=True, charge_state=ChargeState.CHARGING),
            ChargeControlState(stop_asked=True, stop_pending=True),
            timedelta(minutes=3),
            INTERVAL_CHANGING,
        ),
```

In `tests/test_repairs.py`, add `from datetime import timedelta`, `from homeassistant.util import dt as dt_util`, `ChargerState` to the `pynortecgo` import and `STOP_FAILED_ISSUE_ID` to the `.const` import, then:

```python
def _given_up(
    hass_storage: dict[str, Any], entry: MockConfigEntry, *, blocked: bool = False
) -> None:
    """A stored stop past its 30 minutes: the control gives up at load and raises the issue."""
    key = f"nortec_go.{entry.entry_id}.charge_control"
    hass_storage[key] = {
        "version": 1,
        "minor_version": 2,
        "key": key,
        "data": {
            "blocked_since": "2026-09-26T20:00:00+00:00" if blocked else None,
            "block_reason": "start_blocked" if blocked else None,
            "start_pending_since": None,
            "stop_asked_since": (dt_util.utcnow() - timedelta(minutes=31)).isoformat(),
            "stop_tries": 0,
            "stop_tried_at": None,
        },
    }


async def test_stop_failed_fix_dismisses_the_issue(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    hass_storage: dict[str, Any],
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
) -> None:
    """Confirming the stop notice dismisses it and calls nothing."""
    _given_up(hass_storage, mock_config_entry)
    mock_client.get_charger.return_value = make_charger(
        is_connected=True, charge_state=ChargeState.CHARGING
    )
    await setup_integration(hass, mock_config_entry)
    assert await async_setup_component(hass, "repairs", {})
    issue_id = STOP_FAILED_ISSUE_ID.format(entry_id=mock_config_entry.entry_id)
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None
    client = await hass_client()
    flow = await _start_fix(client, issue_id)
    assert flow["step_id"] == "confirm"
    resp = await client.post(f"/api/repairs/issues/fix/{flow['flow_id']}", json={})
    assert (await resp.json())["type"] == "create_entry"
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
    mock_client.stop_charge.assert_not_awaited()
    mock_client.start_charge.assert_not_awaited()


async def test_stop_failed_fix_leaves_a_start_block(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    hass_storage: dict[str, Any],
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
) -> None:
    """Confirming the stop notice while starts are blocked leaves the block and its issue in place."""
    _given_up(hass_storage, mock_config_entry, blocked=True)
    # An unknown charger state: neither "off", which would delete the notice, nor evidence
    # that clears the block.
    mock_client.get_charger.return_value = make_charger(
        is_connected=True, state=ChargerState.UNKNOWN
    )
    await setup_integration(hass, mock_config_entry)
    assert await async_setup_component(hass, "repairs", {})
    issue_id = STOP_FAILED_ISSUE_ID.format(entry_id=mock_config_entry.entry_id)
    client = await hass_client()
    flow = await _start_fix(client, issue_id)
    resp = await client.post(f"/api/repairs/issues/fix/{flow['flow_id']}", json={})
    assert (await resp.json())["type"] == "create_entry"
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
    assert mock_config_entry.runtime_data.data.control.blocked
    assert (
        ir.async_get(hass).async_get_issue(
            DOMAIN, f"start_blocked_{mock_config_entry.entry_id}"
        )
        is not None
    )
```

Add `ChargeState` to the same `pynortecgo` import if it isn't there.

In `tests/test_init.py`, add `AuthError`, `ChargeState` and `NortecGoConnectionError` to the `pynortecgo` import if they aren't there, `START_LOAD_GRACE` and `STOP_CONFIRM_TIMEOUT` to a `.const` import, and:

```python
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
    async_fire_time_changed(hass)  # a delayed save's timer
    await hass.async_block_till_done()
    stored = hass_storage[key]["data"]
    assert stored["start_pending_since"] is None  # the read saw the charge
    assert stored["stop_asked_since"] == now  # the stop is still asked
    assert stored["stop_tries"] == 1

    mock_client.stop_charge.side_effect = None
    mock_client.get_price_forecast.side_effect = None
    await hass.config_entries.async_reload(mock_config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert mock_config_entry.state is ConfigEntryState.LOADED
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
    await hass.config_entries.async_reload(mock_config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert mock_config_entry.state is ConfigEntryState.LOADED
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
```

- [ ] **Step 3: Run the tests to see them fail**

Run: `uv run pytest tests/test_charge_control.py tests/test_coordinator.py tests/test_repairs.py tests/test_init.py -q`
Expected: the new tests fail (no issue is raised, no `stop limit` timer exists, `interval_for` gives 5 minutes for a stored stop). `test_stop_survives_the_start_deadline_at_a_slow_setup` and `test_old_format_stop_is_sent_after_the_upgrade` may pass already: Task 4 fixed their cases, and they pin them at the setup level.

- [ ] **Step 4: Giving up, the limit timer and the issue**

In `custom_components/nortec_go/charge_control.py`:

1. Add `STOP_ASKED_MAX_AGE` and `STOP_FAILED_ISSUE_ID` to the `.const` import, and after `_CHARGE_OVER`:

```python
# Why the control gave up on a stop, for the log.
_NO_STOP_SEEN = f"no stop seen after {STOP_MAX_TRIES} tries"
_TOO_OLD = f"it was asked for more than {STOP_ASKED_MAX_AGE} ago"
```

2. `async_remove_charge_control` deletes the stop issue too. Add at its end:

```text
    ir.async_delete_issue(hass, DOMAIN, STOP_FAILED_ISSUE_ID.format(entry_id=entry_id))
```

3. In `__init__`, add `self._limit_timer: CALLBACK_TYPE | None = None` next to `self._wait_timer`.

4. In `async_load`, replace the line `self._stop_asked_since = stored.stop_asked_since` with nothing, and add after the wait block (the `if stored.stop_tried_at is not None:` block), before the pending start:

```text
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
```

5. In `async_start`, add after the `stop_pending` refusal and before the stop is cleared:

```text
            self._delete_stop_issue()
```

6. In `async_stop`, replace `self._stop_asked_since = dt_util.utcnow()` with `self._set_stop_asked(dt_util.utcnow())`.

7. In `_async_try_stop`, a failed 10th call gives up at once. Replace the `if failed is None:` block with:

```text
        if failed is None:
            self._request_read()
        else:
            _LOGGER.warning(
                "Stopping the charge failed (try %d of %d): %s",
                tries,
                STOP_MAX_TRIES,
                failed,
            )
            if tries >= STOP_MAX_TRIES:
                self._give_up(_NO_STOP_SEEN)
```

8. In `on_charger_read`, replace the stop's block (from `if self._stop_asked_since is not None and self._pending_since is None:` to the end of its `elif`) with:

```text
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
```

`_may_try` already refuses while a start is pending.

9. Replace `_clear_stop` and `_async_wait_due`, and add the rest:

```text
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

    def _cancel_limit_timer(self) -> None:
        if self._limit_timer is not None:
            self._limit_timer()
            self._limit_timer = None
```

10. In `_cancel_timers`, add `self._cancel_limit_timer()`.

- [ ] **Step 5: The read interval**

In `custom_components/nortec_go/coordinator.py`, replace the first `if` of `interval_for` and update its docstring:

```text
    """The next polling interval, from the charge status, a stop asked for and the last good read's age (D29, D31, D50)."""
    if control.stop_asked or charge_status(charger, control) in ("starting", "stopping"):
```

The two lines under it stay: a pending start or stop keeps 30 s, and otherwise only while the last good read is under 2 minutes old.

In `_async_update_data`, replace the two-line comment above the setup's car read with:

```text
            # The car first: a setup that fails on it must leave the charge control as loaded
            # (D44). A stop it had queued would be cancelled, and wait 2 minutes for its next try (D50).
```

- [ ] **Step 6: The fix flow**

In `custom_components/nortec_go/repairs.py`:

```python
from homeassistant.components.repairs import (
    ConfirmRepairFlow,
    RepairsFlow,
    RepairsFlowResult,
)
```

```python
from .const import CAR_GONE_ISSUE_ID, STOP_FAILED_ISSUE_ID
```

In `async_create_fix_flow`, add before the last `return`, and name the third issue in the docstring:

```text
    if issue_id == STOP_FAILED_ISSUE_ID.format(entry_id=entry_id):
        # Only a notice to dismiss: confirming it must never clear a start block.
        return ConfirmRepairFlow()
```

Update the module docstring to name the stop notice.

- [ ] **Step 7: The texts**

In `strings.json` and `translations/en.json`:

- Remove `exceptions.charge_not_stoppable` and `exceptions.stop_failed`.
- Add under `issues`, after `start_blocked_store`:

```json
"stop_failed": {
  "title": "A charge stop on {name} couldn't be confirmed",
  "fix_flow": {
    "step": {
      "confirm": {
        "title": "The charge on {name} may still be running",
        "description": "You turned Charge off, but Home Assistant couldn't stop the charge or see it stop, and has stopped trying. The charge may still be running.\n\nCheck the charger in the Nortec Go app and stop the charge there if needed. Turning Charge off again makes Home Assistant try again. Select **Submit** to dismiss this notice."
      }
    }
  }
},
```

- [ ] **Step 8: Run the tests**

Run: `uv run pytest tests/test_charge_control.py tests/test_coordinator.py tests/test_repairs.py tests/test_init.py -q`
Expected: all pass.

Run: `uv run pytest -q`
Expected: all pass. If a test elsewhere expects one of the two removed translations, it tested a path that no longer raises: check it against spec §1 *A try's outcome* and change it to the new behaviour.

- [ ] **Step 9: Gates and commit**

Run the gates. Write the message to `/tmp/stop-safety-task-5-msg.txt`:

```text
fix: a stop that can't be done ends in a repair issue after 10 tries or 30 minutes (#85, #32)

The control gives up on a stored stop after 10 stop calls or 30 minutes from
the turn-off, whichever is first, also across a restart: it logs an error,
raises a persistent repair issue and shows the charger's state again. The
issue goes when a read shows the charge off or Charge is turned on; a new
turn-off doesn't remove it. The charger is read every 30 s while a stop is
stored, within the outage limits.
```

```bash
git add custom_components/nortec_go/charge_control.py custom_components/nortec_go/coordinator.py custom_components/nortec_go/repairs.py custom_components/nortec_go/strings.json custom_components/nortec_go/translations/en.json tests/test_charge_control.py tests/test_coordinator.py tests/test_repairs.py tests/test_init.py
git commit -F /tmp/stop-safety-task-5-msg.txt
```

---

### Task 6: User docs, D50, the CHANGELOG and the quality scale comments

**Model:** opus — a docs task (D33).
**Wave:** 4 (started ahead of its input, Task 5, from the names this plan fixes; held until Task 5 is on the feature branch, then re-checked against that code and only then picked: `docs/way-of-working.md` §1, *Starting ahead of inputs*)

**Files:**
- Modify: `docs/user/nortec_go.md`
- Modify: `docs/decisions.md`
- Modify: `docs/manual-testing.md`
- Modify: `CHANGELOG.md`
- Modify: `custom_components/nortec_go/quality_scale.yaml` (two comments)

**Interfaces:**
- Consumes: the names in *Global Constraints*; the behaviour in spec §1, §2, §4 and §5.
- Produces: D50 in `decisions.md`.

Write for a Home Assistant user: what they see and what to do, not how the code does it. Follow `docs/way-of-working.md` §7: each fact in one place.

- [ ] **Step 1: The user docs**

In `docs/user/nortec_go.md`:

1. *Starting a charge*: replace the last paragraph (from "After you turn *Charge* off, it shows off for up to 2 minutes" to "is refused.") with:

```markdown
After you turn *Charge* off, the switch shows off until Home Assistant has seen the charge stop. It sends
the stop when the charger says the charge can be stopped, so a turn-off right after a start waits for the
charge to open. *Charge status* shows *Stopping* for up to 2 minutes after the charger has accepted a stop,
and turning *Charge* on in that time is refused.

If a stop fails, or the charge is still running 2 minutes after the charger accepted it, Home Assistant
tries again, at most once every 2 minutes. After 10 tries, or 30 minutes after you turned *Charge* off,
it gives up: the switch shows the charger's state again, and a repair issue tells you that the charge may
still be running (see *Troubleshooting*). Turning *Charge* on cancels a stop that hasn't gone through.

A stop also holds across a restart of Home Assistant, within the same 30 minutes.
```

2. *Data updates*: replace the first list item and the paragraph under the list with:

```markdown
- every 30 seconds while a charge is starting or stopping, including right after you turn *Charge* on or
  off, and while a stop you asked for hasn't gone through,
```

```markdown
While the charger can't be read, the 30-second reads stop after about 2 minutes, or about 10 minutes after
you turn *Charge* on. Reads then come every 5 minutes while a stop is waiting.
```

3. *Known limitations*: add after the item on a hold that led to no charge:

```markdown
- A stop is given up after 10 tries or 30 minutes. A stop you asked for more than 30 minutes before Home
  Assistant came back from a restart or an outage is not sent; a repair issue tells you instead.
- A stop that is waiting is sent to whatever charge is open. If the charge it was meant for has ended and
  another one was started outside Home Assistant in the same 30 minutes, that one is stopped.
- If Home Assistant can't read its saved start guard, a stop that was waiting is lost with it.
```

4. *Troubleshooting*: add after *Asked to sign in again*:

```markdown
### Changing the sign-in

To sign in with another email or a new password, open the integration's page, select the three dots next
to the entry and choose **Reconfigure**. You must sign in to the account that has the same charger;
another charger is refused. The entities and their history are kept.
```

and after *"Starts are blocked"*:

```markdown
### "A charge stop … couldn't be confirmed"

You turned *Charge* off, and Home Assistant couldn't stop the charge or see it stop within 10 tries or 30
minutes. The charge may still be running. Check the charger in the Nortec Go app and stop the charge there
if needed. Turning *Charge* off again makes Home Assistant try again. The notice goes away by itself when
Home Assistant sees that no charge is running, or when you turn *Charge* on.
```

5. In *Starting a charge*, the paragraph "Starts are also blocked, to be safe, if Home Assistant can't read its saved start guard." gets one more sentence: `That also happens when the saved file is damaged.`

- [ ] **Step 2: D50 and D29's status**

In `docs/decisions.md`, change D29's status line to:

```markdown
- **Date:** 2026-09-27 · **Status:** active; the 30 s reads while the charger can't be read superseded by D31; what ends the pending stop, what follows the 2 minutes, and the reads while a stop is stored, superseded by D50
```

and add at the end of the file:

```markdown
### D50: A stop is stored until the charge is seen off
- **Date:** 2026-10-02 · **Status:** active
- **Decision:** Turning *Charge* off stores the stop until a read shows the charge off (stopping,
  completed, or not open on a charger whose state is known), or *Charge* is turned on. Meanwhile the stop
  is sent, at the turn-off or when a read shows the charge stoppable, never to a charge that is stopping
  and never while a start is pending, with at least 2 minutes between two stop calls; a try fails when the
  call fails or when the charge is still on 2 minutes after the charger accepted it. A failed try raises
  no error (a rejected session aside). After 10 tries or 30 minutes from the ask, whichever is first, the
  control gives up, logs an error and raises a repair issue that a new turn-off doesn't remove. The
  charger is read every 30 s while a stop is stored, within D31's limits. A start is still never retried.
- **Why:** A stop tied to the pending start was lost whenever that ended first (#85, #32, #26), and an
  unattended stop from EV Smart Charging must actually stop the car. The stop isn't tied to one charge, so
  its age bounds the chance of stopping a later one.
- **Source:** [stop safety spec](superpowers/specs/2026-10-02-stop-safety-reconfigure-design.md),
  Decisions and §1
```

Match the blank lines and the wrap of the entries above it. Before committing, check that no entry on the feature branch already uses D50 (`grep -n '^### D50' docs/decisions.md`); if one does, stop and report it.

- [ ] **Step 3: The manual testing guide**

In `docs/manual-testing.md`, *Setup and restart*, add after the reauthentication item:

```markdown
- [ ] **Owner** Reconfigure, only when the sign-in really has to change: every submit signs in. The
  automated tests cover its errors.
```

and in *Start and stop*, add after the "Stop" item:

```markdown
- [ ] A stop that doesn't go through, and its repair issue, are checked only if one happens; there is no
  way here to cause one.
```

- [ ] **Step 4: The CHANGELOG**

In `CHANGELOG.md`, under `## [Unreleased]`:

```markdown
### Added

- Reconfigure: change the account's email or password from the integration's page, without removing the
  integration. The account must have the same charger.

### Changed

- Turning *Charge* off now holds until the charge is seen to stop. A stop that fails is tried again, at
  most once every 2 minutes, instead of raising an error. After 10 tries or 30 minutes a repair issue tells
  you that the charge may still be running.
- The charger is read every 30 seconds while a stop is waiting.

### Fixed

- A stop asked for right after a start could be lost: at a restart, at a reload, when the start took too
  long to show, or when the charger refused the stop. The car then kept charging.
- A stop is no longer sent to a charger that is busy but has no charge yet.
- A damaged saved start guard now blocks starts, to be safe, instead of being read as "nothing saved".
- The repair issue for blocked starts keeps the right text after a restart.
```

- [ ] **Step 5: The quality scale comments**

In `custom_components/nortec_go/quality_scale.yaml`:

```yaml
  appropriate-polling:
    status: done
    comment: "30 s only while a charge is starting or stopping or a stop asked for hasn't gone through (at most 30 minutes per stop, D50), bounded while reads fail (10 min after a start, 2 min after a stop or the last good read); 5 min while charging, 60 min otherwise (D29, D31)."
```

```yaml
  action-exceptions:
    status: done
    comment: "Turning Charge on and the Refresh button raise translated errors when their action fails. A turn-off that can't stop the charge is tried again and ends in a repair issue (D50); it raises only for a rejected session or while the integration reloads."
```

- [ ] **Step 6: Check and commit**

Run: `uv run pytest tests/test_quality_scale.py -q` (the comments are still there and the rule count is 54), then the gates: the pre-commit hooks reformat Markdown code blocks, so run `uv run pre-commit run --files docs/user/nortec_go.md docs/decisions.md docs/manual-testing.md CHANGELOG.md custom_components/nortec_go/quality_scale.yaml` and commit what they leave.

Write the message to `/tmp/stop-safety-task-6-msg.txt`:

```text
docs: the stored stop, reconfigure and D50 (#85, #32, #26, #44)

The user docs describe what a turn-off now does, its repair issue and the
reconfigure step; D50 records the decision and D29 names what it replaces.
```

```bash
git add docs/user/nortec_go.md docs/decisions.md docs/manual-testing.md CHANGELOG.md custom_components/nortec_go/quality_scale.yaml
git commit -F /tmp/stop-safety-task-6-msg.txt
```

**When this task is re-checked against Task 5's code** (it started ahead of it): the issue's title and the 10 tries, 2 minutes and 30 minutes in the docs match `strings.json` and `const.py`; the repair issue's ways of going away match `on_charger_read` and `async_start`.

---

## After the last task (controller)

- Learnings (way-of-working §1 step 8): candidates are the `Store` corrupt-file behaviour and the minor-version migration for `docs/ha-notes.md`, if they aren't there yet.
- Branch review with `full-reviewer`, then `scripts/smoke`, the bump step (`feat`: a minor release) and the PR description, with one `Closes #n` line each for #85, #32, #26 and #44. The PR is the owner's to merge: it is near charge stop and auth.
