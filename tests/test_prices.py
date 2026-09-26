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
    current_price,
    merge_forecast,
    prices_today,
    prices_tomorrow,
    prune,
)

from .conftest import make_forecast

TZ = ZoneInfo("Europe/Copenhagen")
STEP = timedelta(minutes=15)
# 2026-09-27 00:00 local (CEST, UTC+2) is 2026-09-26 22:00 UTC.
MIDNIGHT = datetime(2026, 9, 26, 22, 0, tzinfo=UTC)
NOW = datetime(2026, 9, 27, 12, 7, tzinfo=UTC)  # 14:07 local


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


async def test_store_round_trip(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Saved slots load back as UTC keys; remove deletes the file."""
    store = PriceStore(hass, "entry1")
    known = _slots(MIDNIGHT, [1.0, 2.0])
    await store.async_save(known)
    assert hass_storage["nortec_go.entry1.prices"]["data"] == {
        "slots": [
            {"start": "2026-09-26T22:00:00+00:00", "price": 1.0},
            {"start": "2026-09-26T22:15:00+00:00", "price": 2.0},
        ]
    }
    assert await PriceStore(hass, "entry1").async_load() == known
    await store.async_remove()
    assert "nortec_go.entry1.prices" not in hass_storage


async def test_store_missing_file(hass: HomeAssistant) -> None:
    """No file: no known slots."""
    assert await PriceStore(hass, "entry1").async_load() == {}


@pytest.mark.parametrize(
    "data",
    [
        {"no_slots": []},
        {"slots": [{"start": "not a time", "price": 1.0}]},
        {"slots": [{"start": "2026-09-26T22:00:00+00:00", "price": "cheap"}]},
        {"slots": [{"start": "2026-09-26T22:00:00", "price": 1.0}]},  # no offset
        {"slots": [{"price": 1.0}]},
        {"slots": "wrong"},
    ],
)
async def test_store_wrong_shape(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    data: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Valid JSON of the wrong shape gives no known slots and a warning."""
    hass_storage["nortec_go.entry1.prices"] = {
        "version": 1,
        "minor_version": 1,
        "key": "nortec_go.entry1.prices",
        "data": data,
    }
    assert await PriceStore(hass, "entry1").async_load() == {}
    assert "stored prices" in caplog.text
