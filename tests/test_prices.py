"""Tests for the price slot logic and its storage."""

from datetime import UTC, datetime, timedelta
from itertools import pairwise
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant
import pytest

from custom_components.nortec_go.const import MISSING_SLOT_PRICE, PAST_SLOT_PRICE
from custom_components.nortec_go.prices import (
    PriceStore,
    SlotSplit,
    StoredPrices,
    current_fees,
    current_price,
    current_spot,
    fees_prices,
    merge_forecast,
    merge_split,
    next_price_read,
    prices_today,
    prices_tomorrow,
    prune,
    spot_prices,
)

from .conftest import make_forecast

TZ = ZoneInfo("Europe/Copenhagen")
STEP = timedelta(minutes=15)
# 2026-09-27 00:00 local (CEST, UTC+2) is 2026-09-26 22:00 UTC.
MIDNIGHT = datetime(2026, 9, 26, 22, 0, tzinfo=UTC)
NOW = datetime(2026, 9, 27, 12, 7, tzinfo=UTC)  # 14:07 local
KEY = "nortec_go.entry1.prices"


def _slots(start: datetime, prices: list[float]) -> dict[datetime, float]:
    return {start + i * STEP: price for i, price in enumerate(prices)}


def test_merge_overwrites_and_adds() -> None:
    """A new forecast overwrites the slots it covers and keeps the others."""
    known = _slots(MIDNIGHT, [1.0, 2.0])
    merged = merge_forecast(known, make_forecast(MIDNIGHT + STEP, [5.0, 6.0]))
    assert merged == _slots(MIDNIGHT, [1.0, 5.0, 6.0])
    assert known == _slots(MIDNIGHT, [1.0, 2.0])  # input not changed


def test_merge_normalises_to_utc() -> None:
    """Slot starts from another offset become UTC keys."""
    local_start = MIDNIGHT.astimezone(TZ)
    merged = merge_forecast({}, make_forecast(local_start, [1.0]))
    (key,) = merged
    assert key.utcoffset() == timedelta(0)
    assert key == MIDNIGHT


def test_merge_stores_the_total_price() -> None:
    """A slot's total price is stored, not its spot price."""
    forecast = make_forecast(MIDNIGHT, [2.0])
    assert forecast.slots[0].spot_price != 2.0
    assert merge_forecast({}, forecast) == {MIDNIGHT: 2.0}


def test_prune_drops_before_local_midnight() -> None:
    """Slots before today's local midnight are dropped."""
    known = _slots(MIDNIGHT - STEP, [9.0, 1.0])
    assert prune(known, NOW, TZ) == {MIDNIGHT: 1.0}


def test_prices_today_full_day_with_padding() -> None:
    """96 slots in local time: known prices, 0 for missing past, 10 for missing current and future."""
    known = {MIDNIGHT: 1.5, NOW.replace(minute=15): 2.5}  # 00:00 and 14:15 local
    today = prices_today(known, NOW, TZ)
    assert len(today) == 96
    assert today[0] == {"time": MIDNIGHT.astimezone(TZ), "price": 1.5}
    assert today[1]["price"] == PAST_SLOT_PRICE  # 00:15, missing, past
    current = NOW.replace(minute=0)  # 14:00 local, the slot holding now
    assert today[56] == {"time": current.astimezone(TZ), "price": MISSING_SLOT_PRICE}
    assert today[57]["price"] == 2.5
    assert today[-1]["price"] == MISSING_SLOT_PRICE
    assert all(entry["time"].tzinfo == TZ for entry in today)
    times = [entry["time"] for entry in today]
    assert times == sorted(times)


def test_prices_today_padding_only() -> None:
    """With nothing known, today is still a full, valid day."""
    today = prices_today({}, NOW, TZ)
    assert len(today) == 96
    assert {entry["price"] for entry in today} == {PAST_SLOT_PRICE, MISSING_SLOT_PRICE}


def test_prices_tomorrow_empty_when_unknown() -> None:
    """No slot of tomorrow known: an empty list."""
    assert prices_tomorrow(_slots(MIDNIGHT, [1.0]), NOW, TZ) == []


