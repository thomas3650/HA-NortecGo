"""Total energy: a stored ledger of the energy the charger delivered, summed per charge (D47).

Each completed charge counts once, by its charge ID, and the open charge counts at its live
reading. The total never goes down.
"""

from dataclasses import dataclass, replace
from datetime import UTC, datetime
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from pynortecgo import Charger

from .const import ENERGY_STORE_KEY, ENERGY_STORE_VERSION

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProvisionalCharge:
    """A charge counted at its highest live reading, waiting for its final record.

    seen_at is when it was last seen open.
    """

    id: str
    kwh: float
    seen_at: datetime


@dataclass(frozen=True)
class EnergyLedger:
    """What Total energy is summed from.

    since is when the ledger was created: a charge completed at or before it is never counted as
    a completed charge. settled_kwh is the sum of the charges that are done with; settled_id and
    settled_at are the last completed charge counted. provisional holds the charges still counted
    at their live reading, in the order they were first seen.
    """

    since: datetime
    settled_kwh: float
    settled_id: str | None
    settled_at: datetime | None
    provisional: tuple[ProvisionalCharge, ...]


def new_ledger(now: datetime) -> EnergyLedger:
    """A ledger that has counted nothing yet."""
    return EnergyLedger(
        since=now, settled_kwh=0.0, settled_id=None, settled_at=None, provisional=()
    )


def total_kwh(ledger: EnergyLedger) -> float:
    """The energy counted so far."""
    return ledger.settled_kwh + sum(charge.kwh for charge in ledger.provisional)


def advance(ledger: EnergyLedger, charger: Charger, now: datetime) -> EnergyLedger:
    """Count one charger read; returns the ledger itself when nothing changes."""
    settled_kwh = ledger.settled_kwh
    settled_id = ledger.settled_id
    settled_at = ledger.settled_at
    provisional = list(ledger.provisional)
    last = charger.last_charge
    active = charger.active_charge

    # 1. The completed charge, once: by its ID, and only if it completed after the last one
    # counted (or after the ledger was created).
    if (
        last is not None
        and last.id != settled_id
        and last.completed_at > (settled_at or ledger.since)
    ):
        open_id = None if active is None else active.id
        final = last.kwh
        folded = 0.0
        waiting: list[ProvisionalCharge] = []
        for charge in provisional:
            if charge.id == last.id:
                # The final energy replaces the live reading, but the total doesn't go down.
                final = max(final, charge.kwh)
            elif charge.id != open_id and charge.seen_at < last.completed_at:
                # Open before this one completed, so older: its record can't arrive any more.
                folded += charge.kwh
            else:
                waiting.append(charge)
        settled_kwh += final + folded
        settled_id = last.id
        settled_at = last.completed_at
        provisional = waiting

    # 2. The open charge, at its highest reading, unless step 1 has counted it already.
    if active is not None and active.id != settled_id:
        for index, charge in enumerate(provisional):
            if charge.id == active.id:
                kwh = charge.kwh if active.kwh is None else max(charge.kwh, active.kwh)
                provisional[index] = replace(charge, kwh=kwh, seen_at=now)
                break
        else:
            kwh = 0.0 if active.kwh is None else active.kwh
            provisional.append(ProvisionalCharge(id=active.id, kwh=kwh, seen_at=now))

    advanced = EnergyLedger(
        since=ledger.since,
        settled_kwh=settled_kwh,
        settled_id=settled_id,
        settled_at=settled_at,
        provisional=tuple(provisional),
    )
    return ledger if advanced == ledger else advanced


def _parse_time(value: object) -> datetime:
    """A stored time as UTC; raises TypeError or ValueError on a wrong shape."""
    if not isinstance(value, str):
        raise TypeError("time is not a string")
    time = datetime.fromisoformat(value)
    if time.tzinfo is None:
        raise ValueError("time without a time zone")
    return time.astimezone(UTC)


def _parse_kwh(value: object) -> float:
    """A stored energy; raises TypeError on a wrong shape."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError("energy is not a number")
    return float(value)


def _parse_id(value: object) -> str:
    """A stored charge ID; raises TypeError on a wrong shape."""
    if not isinstance(value, str):
        raise TypeError("charge ID is not a string")
    return value


def _ledger_from(data: dict[str, Any]) -> EnergyLedger:
    """The stored ledger; raises KeyError, TypeError or ValueError on a wrong shape."""
    settled_id = data["settled_id"]
    settled_at = data["settled_at"]
    return EnergyLedger(
        since=_parse_time(data["since"]),
        settled_kwh=_parse_kwh(data["settled_kwh"]),
        settled_id=None if settled_id is None else _parse_id(settled_id),
        settled_at=None if settled_at is None else _parse_time(settled_at),
        provisional=tuple(
            ProvisionalCharge(
                id=_parse_id(item["id"]),
                kwh=_parse_kwh(item["kwh"]),
                seen_at=_parse_time(item["seen_at"]),
            )
            for item in data["provisional"]
        ),
    )


class EnergyStore:
    """The Total energy ledger of one config entry, in Home Assistant's storage."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Use the store file of this entry."""
        self._store: Store[dict[str, Any]] = Store(
            hass, ENERGY_STORE_VERSION, ENERGY_STORE_KEY.format(entry_id=entry_id)
        )

    async def async_load(self) -> EnergyLedger | None:
        """Load the saved ledger; None if the file is missing or of the wrong shape."""
        data = await self._store.async_load()
        if data is None:
            return None
        try:
            return _ledger_from(data)
        except KeyError, TypeError, ValueError:
            _LOGGER.warning(
                "Ignoring the stored energy total: it has an unexpected shape"
            )
            return None

    async def async_save(self, ledger: EnergyLedger) -> None:
        """Save the ledger."""
        await self._store.async_save(
            {
                "since": ledger.since.isoformat(),
                "settled_kwh": ledger.settled_kwh,
                "settled_id": ledger.settled_id,
                "settled_at": (
                    None if ledger.settled_at is None else ledger.settled_at.isoformat()
                ),
                "provisional": [
                    {
                        "id": charge.id,
                        "kwh": charge.kwh,
                        "seen_at": charge.seen_at.isoformat(),
                    }
                    for charge in ledger.provisional
                ],
            }
        )

    async def async_remove(self) -> None:
        """Delete the store file."""
        await self._store.async_remove()
