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