def test_prices_tomorrow_padded_when_partly_known() -> None:
    """One known slot of tomorrow gives the full day, gaps at 10, after today's last entry."""
    tomorrow_start = MIDNIGHT + timedelta(days=1)
    tomorrow = prices_tomorrow({tomorrow_start + STEP: 3.0}, NOW, TZ)
    assert len(tomorrow) == 96
    assert tomorrow[0] == {
        "time": tomorrow_start.astimezone(TZ),
        "price": MISSING_SLOT_PRICE,
    }
    assert tomorrow[1]["price"] == 3.0
    assert prices_today({}, NOW, TZ)[-1]["time"] < tomorrow[0]["time"]


@pytest.mark.parametrize(
    ("now", "slots"),
    [
        (datetime(2026, 10, 25, 12, 0, tzinfo=UTC), 100),  # CEST -> CET, 25 hours
        (datetime(2026, 3, 29, 12, 0, tzinfo=UTC), 92),  # CET -> CEST, 23 hours
    ],
)
def test_dst_days(now: datetime, slots: int) -> None:
    """A DST day has 100 or 92 slots, in order, 15 minutes apart in UTC."""
    today = prices_today({}, now, TZ)
    assert len(today) == slots
    starts = [entry["time"].astimezone(UTC) for entry in today]
    assert all(b - a == STEP for a, b in pairwise(starts))


def test_current_price() -> None:
    """The known price of the slot holding now, or None."""
    slot = NOW.replace(minute=0)
    assert current_price({slot: 2.0}, NOW) == 2.0
    assert current_price({slot + STEP: 2.0}, NOW) is None


def test_merge_split_overwrites_and_adds() -> None:
    """A forecast writes its slots' spot prices and tariff flags over the known split."""
    known = {
        MIDNIGHT: SlotSplit(9.0, True),
        MIDNIGHT + 4 * STEP: SlotSplit(7.0, False),
    }
    forecast = make_forecast(
        MIDNIGHT, [2.0, 3.0], spot_prices=[1.2, 1.5], estimated=[False, True]
    )
    assert merge_split(known, forecast) == {
        MIDNIGHT: SlotSplit(1.2, False),
        MIDNIGHT + STEP: SlotSplit(1.5, True),
        MIDNIGHT + 4 * STEP: SlotSplit(7.0, False),
    }
    assert known[MIDNIGHT] == SlotSplit(9.0, True)  # input not changed
    assert merge_forecast({}, forecast) == {MIDNIGHT: 2.0, MIDNIGHT + STEP: 3.0}


def test_merge_split_normalises_to_utc() -> None:
    """Slot starts from another offset become UTC keys in the split too."""
    local_start = MIDNIGHT.astimezone(TZ)
    merged = merge_split({}, make_forecast(local_start, [1.0]))
    (key,) = merged
    assert key.utcoffset() == timedelta(0)
    assert key == MIDNIGHT


def test_prune_drops_split_before_local_midnight() -> None:
    """A split is pruned as the totals are."""
    split = {
        MIDNIGHT - STEP: SlotSplit(9.0, True),
        MIDNIGHT: SlotSplit(1.0, False),
    }
    assert prune(split, NOW, TZ) == {MIDNIGHT: SlotSplit(1.0, False)}


def test_spot_and_fees_lists_today() -> None:
    """Today's lists: the spot price and the add-on per slot, None where unknown."""
    known = _slots(MIDNIGHT, [2.0, 3.0])
    split = {
        MIDNIGHT: SlotSplit(1.2, True),
        MIDNIGHT + 2 * STEP: SlotSplit(0.7, False),  # a split, but no total
    }
    spot = spot_prices(split, known, NOW, TZ, day=0)
    assert len(spot) == 96
    assert spot[0] == {"time": MIDNIGHT.astimezone(TZ), "price": 1.2}
    assert spot[1] == {"time": (MIDNIGHT + STEP).astimezone(TZ), "price": None}
    assert spot[2]["price"] == 0.7
    fees = fees_prices(split, known, NOW, TZ, day=0)
    assert len(fees) == 96
    assert fees[0] == {
        "time": MIDNIGHT.astimezone(TZ),
        "price": 0.8,
        "tariff_estimated": True,
    }
    for item in fees[1:3]:
        assert item["price"] is None
        assert item["tariff_estimated"] is None
    assert [item["time"] for item in spot] == [item["time"] for item in fees]
    assert [item["time"] for item in spot] == [
        item["time"] for item in prices_today(known, NOW, TZ)
    ]


