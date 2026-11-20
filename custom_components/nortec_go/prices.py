"""Price slots: merge, prune, the day lists, the price's parts, and their storage."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta, tzinfo
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from pynortecgo import PriceForecast

from .const import (
    MISSING_SLOT_PRICE,
    PAST_SLOT_PRICE,
    PRICE_READ_HOURS,
    PRICE_READ_MINUTE,
    PRICE_STORE_KEY,
    PRICE_STORE_VERSION,
    SLOT_LENGTH,
)

_LOGGER = logging.getLogger(__name__)

type KnownSlots = dict[datetime, float]
"""Slot start (UTC) to price."""


@dataclass(frozen=True)
class SlotSplit:
    """A slot's spot price, and whether its grid tariff is estimated."""

    spot: float
    tariff_estimated: bool


type KnownSplit = dict[datetime, SlotSplit]
"""Slot start (UTC) to its split."""


@dataclass(frozen=True)
class StoredPrices:
    """The known slots, the prices' currency and the known split, as stored."""

    slots: KnownSlots
    currency: str | None
    split: KnownSplit = field(default_factory=dict)


def merge_forecast(
    known: Mapping[datetime, float], forecast: PriceForecast
) -> KnownSlots:
    """Return the known slots with the forecast's slots written over them."""
    merged = dict(known)
    for slot in forecast.slots:
        merged[slot.start.astimezone(UTC)] = slot.price
    return merged


def merge_split(
    known: Mapping[datetime, SlotSplit], forecast: PriceForecast
) -> KnownSplit:
    """Return the known split with the forecast's slots written over it."""
    merged = dict(known)
    for slot in forecast.slots:
        merged[slot.start.astimezone(UTC)] = SlotSplit(
            slot.spot_price, slot.tariff_estimated
        )
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


def prune[T](
    known: Mapping[datetime, T], now: datetime, time_zone: tzinfo
) -> dict[datetime, T]:
    """Drop the slots that start before today's local midnight."""
    today = _local_midnight(now, time_zone)
    return {start: value for start, value in known.items() if start >= today}


def prices_today(
    known: Mapping[datetime, float], now: datetime, time_zone: tzinfo
) -> list[dict[str, Any]]:
    """Today's full day for EV Smart Charging, padded."""
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


def _split_day_starts(
    known: Mapping[datetime, float], now: datetime, time_zone: tzinfo, day: int
) -> list[datetime]:
    """The slot starts of today (0) or tomorrow (1); none for tomorrow without a known total."""
    starts = _day_starts(now, time_zone, day)
    if day == 1 and not any(start in known for start in starts):
        return []
    return starts


def _fees(
    split: Mapping[datetime, SlotSplit],
    known: Mapping[datetime, float],
    start: datetime,
) -> float | None:
    """A slot's total less its spot price, rounded to 4 decimals, or None."""
    if start in split and start in known:
        return round(known[start] - split[start].spot, 4)
    return None


def spot_prices(
    split: Mapping[datetime, SlotSplit],
    known: Mapping[datetime, float],
    now: datetime,
    time_zone: tzinfo,
    day: int,
) -> list[dict[str, Any]]:
    """A local day's spot price per slot, None where unknown; tomorrow [] as prices_tomorrow."""
    return [
        {
            "time": start.astimezone(time_zone),
            "price": split[start].spot if start in split else None,
        }
        for start in _split_day_starts(known, now, time_zone, day)
    ]


def fees_prices(
    split: Mapping[datetime, SlotSplit],
    known: Mapping[datetime, float],
    now: datetime,
    time_zone: tzinfo,
    day: int,
) -> list[dict[str, Any]]:
    """A local day's add-on and tariff flag per slot, None where unknown; tomorrow as spot_prices."""
    return [
        {
            "time": start.astimezone(time_zone),
            "price": _fees(split, known, start),
            "tariff_estimated": split[start].tariff_estimated
            if start in split and start in known
            else None,
        }
        for start in _split_day_starts(known, now, time_zone, day)
    ]


