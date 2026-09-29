"""Price slots: merge, prune, EV Smart Charging's day lists, and their storage."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta, tzinfo
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from pynortecgo import PriceForecast

from .const import (
    MISSING_SLOT_PRICE,
    PAST_SLOT_PRICE,
    PRICE_STORE_KEY,
    PRICE_STORE_VERSION,
    SLOT_LENGTH,
)

_LOGGER = logging.getLogger(__name__)

type KnownSlots = dict[datetime, float]
"""Slot start (UTC) to price."""


@dataclass(frozen=True)
class StoredPrices:
    """The known slots and the prices' currency, as stored."""

    slots: KnownSlots
    currency: str | None


def merge_forecast(
    known: Mapping[datetime, float], forecast: PriceForecast
) -> KnownSlots:
    """Return the known slots with the forecast's slots written over them."""
    merged = dict(known)
    for slot in forecast.slots:
        merged[slot.start.astimezone(UTC)] = slot.price
    return merged


def _local_midnight(now: datetime, time_zone: tzinfo, days: int = 0) -> datetime:
    """Local midnight at the start of now's local day plus days, in UTC."""
    day = now.astimezone(time_zone).date() + timedelta(days=days)
    return datetime.combine(day, time(0), tzinfo=time_zone).astimezone(UTC)


def _day_starts(now: datetime, time_zone: tzinfo, days: int) -> list[datetime]:
    """Every slot start (UTC) of a local day: 96, or 92/100 on DST days."""
    start = _local_midnight(now, time_zone, days)
    end = _local_midnight(now, time_zone, days + 1)
    starts = []
    while start < end:
        starts.append(start)
        start += SLOT_LENGTH
    return starts


def prune(
    known: Mapping[datetime, float], now: datetime, time_zone: tzinfo
) -> KnownSlots:
    """Drop the slots that start before today's local midnight."""
    today = _local_midnight(now, time_zone)
    return {start: price for start, price in known.items() if start >= today}


def prices_today(
    known: Mapping[datetime, float], now: datetime, time_zone: tzinfo
) -> list[dict[str, Any]]:
    """Today's full day for EV Smart Charging, padded (D23)."""
    today = []
    for start in _day_starts(now, time_zone, 0):
        price = known.get(start)
        if price is None:
            price = (
                PAST_SLOT_PRICE if start + SLOT_LENGTH <= now else MISSING_SLOT_PRICE
            )
        today.append({"time": start.astimezone(time_zone), "price": price})
    return today


def prices_tomorrow(
    known: Mapping[datetime, float], now: datetime, time_zone: tzinfo
) -> list[dict[str, Any]]:
    """Tomorrow's full day, gaps padded, or [] when no slot of tomorrow is known."""
    starts = _day_starts(now, time_zone, 1)
    if not any(start in known for start in starts):
        return []
    return [
        {
            "time": start.astimezone(time_zone),
            "price": known.get(start, MISSING_SLOT_PRICE),
        }
        for start in starts
    ]


def current_price(known: Mapping[datetime, float], now: datetime) -> float | None:
    """The known price of the slot that holds now, or None."""
    now = now.astimezone(UTC)
    slot = now.replace(minute=now.minute - now.minute % 15, second=0, microsecond=0)
    return known.get(slot)


def _parse_start(value: str) -> datetime:
    """A stored slot start as UTC; raises ValueError without a time zone."""
    start = datetime.fromisoformat(value)
    if start.tzinfo is None:
        raise ValueError("slot start without a time zone")
    return start.astimezone(UTC)


def _parse_currency(value: object) -> str | None:
    """A stored currency code, or None; raises TypeError on a wrong shape."""
    if value is not None and not isinstance(value, str):
        raise TypeError("currency is not a string")
    return value


class _PriceData(Store[dict[str, Any]]):
    """The price store file, with its migration."""

    async def _async_migrate_func(
        self,
        old_major_version: int,
        old_minor_version: int,
        old_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Version 1 held spot prices: drop them, as they can't be mixed with totals (D34)."""
        # Version 1 is the only older version; a version 3 must branch on old_major_version.
        return {"currency": None, "slots": []}


class PriceStore:
    """The known slots of one config entry, in Home Assistant's storage."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Use the store file of this entry."""
        self._store: _PriceData = _PriceData(
            hass, PRICE_STORE_VERSION, PRICE_STORE_KEY.format(entry_id=entry_id)
        )

    async def async_load(self) -> StoredPrices:
        """Load the saved slots and currency; none if the file is missing or of the wrong shape."""
        data = await self._store.async_load()
        if data is None:
            return StoredPrices({}, None)
        try:
            currency = _parse_currency(data["currency"])
            known: KnownSlots = {}
            for item in data["slots"]:
                known[_parse_start(item["start"])] = float(item["price"])
        except KeyError, TypeError, ValueError:
            _LOGGER.warning("Ignoring the stored prices: they have an unexpected shape")
            return StoredPrices({}, None)
        return StoredPrices(known, currency)

    async def async_save(
        self, known: Mapping[datetime, float], currency: str | None
    ) -> None:
        """Save the slots, sorted by start, and the currency."""
        await self._store.async_save(
            {
                "currency": currency,
                "slots": [
                    {"start": start.isoformat(), "price": price}
                    for start, price in sorted(known.items())
                ],
            }
        )

    async def async_remove(self) -> None:
        """Delete the store file."""
        await self._store.async_remove()