def test_split_lists_keep_false_and_zero() -> None:
    """A spot price of 0.0 and an exact tariff stay 0.0 and False, not None."""
    slot = NOW.replace(minute=0)  # the slot holding now, 14:00 local
    split = {slot: SlotSplit(0.0, False)}
    known = {slot: 0.5}
    assert spot_prices(split, known, NOW, TZ, day=0)[56]["price"] == 0.0
    fees = fees_prices(split, known, NOW, TZ, day=0)[56]
    assert fees["price"] == 0.5
    assert fees["tariff_estimated"] is False
    assert current_spot(split, NOW) == 0.0
    assert current_fees(split, known, NOW) == 0.5


def test_fees_rounded() -> None:
    """The add-on is rounded to 4 decimals, in the list and in the state."""
    slot = NOW.replace(minute=0)
    split = {slot: SlotSplit(1.1, False)}
    known = {slot: 2.0}
    assert fees_prices(split, known, NOW, TZ, day=0)[56]["price"] == 0.9
    assert current_fees(split, known, NOW) == 0.9


def test_split_tomorrow_empty_exactly_when_prices_tomorrow_is() -> None:
    """Tomorrow's lists are [] with no total of tomorrow, else a full day."""
    known = _slots(MIDNIGHT, [1.0])
    split = {MIDNIGHT: SlotSplit(0.5, False)}
    assert prices_tomorrow(known, NOW, TZ) == []
    assert spot_prices(split, known, NOW, TZ, day=1) == []
    assert fees_prices(split, known, NOW, TZ, day=1) == []

    tomorrow_start = MIDNIGHT + timedelta(days=1)
    known = {tomorrow_start + STEP: 3.0}
    spot = spot_prices({}, known, NOW, TZ, day=1)
    fees = fees_prices({}, known, NOW, TZ, day=1)
    assert len(spot) == len(fees) == 96
    assert spot[0]["time"] == tomorrow_start.astimezone(TZ)
    assert {item["price"] for item in spot} == {None}
    assert {item["price"] for item in fees} == {None}
    assert {item["tariff_estimated"] for item in fees} == {None}


def test_split_tomorrow_slot_with_total_and_split() -> None:
    """A slot of tomorrow with a total and a split shows its spot and rounded add-on."""
    slot = MIDNIGHT + timedelta(days=1) + 2 * STEP
    known = {slot: 3.0}
    split = {slot: SlotSplit(1.23456, True)}
    assert prices_tomorrow(known, NOW, TZ) != []
    spot = spot_prices(split, known, NOW, TZ, day=1)
    fees = fees_prices(split, known, NOW, TZ, day=1)
    assert len(spot) == len(fees) == 96
    assert spot[2] == {"time": slot.astimezone(TZ), "price": 1.23456}
    assert fees[2] == {
        "time": slot.astimezone(TZ),
        "price": 1.7654,
        "tariff_estimated": True,
    }
    assert spot[1]["price"] is None
    assert fees[1]["price"] is None
    assert fees[1]["tariff_estimated"] is None


@pytest.mark.parametrize(
    ("now", "slots"),
    [
        (datetime(2026, 10, 25, 12, 0, tzinfo=UTC), 100),  # CEST -> CET, 25 hours
        (datetime(2026, 3, 29, 12, 0, tzinfo=UTC), 92),  # CET -> CEST, 23 hours
    ],
)
def test_split_lists_dst_days(now: datetime, slots: int) -> None:
    """On a DST day both lists have 100 or 92 items, 15 minutes apart in UTC."""
    for items in (
        spot_prices({}, {}, now, TZ, day=0),
        fees_prices({}, {}, now, TZ, day=0),
    ):
        assert len(items) == slots
        starts = [item["time"].astimezone(UTC) for item in items]
        assert all(b - a == STEP for a, b in pairwise(starts))