def _slot_holding(now: datetime) -> datetime:
    """The start (UTC) of the slot that holds now."""
    now = now.astimezone(UTC)
    return now.replace(minute=now.minute - now.minute % 15, second=0, microsecond=0)


def current_spot(split: Mapping[datetime, SlotSplit], now: datetime) -> float | None:
    """The spot price of the slot that holds now, or None."""
    slot = _slot_holding(now)
    return split[slot].spot if slot in split else None


def current_fees(
    split: Mapping[datetime, SlotSplit], known: Mapping[datetime, float], now: datetime
) -> float | None:
    """The add-on of the slot that holds now, rounded as in the list, or None."""
    return _fees(split, known, _slot_holding(now))


def _local_read_time(day: date, hour: int, time_zone: tzinfo) -> datetime:
    """A read time on a local day, in UTC; fold=0 on a repeated hour."""
    return datetime.combine(
        day, time(hour, PRICE_READ_MINUTE), tzinfo=time_zone
    ).astimezone(UTC)


def next_price_read(now: datetime, time_zone: tzinfo) -> datetime:
    """The first scheduled price read after now, in UTC."""
    today = now.astimezone(time_zone).date()
    for hour in PRICE_READ_HOURS:
        read = _local_read_time(today, hour, time_zone)
        if read > now:
            return read
    return _local_read_time(today + timedelta(days=1), PRICE_READ_HOURS[0], time_zone)


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


def _is_spot(value: object) -> bool:
    """Whether a stored spot price is a number (a bool is not)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _parse_split(items: list[Any], starts: list[datetime]) -> KnownSplit | None:
    """The stored split per slot, or None when a key holds a wrong type.

    A key that is present and not null is checked first, in every item. Only then
    does a missing or null key mean that slot has no split.
    """
    split: KnownSplit = {}
    for item, start in zip(items, starts, strict=True):
        spot = item.get("spot")
        estimated = item.get("tariff_estimated")
        if (spot is not None and not _is_spot(spot)) or (
            estimated is not None and not isinstance(estimated, bool)
        ):
            return None
        if spot is not None and estimated is not None:
            split[start] = SlotSplit(float(spot), estimated)
    return split


class _PriceData(Store[dict[str, Any]]):
    """The price store file, with its migration."""

    async def _async_migrate_func(
        self,
        old_major_version: int,
        old_minor_version: int,
        old_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Version 1 held spot prices: drop them, as they can't be mixed with totals."""
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
        """Load the saved slots, their split and the currency.

        A wrongly typed split drops only the split; the totals and the currency are
        kept. A missing file, or a wrong shape anywhere else, gives none.
        """
        data = await self._store.async_load()
        if data is None:
            return StoredPrices({}, None)
        try:
            currency = _parse_currency(data["currency"])
            known: KnownSlots = {}
            starts: list[datetime] = []
            for item in data["slots"]:
                start = _parse_start(item["start"])
                known[start] = float(item["price"])
                starts.append(start)
        except KeyError, TypeError, ValueError:
            _LOGGER.warning("Ignoring the stored prices: they have an unexpected shape")
            return StoredPrices({}, None)
        split = _parse_split(data["slots"], starts)
        if split is None:
            _LOGGER.warning(
                "Ignoring the stored spot prices: they have an unexpected shape"
            )
            split = {}
        return StoredPrices(known, currency, split)

    async def async_save(
        self,
        known: Mapping[datetime, float],
        currency: str | None,
        split: Mapping[datetime, SlotSplit],
    ) -> None:
        """Save the slots, sorted by start, each with its split or nulls, and the currency."""
        slots = []
        for start, price in sorted(known.items()):
            slot_split = split.get(start)
            slots.append(
                {
                    "start": start.isoformat(),
                    "price": price,
                    "spot": None if slot_split is None else slot_split.spot,
                    "tariff_estimated": None
                    if slot_split is None
                    else slot_split.tariff_estimated,
                }
            )
        await self._store.async_save({"currency": currency, "slots": slots})

    async def async_remove(self) -> None:
        """Delete the store file."""
        await self._store.async_remove()
