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