def test_current_split() -> None:
    """The spot price and the add-on of the slot holding now, or None."""
    slot = NOW.replace(minute=0)
    split = {slot: SlotSplit(1.2, True), slot + STEP: SlotSplit(9.0, False)}
    known = {slot: 2.0, slot + STEP: 10.0}
    assert current_spot(split, NOW) == 1.2
    assert current_fees(split, known, NOW) == 0.8
    assert current_spot({}, NOW) is None
    assert current_fees({}, known, NOW) is None
    assert current_fees(split, {}, NOW) is None


async def test_store_round_trip(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Saved slots, split and currency load back, with UTC keys; remove deletes the file."""
    store = PriceStore(hass, "entry1")
    known = _slots(MIDNIGHT, [1.0, 2.0])
    split = {MIDNIGHT: SlotSplit(1.2, True)}
    await store.async_save(known, "DKK", split)
    assert hass_storage[KEY]["version"] == 2
    assert hass_storage[KEY]["minor_version"] == 1
    assert hass_storage[KEY]["data"] == {
        "currency": "DKK",
        "slots": [
            {
                "start": "2026-09-26T22:00:00+00:00",
                "price": 1.0,
                "spot": 1.2,
                "tariff_estimated": True,
            },
            {
                "start": "2026-09-26T22:15:00+00:00",
                "price": 2.0,
                "spot": None,
                "tariff_estimated": None,
            },
        ],
    }
    assert await PriceStore(hass, "entry1").async_load() == StoredPrices(
        known, "DKK", split
    )
    await store.async_remove()
    assert KEY not in hass_storage


async def test_store_without_split_keys_loads_totals(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A file without the split keys loads its totals; half a split is no split."""
    hass_storage[KEY] = {
        "version": 2,
        "minor_version": 1,
        "key": KEY,
        "data": {
            "currency": "DKK",
            "slots": [
                {"start": "2026-09-26T22:00:00+00:00", "price": 1.0},
                {"start": "2026-09-26T22:15:00+00:00", "price": 2.0},
            ],
        },
    }
    known = _slots(MIDNIGHT, [1.0, 2.0])
    assert await PriceStore(hass, "entry1").async_load() == StoredPrices(
        known, "DKK", {}
    )

    hass_storage[KEY]["data"] = {
        "currency": "DKK",
        "slots": [
            {"start": "2026-09-26T22:00:00+00:00", "price": 1.0, "spot": 0.5},
            {
                "start": "2026-09-26T22:15:00+00:00",
                "price": 2.0,
                "spot": None,
                "tariff_estimated": True,
            },
            {
                "start": "2026-09-26T22:30:00+00:00",
                "price": 3.0,
                "spot": 1,
                "tariff_estimated": False,
            },
        ],
    }
    assert await PriceStore(hass, "entry1").async_load() == StoredPrices(
        _slots(MIDNIGHT, [1.0, 2.0, 3.0]),
        "DKK",
        {MIDNIGHT + 2 * STEP: SlotSplit(1.0, False)},
    )
    assert "spot prices" not in caplog.text


@pytest.mark.parametrize(
    "bad",
    [
        {"spot": "cheap", "tariff_estimated": True},
        {"spot": True, "tariff_estimated": True},
        {"spot": 1.0, "tariff_estimated": 1},
        {"spot": None, "tariff_estimated": 1},
        {"spot": "cheap"},
    ],
)
async def test_store_bad_split_keeps_totals(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    bad: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A wrong type in either split key drops the whole file's split, not the totals."""
    hass_storage[KEY] = {
        "version": 2,
        "minor_version": 1,
        "key": KEY,
        "data": {
            "currency": "DKK",
            "slots": [
                {"start": "2026-09-26T22:00:00+00:00", "price": 1.0} | bad,
                {
                    "start": "2026-09-26T22:15:00+00:00",
                    "price": 2.0,
                    "spot": 1.5,
                    "tariff_estimated": False,
                },
            ],
        },
    }
    assert await PriceStore(hass, "entry1").async_load() == StoredPrices(
        _slots(MIDNIGHT, [1.0, 2.0]), "DKK", {}
    )
    assert "Ignoring the stored spot prices" in caplog.text
    assert caplog.text.count("Ignoring the stored") == 1


async def test_store_missing_file(hass: HomeAssistant) -> None:
    """No file: no known slots and no currency."""
    assert await PriceStore(hass, "entry1").async_load() == StoredPrices({}, None)


async def test_store_version_1_migrates_to_empty(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Version 1 held spot prices: they are dropped, and the file is saved as version 2."""
    hass_storage[KEY] = {
        "version": 1,
        "minor_version": 1,
        "key": KEY,
        "data": {"slots": [{"start": "2026-09-26T22:00:00+00:00", "price": 1.0}]},
    }
    assert await PriceStore(hass, "entry1").async_load() == StoredPrices({}, None)
    await hass.async_block_till_done()
    assert hass_storage[KEY]["version"] == 2
    assert hass_storage[KEY]["data"] == {"currency": None, "slots": []}


@pytest.mark.parametrize(
    "data",
    [
        {"no_slots": []},
        {"slots": []},  # no currency
        {"currency": 5, "slots": []},
        {"currency": "DKK", "slots": [{"start": "not a time", "price": 1.0}]},
        {
            "currency": "DKK",
            "slots": [{"start": "2026-09-26T22:00:00+00:00", "price": "cheap"}],
        },
        {"currency": "DKK", "slots": [{"start": "2026-09-26T22:00:00", "price": 1.0}]},
        {"currency": "DKK", "slots": [{"price": 1.0}]},
        {"currency": "DKK", "slots": "wrong"},
    ],
)
async def test_store_wrong_shape(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    data: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Valid JSON of the wrong shape gives no slots, no currency and a warning."""
    hass_storage[KEY] = {"version": 2, "minor_version": 1, "key": KEY, "data": data}
    assert await PriceStore(hass, "entry1").async_load() == StoredPrices({}, None)
    assert "stored prices" in caplog.text


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (
            datetime(2026, 9, 27, 0, 0, tzinfo=TZ),
            datetime(2026, 9, 27, 0, 5, tzinfo=TZ),
        ),
        (
            datetime(2026, 9, 27, 15, 4, 59, tzinfo=TZ),
            datetime(2026, 9, 27, 15, 5, tzinfo=TZ),
        ),
        (
            datetime(2026, 9, 27, 15, 5, tzinfo=TZ),
            datetime(2026, 9, 27, 20, 5, tzinfo=TZ),
        ),
        (
            datetime(2026, 9, 27, 20, 5, tzinfo=TZ),
            datetime(2026, 9, 28, 0, 5, tzinfo=TZ),
        ),
        (
            datetime(2026, 9, 27, 23, 59, tzinfo=TZ),
            datetime(2026, 9, 28, 0, 5, tzinfo=TZ),
        ),
        # Spring forward (02:00 -> 03:00): from before and after the change.
        (
            datetime(2026, 3, 29, 1, 0, tzinfo=TZ),
            datetime(2026, 3, 29, 5, 5, tzinfo=TZ),
        ),
        (
            datetime(2026, 3, 29, 20, 10, tzinfo=TZ),
            datetime(2026, 3, 30, 0, 5, tzinfo=TZ),
        ),
        # Fall back (03:00 -> 02:00): from before and after the change.
        (
            datetime(2026, 10, 25, 0, 10, tzinfo=TZ),
            datetime(2026, 10, 25, 5, 5, tzinfo=TZ),
        ),
        (
            datetime(2026, 10, 25, 20, 10, tzinfo=TZ),
            datetime(2026, 10, 26, 0, 5, tzinfo=TZ),
        ),
    ],
)
def test_next_price_read(now: datetime, expected: datetime) -> None:
    """The next read time is the first local 00:05, 05:05, 10:05, 15:05 or 20:05 after now, in UTC."""
    result = next_price_read(now.astimezone(UTC), TZ)
    assert result == expected
    assert result.tzinfo is UTC
