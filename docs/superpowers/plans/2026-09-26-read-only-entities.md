# Read-only entities for EV Smart Charging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Poll the charger, the car and the price forecast, and show them as sensors and binary sensors on a
charger device and a car device, in the shape EV Smart Charging needs.

**Architecture:** `prices.py` holds pure functions on price slots and the `Store` wrapper. `coordinator.py`
holds one `DataUpdateCoordinator` that reads the charger and the car on a state-based interval, plus the price
job and the quarter-hour tick on their own timers. `entity.py` gives the charger and car base entities;
`sensor.py` and `binary_sensor.py` map `pynortecgo` models to entities.

**Tech Stack:** Python 3.14, Home Assistant 2026.9.3 (via `pytest-homeassistant-custom-component`),
`pynortecgo==0.2.0`, uv, ruff, mypy (strict), pytest with `freezer`.

**Spec:** `docs/superpowers/specs/2026-09-26-read-only-entities-design.md`. Read it with this plan; every §
refers to it.

## Global Constraints

- `pynortecgo==0.2.0` (already pinned). Only `set_charger()`, `get_charger()`, `get_vehicle()` and
  `get_price_forecast()` are called. Nothing starts or stops a charge.
- Intervals: 60 min unplugged, 15 min connected, 5 min while `charge_state` is `STARTING`, `CHARGING` or
  `STOPPING`. Initial interval 15 min.
- Price reads: once at setup, then at 00:05, 05:05, 10:05, 15:05, 20:05 in HA's time zone.
- Padding: `PAST_SLOT_PRICE = 0.0`, `MISSING_SLOT_PRICE = 10.0`; `prices_tomorrow` is `[]` when no slot of
  tomorrow is known.
- Price unit `f"{hass.config.currency}/kWh"`; no device class; state class `measurement`.
- Store: version 1, key `nortec_go.<entry_id>.prices`, data `{"slots": [{"start": <ISO UTC>, "price": <float>}]}`.
- Unique IDs `<charger id>_<key>`; devices `(DOMAIN, "<charger id>")` and `(DOMAIN, "<charger id>_car")`;
  no `via_device`.
- No options flow, no refresh button.
- No email, password, token, charger ID, car ID or `device_id` in any log line or exception message (hard
  rule 5). `pynortecgo` 0.2.0's exception texts hold none and may be passed on with `str(err)`.
- `AuthError` is never retried; it leads to reauth (hard rule 6).
- `strings.json` has literal text only; `translations/en.json` is an exact copy.
- Tests always mock `pynortecgo`; fixtures are built from `pynortecgo` model objects with obviously fake
  values (hard rule 7). Nothing in the repo holds real IDs, raw API endpoints or response shapes (hard rule 3).
- Subagents never read `.env`, `local/` or `config/`.
- TDD: every behaviour gets a failing test first.
- Gates before every commit, in the task's working directory:
  `uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95`.
- Commit messages are written with the Write tool to a file outside the repo and committed with
  `git commit -F <file>` (the subagent guard refuses heredocs). They end with the co-author trailer given in
  the dispatch.
- Docs: plain, short sentences; lines ≤ 120 characters in `.md` files, except table rows.
- Tests that depend on local time set `await hass.config.async_set_time_zone("Europe/Copenhagen")` first:
  the test `hass` starts in `US/Pacific`.

## Review Focus

- A restart late in the evening with no stored prices and a failing forecast: Current price is available,
  its state is unknown, and `prices_today` still has 96 entries. Pinned in Task 3.
- A DST day (25 Oct 2026, 29 Mar 2026): today has 100 or 92 slots and the times stay in order across the
  change. Pinned in Task 1.
- A car without its own integration (`battery_level`, `charge_limit`, `plugged_in`, `last_seen` all `None`):
  states are unknown, not unavailable, and *Connected to charger* is unknown only while the cable is
  connected. Pinned in Task 3.
- The forecast read fails at setup with a network error: setup succeeds and uses the stored prices. Pinned
  in Task 2.
- The charger read fails after setup while prices are known: charger and car entities are unavailable,
  Current price stays available with its lists. Pinned in Task 3.

## Waves

| Wave | Tasks | Notes |
|---|---|---|
| 1 | 1, 4 | Disjoint files. Task 4 (docs) starts ahead of inputs, from the names this plan fixes, and is re-checked against the code that lands |
| 2 | 2 | Needs Task 1's `prices.py`, constants and fixtures |
| 3 | 3 | Needs Task 2's coordinator |

No task has guarded files.

## File map

| File | Task | Responsibility |
|---|---|---|
| `custom_components/nortec_go/const.py` | 1 | All new constants (intervals, price times, padding, store) |
| `custom_components/nortec_go/prices.py` | 1 | `KnownSlots`, merge, prune, day lists, current price, `PriceStore` |
| `tests/conftest.py` | 1 | `make_charger` extended, `make_vehicle`, `make_forecast`, client defaults, `setup_integration` |
| `tests/test_prices.py` | 1 | Tests for `prices.py` |
| `custom_components/nortec_go/coordinator.py` | 2 | `NortecGoData`, `interval_for`, `NortecGoCoordinator` |
| `custom_components/nortec_go/entry.py` | 2 | `NortecGoConfigEntry = ConfigEntry[NortecGoCoordinator]` |
| `custom_components/nortec_go/__init__.py` | 2, 3 | Setup with the coordinator (2); `PLATFORMS` (3) |
| `tests/test_coordinator.py`, `tests/test_init.py` | 2 | Coordinator and setup tests |
| `custom_components/nortec_go/entity.py` | 3 | Base, charger and car entities |
| `custom_components/nortec_go/sensor.py`, `binary_sensor.py` | 3 | The entities |
| `custom_components/nortec_go/strings.json`, `translations/en.json` | 3 | Device and entity names |
| `tests/test_sensor.py`, `tests/test_binary_sensor.py` | 3 | Entity tests |
| `custom_components/nortec_go/quality_scale.yaml` | 4 | §6 |
| `docs/user/nortec_go.md`, `CHANGELOG.md` | 4 | §7 |
| `docs/decisions.md`, `docs/way-of-working.md` | 4 | D22–D24, labels |

---

### Task 1: Price logic, constants and test fixtures

**Model:** sonnet · **Wave:** 1

**Files:**
- Modify: `custom_components/nortec_go/const.py`
- Create: `custom_components/nortec_go/prices.py`
- Modify: `tests/conftest.py`
- Create: `tests/test_prices.py`

**Interfaces:**
- Consumes: `pynortecgo` 0.2.0 models (`PriceForecast`, `PriceSlot`, `Charger`, `ChargeState`, `Vehicle`).
- Produces:
  - `const.py`: `INTERVAL_UNPLUGGED`, `INTERVAL_CONNECTED`, `INTERVAL_CHARGING` (`timedelta`),
    `PRICE_READ_HOURS: tuple[int, ...] = (0, 5, 10, 15, 20)`, `PRICE_READ_MINUTE = 5`,
    `TICK_MINUTES: tuple[int, ...] = (0, 15, 30, 45)`, `SLOT_LENGTH = timedelta(minutes=15)`,
    `PAST_SLOT_PRICE = 0.0`, `MISSING_SLOT_PRICE = 10.0`, `PRICE_STORE_VERSION = 1`,
    `PRICE_STORE_KEY = "nortec_go.{entry_id}.prices"`.
  - `prices.py`:
    - `type KnownSlots = dict[datetime, float]` (slot start in UTC → price)
    - `def merge_forecast(known: Mapping[datetime, float], forecast: PriceForecast) -> KnownSlots`
    - `def prune(known: Mapping[datetime, float], now: datetime, time_zone: tzinfo) -> KnownSlots`
    - `def prices_today(known: Mapping[datetime, float], now: datetime, time_zone: tzinfo) -> list[dict[str, Any]]`
    - `def prices_tomorrow(known: Mapping[datetime, float], now: datetime, time_zone: tzinfo) -> list[dict[str, Any]]`
    - `def current_price(known: Mapping[datetime, float], now: datetime) -> float | None`
    - `class PriceStore` with `__init__(self, hass: HomeAssistant, entry_id: str)`,
      `async def async_load(self) -> KnownSlots`, `async def async_save(self, known: Mapping[datetime, float]) -> None`,
      `async def async_remove(self) -> None`
  - `tests/conftest.py`: `FAKE_VEHICLE_NAME = "Family car"`,
    `make_charger(charger_id: int = FAKE_CHARGER_ID, name: str = FAKE_CHARGER_NAME, *, is_connected: bool = False, charge_state: ChargeState | None = None) -> Charger`,
    `make_vehicle(*, name: str = FAKE_VEHICLE_NAME, brand: str | None = "Example", model: str | None = "Model E", battery_level: float | None = 55.0, charge_limit: float | None = 80.0, plugged_in: bool | None = False, last_seen: datetime | None = FAKE_LAST_SEEN) -> Vehicle`,
    `make_forecast(start: datetime, prices: Sequence[float]) -> PriceForecast`,
    `FAKE_LAST_SEEN`, `async def setup_integration(hass: HomeAssistant, entry: MockConfigEntry) -> None`.
    `mock_client_class` also sets `get_vehicle.return_value = make_vehicle()` and
    `get_price_forecast.return_value = make_forecast(DEFAULT_FORECAST_START, [1.25] * 8)`.

- [ ] **Step 1: Constants**

Append to `custom_components/nortec_go/const.py` (add `from datetime import timedelta` to the imports):

```python
# Charger and car polling, by the charger's state (D22).
INTERVAL_UNPLUGGED: Final = timedelta(minutes=60)
INTERVAL_CONNECTED: Final = timedelta(minutes=15)
INTERVAL_CHARGING: Final = timedelta(minutes=5)

# Price reads (local time) and the quarter-hour tick that moves the current slot.
PRICE_READ_HOURS: Final = (0, 5, 10, 15, 20)
PRICE_READ_MINUTE: Final = 5
TICK_MINUTES: Final = (0, 15, 30, 45)
SLOT_LENGTH: Final = timedelta(minutes=15)

# EV Smart Charging's lists are padded to a full day (D23).
PAST_SLOT_PRICE: Final = 0.0
MISSING_SLOT_PRICE: Final = 10.0

PRICE_STORE_VERSION: Final = 1
PRICE_STORE_KEY: Final = "nortec_go.{entry_id}.prices"
```

- [ ] **Step 2: Fixtures**

In `tests/conftest.py`:

- Add imports: `from collections.abc import Generator, Sequence`, `from datetime import UTC, datetime, timedelta`,
  and from `pynortecgo`: `ChargeState, PriceForecast, PriceSlot, Vehicle`; from `homeassistant.core` import
  `HomeAssistant`.
- Add constants after `NEW_TOKENS`:

```python
FAKE_VEHICLE_NAME = "Family car"
FAKE_LAST_SEEN = datetime(2026, 9, 26, 8, 30, tzinfo=UTC)
DEFAULT_FORECAST_START = datetime(2026, 9, 26, 22, 0, tzinfo=UTC)
```

- Replace `make_charger` and add the two new builders:

```python
def make_charger(
    charger_id: int = FAKE_CHARGER_ID,
    name: str = FAKE_CHARGER_NAME,
    *,
    is_connected: bool = False,
    charge_state: ChargeState | None = None,
) -> Charger:
    """Return a charger; idle and unplugged unless told otherwise."""
    return Charger(
        id=charger_id,
        name=name,
        max_kw=11.0,
        state=ChargerState.AVAILABLE,
        state_raw="available",
        is_connected=is_connected,
        charge_state=charge_state,
        charge_state_raw=None if charge_state is None else charge_state.value,
        charge_id=None if charge_state is None else "fake-charge-id",
        can_stop=None if charge_state is None else True,
    )


def make_vehicle(
    *,
    name: str = FAKE_VEHICLE_NAME,
    brand: str | None = "Example",
    model: str | None = "Model E",
    battery_level: float | None = 55.0,
    charge_limit: float | None = 80.0,
    plugged_in: bool | None = False,
    last_seen: datetime | None = FAKE_LAST_SEEN,
) -> Vehicle:
    """Return the account's car with fake values."""
    return Vehicle(
        id=424242,
        name=name,
        capacity_kwh=60.0,
        max_kw_ac=11.0,
        brand=brand,
        model=model,
        battery_level=battery_level,
        charge_limit=charge_limit,
        plugged_in=plugged_in,
        power_delivery_state=None,
        power_delivery_state_raw=None,
        last_seen=last_seen,
    )


def make_forecast(start: datetime, prices: Sequence[float]) -> PriceForecast:
    """Return 15-minute slots from start, one per price."""
    step = timedelta(minutes=15)
    return PriceForecast(
        area_id=99,
        area_name="Test area",
        slots=[
            PriceSlot(start=start + i * step, end=start + (i + 1) * step, price=price)
            for i, price in enumerate(prices)
        ],
    )


async def setup_integration(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Add the entry and set it up."""
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
```

- In `mock_client_class`, after `client.get_charger.return_value = make_charger()`, add:

```python
        client.get_vehicle.return_value = make_vehicle()
        client.get_price_forecast.return_value = make_forecast(
            DEFAULT_FORECAST_START, [1.25] * 8
        )
```

Run `uv run pytest -q`: all existing tests PASS (the new defaults aren't used yet).

- [ ] **Step 3: Write the failing tests**

Create `tests/test_prices.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `uv run pytest tests/test_prices.py -q`
Expected: FAIL (`ModuleNotFoundError: custom_components.nortec_go.prices`).

- [ ] **Step 5: Implement `prices.py`**

Create `custom_components/nortec_go/prices.py`:

```python
"""Price slots: merge, prune, EV Smart Charging's day lists, and their storage."""

from collections.abc import Mapping
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


class PriceStore:
    """The known slots of one config entry, in Home Assistant's storage."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Use the store file of this entry."""
        self._store: Store[dict[str, Any]] = Store(
            hass, PRICE_STORE_VERSION, PRICE_STORE_KEY.format(entry_id=entry_id)
        )

    async def async_load(self) -> KnownSlots:
        """Load the saved slots; none if the file is missing or of the wrong shape."""
        data = await self._store.async_load()
        if data is None:
            return {}
        try:
            known: KnownSlots = {}
            for item in data["slots"]:
                known[_parse_start(item["start"])] = float(item["price"])
        except KeyError, TypeError, ValueError:
            _LOGGER.warning("Ignoring the stored prices: they have an unexpected shape")
            return {}
        return known

    async def async_save(self, known: Mapping[datetime, float]) -> None:
        """Save the slots, sorted by start."""
        await self._store.async_save(
            {
                "slots": [
                    {"start": start.isoformat(), "price": price}
                    for start, price in sorted(known.items())
                ]
            }
        )

    async def async_remove(self) -> None:
        """Delete the store file."""
        await self._store.async_remove()
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/test_prices.py -q`
Expected: PASS. Then run the full gates (Global Constraints).

- [ ] **Step 7: Commit**

`git add custom_components/nortec_go/const.py custom_components/nortec_go/prices.py tests/conftest.py tests/test_prices.py`,
then commit with the message `feat: price slot logic and storage (#8)` plus the trailer.

---

### Task 2: Coordinator and setup

**Model:** opus (reauth on `AuthError`, error mapping at setup and later, the price job) · **Wave:** 2

**Files:**
- Create: `custom_components/nortec_go/coordinator.py`
- Modify: `custom_components/nortec_go/entry.py`
- Modify: `custom_components/nortec_go/__init__.py`
- Create: `tests/test_coordinator.py`
- Modify: `tests/test_init.py`

**Interfaces:**
- Consumes: Task 1's constants, `prices.py` (`KnownSlots`, `merge_forecast`, `prune`, `PriceStore`) and
  fixtures (`make_charger`, `make_vehicle`, `make_forecast`, `setup_integration`, `FAKE_VEHICLE_NAME`).
- Produces:
  - `entry.py`: `type NortecGoConfigEntry = ConfigEntry[NortecGoCoordinator]`.
  - `coordinator.py`:
    - `@dataclass(frozen=True) class NortecGoData: charger: Charger; vehicle: Vehicle | None`
    - `def interval_for(charger: Charger) -> timedelta`
    - `def car_device_identifier(charger_id: str) -> tuple[str, str]` → `(DOMAIN, f"{charger_id}_car")`
    - `class NortecGoCoordinator(DataUpdateCoordinator[NortecGoData])` with attributes
      `client: NortecGoClient`, `charger_id: str`, `has_car: bool`, `known_prices: KnownSlots`, and methods
      `async def async_load_prices(self) -> None`,
      `async def async_read_prices(self, *, during_setup: bool = False) -> None`,
      `@callback def async_start_price_read(self) -> None` (one read as an entry background task; the price
      timer calls it too), `@callback def async_start_timers(self) -> None`.
  - `__init__.py`: `async_setup_entry` builds the coordinator (§4.1); `async_remove_entry` removes the stored
    prices. `PLATFORMS` stays `[]` (Task 3 fills it).

- [ ] **Step 1: Write the failing coordinator tests**

Create `tests/test_coordinator.py`:

```python
"""Tests for the Nortec Go coordinator: polling, errors, prices and timers."""

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util
from pynortecgo import (
    ApiError,
    AuthError,
    ChargerNotFoundError,
    ChargeState,
    MultipleVehiclesError,
    NortecGoConnectionError,
    RateLimitError,
    UnexpectedResponseError,
    VehicleNotFoundError,
)
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.nortec_go.const import (
    DOMAIN,
    INTERVAL_CHARGING,
    INTERVAL_CONNECTED,
    INTERVAL_UNPLUGGED,
)
from custom_components.nortec_go.coordinator import (
    NortecGoCoordinator,
    car_device_identifier,
    interval_for,
)

from .conftest import (
    FAKE_CHARGER_ID,
    make_charger,
    make_forecast,
    make_vehicle,
    setup_integration,
)

# 2026-09-27 00:00 local (CEST) is 2026-09-26 22:00 UTC.
MIDNIGHT = datetime(2026, 9, 26, 22, 0, tzinfo=UTC)
STORE_KEY = "nortec_go.{}.prices"


@pytest.fixture(autouse=True)
async def copenhagen(hass: HomeAssistant) -> None:
    """Run every test in the owner's time zone."""
    await hass.config.async_set_time_zone("Europe/Copenhagen")


def _coordinator(entry: MockConfigEntry) -> NortecGoCoordinator:
    """The entry's coordinator, with a listener so it keeps polling without entities."""
    coordinator: NortecGoCoordinator = entry.runtime_data
    # HA only schedules the next poll while the coordinator has listeners; in Task 2
    # there are no entities yet. Adding the first listener also schedules a poll.
    coordinator.async_add_listener(lambda: None)
    return coordinator


@pytest.mark.parametrize(
    ("is_connected", "charge_state", "interval"),
    [
        (False, None, INTERVAL_UNPLUGGED),
        (True, None, INTERVAL_CONNECTED),
        (True, ChargeState.PAUSED, INTERVAL_CONNECTED),
        (True, ChargeState.UNKNOWN, INTERVAL_CONNECTED),
        (True, ChargeState.STARTING, INTERVAL_CHARGING),
        (True, ChargeState.CHARGING, INTERVAL_CHARGING),
        (True, ChargeState.STOPPING, INTERVAL_CHARGING),
    ],
)
def test_interval_for(
    is_connected: bool, charge_state: ChargeState | None, interval: timedelta
) -> None:
    """The interval follows the charger's state."""
    charger = make_charger(is_connected=is_connected, charge_state=charge_state)
    assert interval_for(charger) == interval


async def test_setup_reads_charger_car_and_prices(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """Setup sets the charger, reads charger, car and prices once, and sets the interval."""
    mock_client.get_charger.return_value = make_charger(is_connected=True)
    await setup_integration(hass, mock_config_entry)

    coordinator = _coordinator(mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert coordinator.client is mock_client
    assert coordinator.has_car
    assert coordinator.data.vehicle == make_vehicle()
    assert coordinator.update_interval == INTERVAL_CONNECTED
    mock_client.set_charger.assert_called_once_with(FAKE_CHARGER_ID)
    mock_client.get_vehicle.assert_awaited_once()
    mock_client.get_price_forecast.assert_awaited_once_with()


async def test_interval_changes_after_a_poll(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A poll that sees a charge starts polling every 5 minutes."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    assert coordinator.update_interval == INTERVAL_UNPLUGGED

    mock_client.get_charger.return_value = make_charger(
        is_connected=True, charge_state=ChargeState.CHARGING
    )
    freezer.tick(INTERVAL_UNPLUGGED)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert coordinator.update_interval == INTERVAL_CHARGING
    assert mock_client.get_charger.await_count == 2
    assert mock_client.get_vehicle.await_count == 2


@pytest.mark.parametrize(
    ("error", "state"),
    [
        (NortecGoConnectionError("network down"), ConfigEntryState.SETUP_RETRY),
        (RateLimitError("too many requests"), ConfigEntryState.SETUP_RETRY),
        (ApiError("GET /example", 500), ConfigEntryState.SETUP_RETRY),
        (
            UnexpectedResponseError("GET /example", "bad shape"),
            ConfigEntryState.SETUP_ERROR,
        ),
        (
            ChargerNotFoundError("GET /example: the set charger was not found"),
            ConfigEntryState.SETUP_ERROR,
        ),
    ],
)
async def test_first_refresh_charger_errors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    error: Exception,
    state: ConfigEntryState,
) -> None:
    """Charger errors at setup retry or stop setup; the car isn't read."""
    mock_client.get_charger.side_effect = error
    await setup_integration(hass, mock_config_entry)

    entry_state = mock_config_entry.state  # a local, so mypy doesn't keep the narrowing
    assert entry_state is state
    if entry_state is ConfigEntryState.SETUP_ERROR:
        assert mock_config_entry.reason == str(error)
    mock_client.get_vehicle.assert_not_awaited()


@pytest.mark.parametrize("method", ["get_charger", "get_vehicle", "get_price_forecast"])
async def test_first_refresh_auth_error_starts_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    method: str,
) -> None:
    """An AuthError from any read during setup starts reauth, without logging in."""
    getattr(mock_client, method).side_effect = AuthError("token rejected")
    with patch.object(ConfigEntry, "async_start_reauth_if_available") as start_reauth:
        await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    start_reauth.assert_called_once()
    mock_client.login.assert_not_awaited()


@pytest.mark.parametrize(
    "error", [VehicleNotFoundError("no car"), MultipleVehiclesError("two cars")]
)
async def test_no_car(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
) -> None:
    """No single car: setup works without a car, logs it once, and the car isn't read again."""
    mock_client.get_vehicle.side_effect = error
    await setup_integration(hass, mock_config_entry)

    coordinator = _coordinator(mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert not coordinator.has_car
    assert coordinator.data.vehicle is None
    assert caplog.text.count("No car entities") == 1

    freezer.tick(INTERVAL_UNPLUGGED)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_client.get_vehicle.await_count == 1


async def test_car_error_at_setup_continues(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Another car error at setup: loaded, car expected but not read yet; a later read fills it in."""
    mock_client.get_vehicle.side_effect = NortecGoConnectionError("network down")
    await setup_integration(hass, mock_config_entry)

    coordinator = _coordinator(mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert coordinator.has_car
    assert coordinator.data.vehicle is None
    assert caplog.text.count("Could not read the car") == 1

    mock_client.get_vehicle.side_effect = None
    freezer.tick(INTERVAL_UNPLUGGED)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert coordinator.data.vehicle == make_vehicle()


async def test_later_charger_errors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A later charger failure fails the update, skips the car and keeps the interval."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)

    mock_client.get_charger.side_effect = NortecGoConnectionError("network down")
    freezer.tick(INTERVAL_UNPLUGGED)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert not coordinator.last_update_success
    assert coordinator.update_interval == INTERVAL_UNPLUGGED
    assert mock_client.get_vehicle.await_count == 1


async def test_rate_limit_retry_after(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A later RateLimitError's retry_after sets the next poll (not the 60 min interval)."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)

    mock_client.get_charger.side_effect = RateLimitError(
        "too many requests", retry_after=120.0
    )
    await coordinator.async_refresh()
    assert not coordinator.last_update_success
    reads = mock_client.get_charger.await_count

    # HA rounds timers to whole seconds, so check well before and well after 120 s.
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_client.get_charger.await_count == reads
    freezer.tick(timedelta(seconds=70))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_client.get_charger.await_count == reads + 1


@pytest.mark.parametrize(
    "error",
    [
        ChargerNotFoundError("GET /example: the set charger was not found"),
        UnexpectedResponseError("GET /example", "bad shape"),
    ],
)
async def test_later_permanent_charger_errors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    error: Exception,
) -> None:
    """A later ChargerNotFoundError or UnexpectedResponseError fails the update; the entry stays loaded."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)

    mock_client.get_charger.side_effect = error
    await coordinator.async_refresh()
    assert not coordinator.last_update_success
    assert mock_config_entry.state is ConfigEntryState.LOADED


@pytest.mark.parametrize("method", ["get_charger", "get_vehicle"])
async def test_later_auth_error_starts_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    method: str,
) -> None:
    """A later AuthError from the charger or car starts reauth, and polling stops."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)

    getattr(mock_client, method).side_effect = AuthError("token rejected")
    with patch.object(ConfigEntry, "async_start_reauth") as start_reauth:
        await coordinator.async_refresh()
    start_reauth.assert_called_once()
    mock_client.login.assert_not_awaited()

    reads = mock_client.get_charger.await_count
    freezer.tick(INTERVAL_UNPLUGGED * 2)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_client.get_charger.await_count == reads


async def test_later_car_error_keeps_car_data(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A later car error keeps the last car data, logs once, and logs the recovery."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)

    for error in (ApiError("GET /example", 500), VehicleNotFoundError("no car")):
        mock_client.get_vehicle.side_effect = error
        await coordinator.async_refresh()
        assert coordinator.last_update_success
        assert coordinator.data.vehicle == make_vehicle()
    assert caplog.text.count("Could not read the car") == 1

    mock_client.get_vehicle.side_effect = None
    await coordinator.async_refresh()
    assert "Reading the car works again" in caplog.text


async def test_car_device_updated_on_rename(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    device_registry: dr.DeviceRegistry,
) -> None:
    """A car read with a new name, brand or model updates the car device.

    The empty-name fallback to the translated "Car" needs Task 3's strings; Task 3 tests it.
    """
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    device = device_registry.async_get_or_create(
        config_entry_id=mock_config_entry.entry_id,
        identifiers={car_device_identifier(str(FAKE_CHARGER_ID))},
        translation_key="car",
    )

    mock_client.get_vehicle.return_value = make_vehicle(
        name="Other car", brand="Other", model="Model X"
    )
    await coordinator.async_refresh()
    updated = device_registry.async_get(device.id, include_child_devices=False)
    assert updated is not None
    assert (updated.name, updated.manufacturer, updated.model) == (
        "Other car",
        "Other",
        "Model X",
    )


async def test_prices_read_at_the_five_times(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Prices are read at setup and at 00:05, 05:05, 10:05, 15:05, 20:05 local, not in between."""
    freezer.move_to(MIDNIGHT - timedelta(minutes=30))  # 23:30 local
    await setup_integration(hass, mock_config_entry)
    assert mock_client.get_price_forecast.await_count == 1

    reads = 1
    for hours in range(24):
        for minute in (0, 5, 30):
            when = MIDNIGHT + timedelta(hours=hours, minutes=minute)
            freezer.move_to(when)
            async_fire_time_changed(hass, when)
            await hass.async_block_till_done()
            local_hour = when.astimezone(dt_util.get_default_time_zone()).hour
            if minute == 5 and local_hour in (0, 5, 10, 15, 20):
                reads += 1
            assert mock_client.get_price_forecast.await_count == reads, when
    assert reads == 6


async def test_price_read_merges_and_saves(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """A price read merges into the known slots, prunes yesterday and saves."""
    freezer.move_to(MIDNIGHT + timedelta(hours=10))
    mock_client.get_price_forecast.return_value = make_forecast(MIDNIGHT, [1.0, 2.0])
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    assert coordinator.known_prices == {
        MIDNIGHT: 1.0,
        MIDNIGHT + timedelta(minutes=15): 2.0,
    }
    stored = hass_storage[STORE_KEY.format(mock_config_entry.entry_id)]["data"]["slots"]
    assert [slot["price"] for slot in stored] == [1.0, 2.0]


async def test_stored_prices_loaded_at_setup(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """Stored slots of today are loaded; yesterday's are dropped; a failed read keeps them."""
    freezer.move_to(MIDNIGHT + timedelta(hours=10))
    key = STORE_KEY.format(mock_config_entry.entry_id)
    hass_storage[key] = {
        "version": 1,
        "minor_version": 1,
        "key": key,
        "data": {
            "slots": [
                {"start": "2026-09-26T21:45:00+00:00", "price": 9.0},
                {"start": "2026-09-26T22:00:00+00:00", "price": 1.0},
            ]
        },
    }
    mock_client.get_price_forecast.side_effect = NortecGoConnectionError("network down")
    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert _coordinator(mock_config_entry).known_prices == {MIDNIGHT: 1.0}


async def test_failed_price_read_keeps_slots(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failed scheduled read logs a warning and keeps the known slots."""
    freezer.move_to(MIDNIGHT + timedelta(hours=1))
    mock_client.get_price_forecast.return_value = make_forecast(MIDNIGHT, [1.0])
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)

    mock_client.get_price_forecast.side_effect = UnexpectedResponseError(
        "GET /example", "gap"
    )
    await coordinator.async_read_prices()
    assert coordinator.known_prices == {MIDNIGHT: 1.0}
    assert "Could not read the price forecast" in caplog.text


async def test_later_price_auth_error_starts_reauth(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """An AuthError in a scheduled price read starts reauth, without logging in."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)

    mock_client.get_price_forecast.side_effect = AuthError("token rejected")
    with patch.object(ConfigEntry, "async_start_reauth") as start_reauth:
        await coordinator.async_read_prices()
    start_reauth.assert_called_once()
    mock_client.login.assert_not_awaited()


async def test_tick_updates_listeners_without_api_calls(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The quarter-hour tick calls the listeners and makes no API call."""
    freezer.move_to(MIDNIGHT + timedelta(hours=1, minutes=10))
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    calls = []
    coordinator.async_add_listener(lambda: calls.append(1))

    when = MIDNIGHT + timedelta(hours=1, minutes=15)
    freezer.move_to(when)
    async_fire_time_changed(hass, when)
    await hass.async_block_till_done()
    assert calls == [1]
    assert mock_client.get_charger.await_count == 1
    assert mock_client.get_price_forecast.await_count == 1


def test_car_device_identifier() -> None:
    """The car device is keyed on the charger."""
    assert car_device_identifier("123") == (DOMAIN, "123_car")
```

- [ ] **Step 2: Adapt `tests/test_init.py`**

- Replace the local `_setup` helper with `setup_integration` from `.conftest` (import it; delete `_setup`),
  and rename every `await _setup(` to `await setup_integration(`.
- In `test_setup_entry`, replace `assert mock_config_entry.runtime_data is mock_client` with
  `assert mock_config_entry.runtime_data.client is mock_client`.
- Delete `test_setup_errors` and `test_setup_auth_error_starts_reauth`; `test_coordinator.py` covers them
  now (`test_first_refresh_charger_errors`, `test_first_refresh_auth_error_starts_reauth`). Remove the
  imports they alone used.
- Add, after `test_unload_entry`:

```python
async def test_unload_stops_the_timers(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """After unload, neither the polling, the price time nor the tick reads anything."""
    await setup_integration(hass, mock_config_entry)
    # A listener keeps polling scheduled without entities (Task 2), so unload has something to stop.
    mock_config_entry.runtime_data.async_add_listener(lambda: None)
    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    freezer.tick(timedelta(days=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_client.get_price_forecast.await_count == 1
    assert mock_client.get_charger.await_count == 1


async def test_unload_cancels_a_price_read_in_flight(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A scheduled price read still running at unload is cancelled."""
    await setup_integration(hass, mock_config_entry)
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def _slow_forecast() -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    mock_client.get_price_forecast.side_effect = _slow_forecast
    mock_config_entry.runtime_data.async_start_price_read()
    await started.wait()
    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert cancelled.is_set()


async def test_remove_entry_removes_stored_prices(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    hass_storage: dict[str, Any],
) -> None:
    """Deleting the entry deletes its stored prices."""
    await setup_integration(hass, mock_config_entry)
    key = f"nortec_go.{mock_config_entry.entry_id}.prices"
    assert key in hass_storage
    assert await hass.config_entries.async_remove(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert key not in hass_storage
```

  Add the imports these need: `import asyncio`, `from datetime import timedelta`, `from typing import Any`,
  `from freezegun.api import FrozenDateTimeFactory`, and `async_fire_time_changed` from
  `pytest_homeassistant_custom_component.common`.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_coordinator.py tests/test_init.py -q`
Expected: FAIL (`ModuleNotFoundError: custom_components.nortec_go.coordinator`).

- [ ] **Step 4: Implement `coordinator.py`**

Create `custom_components/nortec_go/coordinator.py`:

```python
"""The Nortec Go coordinator: charger and car polling, price reads and the quarter-hour tick."""

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.typing import UNDEFINED
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from pynortecgo import (
    ApiError,
    AuthError,
    Charger,
    ChargerNotFoundError,
    ChargeState,
    MultipleVehiclesError,
    NortecGoClient,
    NortecGoConnectionError,
    NortecGoError,
    RateLimitError,
    UnexpectedResponseError,
    Vehicle,
    VehicleNotFoundError,
)

from .const import (
    DOMAIN,
    INTERVAL_CHARGING,
    INTERVAL_CONNECTED,
    INTERVAL_UNPLUGGED,
    PRICE_READ_HOURS,
    PRICE_READ_MINUTE,
    TICK_MINUTES,
)
from .entry import NortecGoConfigEntry
from .prices import KnownSlots, PriceStore, merge_forecast, prune

_LOGGER = logging.getLogger(__name__)

_CHARGE_UNDER_WAY = (ChargeState.STARTING, ChargeState.CHARGING, ChargeState.STOPPING)


@dataclass(frozen=True)
class NortecGoData:
    """One read of the charger and the car. vehicle is None until the car is read."""

    charger: Charger
    vehicle: Vehicle | None


def interval_for(charger: Charger) -> timedelta:
    """The next polling interval for this charger state (D22)."""
    if not charger.is_connected:
        return INTERVAL_UNPLUGGED
    if charger.charge_state in _CHARGE_UNDER_WAY:
        return INTERVAL_CHARGING
    return INTERVAL_CONNECTED


def car_device_identifier(charger_id: str) -> tuple[str, str]:
    """The car device's identifier, keyed on the charger (§2.1)."""
    return (DOMAIN, f"{charger_id}_car")


class NortecGoCoordinator(DataUpdateCoordinator[NortecGoData]):
    """Reads the charger and car on a state-based interval, and the prices on a schedule."""

    config_entry: NortecGoConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: NortecGoConfigEntry, client: NortecGoClient
    ) -> None:
        """Set up the coordinator for one entry."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=INTERVAL_CONNECTED,
            always_update=False,
        )
        assert entry.unique_id is not None  # the config flow always sets it
        self.client = client
        self.charger_id = entry.unique_id
        self.has_car = True
        self.known_prices: KnownSlots = {}
        self._car_checked = False
        self._car_failing = False
        self._vehicle: Vehicle | None = None
        self._price_store = PriceStore(hass, entry.entry_id)

    async def _async_update_data(self) -> NortecGoData:
        """Read the charger, then the car; set the next interval."""
        try:
            charger = await self.client.get_charger()
        except AuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except RateLimitError as err:
            raise UpdateFailed(str(err), retry_after=err.retry_after) from err
        except (NortecGoConnectionError, ApiError) as err:
            raise UpdateFailed(str(err)) from err
        except (ChargerNotFoundError, UnexpectedResponseError) as err:
            raise ConfigEntryError(str(err)) from err

        vehicle = await self._async_read_vehicle()
        self.update_interval = interval_for(charger)
        return NortecGoData(charger=charger, vehicle=vehicle)

    async def _async_read_vehicle(self) -> Vehicle | None:
        """Read the car; a car error never fails the update (§4.2)."""
        if not self.has_car:
            return None
        try:
            vehicle = await self.client.get_vehicle()
        except AuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except (VehicleNotFoundError, MultipleVehiclesError) as err:
            if not self._car_checked:
                self._car_checked = True
                self.has_car = False
                _LOGGER.info("No car entities: %s", err)
                return None
            self._log_car_error(err)
            return self._vehicle
        except NortecGoError as err:
            self._car_checked = True
            self._log_car_error(err)
            return self._vehicle

        self._car_checked = True
        if self._car_failing:
            self._car_failing = False
            _LOGGER.info("Reading the car works again")
        self._vehicle = vehicle
        self._async_update_car_device(vehicle)
        return vehicle

    def _log_car_error(self, err: NortecGoError) -> None:
        if not self._car_failing:
            self._car_failing = True
            _LOGGER.warning("Could not read the car; keeping its last data: %s", err)

    @callback
    def _async_update_car_device(self, vehicle: Vehicle) -> None:
        """Bring the car device's name, brand and model up to date (§2.1)."""
        registry = dr.async_get(self.hass)
        identifier = car_device_identifier(self.charger_id)
        if (
            registry.async_get_device_by_identifier(
                identifier, self.config_entry.entry_id
            )
            is None
        ):
            return  # the entities create the device
        # Updates the existing device; an empty name falls back to the translated "Car".
        registry.async_get_or_create(
            config_entry_id=self.config_entry.entry_id,
            identifiers={identifier},
            name=vehicle.name or UNDEFINED,
            translation_key=None if vehicle.name else "car",
            manufacturer=vehicle.brand or UNDEFINED,
            model=vehicle.model or UNDEFINED,
        )

    async def async_load_prices(self) -> None:
        """Load the stored slots, without yesterday's."""
        self.known_prices = prune(
            await self._price_store.async_load(),
            dt_util.utcnow(),
            dt_util.get_default_time_zone(),
        )

    async def async_read_prices(self, *, during_setup: bool = False) -> None:
        """Read the forecast, merge, prune and save it; keep the known slots on failure (§4.3)."""
        try:
            forecast = await self.client.get_price_forecast()
        except AuthError as err:
            if during_setup:
                raise ConfigEntryAuthFailed(str(err)) from err
            self.config_entry.async_start_reauth(self.hass)
            return
        except NortecGoError as err:
            _LOGGER.warning(
                "Could not read the price forecast; keeping the known prices: %s", err
            )
            return
        self.known_prices = prune(
            merge_forecast(self.known_prices, forecast),
            dt_util.utcnow(),
            dt_util.get_default_time_zone(),
        )
        await self._price_store.async_save(self.known_prices)
        self.async_update_listeners()

    @callback
    def async_start_price_read(self) -> None:
        """Start one price read as a background task that unload cancels."""
        self.config_entry.async_create_background_task(
            self.hass, self.async_read_prices(), f"{DOMAIN} price read"
        )

    @callback
    def async_start_timers(self) -> None:
        """Start the price reads and the quarter-hour tick; unload stops them."""

        @callback
        def _price_time(now: datetime) -> None:
            self.async_start_price_read()

        @callback
        def _tick(now: datetime) -> None:
            self.async_update_listeners()

        self.config_entry.async_on_unload(
            async_track_time_change(
                self.hass,
                _price_time,
                hour=PRICE_READ_HOURS,
                minute=PRICE_READ_MINUTE,
                second=0,
            )
        )
        self.config_entry.async_on_unload(
            async_track_time_change(self.hass, _tick, minute=TICK_MINUTES, second=0)
        )
```

- [ ] **Step 5: Update `entry.py`**

Replace the type alias and its import so the coordinator is imported only for type checking:

```python
from typing import TYPE_CHECKING, Any

...

if TYPE_CHECKING:
    from .coordinator import NortecGoCoordinator

type NortecGoConfigEntry = ConfigEntry[NortecGoCoordinator]
```

Remove `NortecGoClient` from the `pynortecgo` import only if nothing else in `entry.py` uses it
(`create_client` still does, so it stays). If ruff flags the `TYPE_CHECKING` import (TC004), move the alias
into `coordinator.py` instead and import `NortecGoConfigEntry` from there in `__init__.py`; keep
`entry.py`'s helpers where they are.

- [ ] **Step 6: Update `__init__.py`**

Replace the body of `async_setup_entry` after the client is built, and add `async_remove_entry`:

```python
    # Read the config flow's charger directly; a removed one raises ChargerNotFoundError.
    assert entry.unique_id is not None  # the config flow always sets it
    client.set_charger(int(entry.unique_id))

    coordinator = NortecGoCoordinator(hass, entry, client)
    await coordinator.async_load_prices()
    await coordinator.async_config_entry_first_refresh()
    await coordinator.async_read_prices(during_setup=True)
    coordinator.async_start_timers()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_remove_entry(hass: HomeAssistant, entry: NortecGoConfigEntry) -> None:
    """Delete the entry's stored prices."""
    await PriceStore(hass, entry.entry_id).async_remove()
```

Remove the old `try`/`except` around `get_charger()` and the exception imports only it used; import
`NortecGoCoordinator` from `.coordinator` and `PriceStore` from `.prices`. Keep the comment
"pynortecgo's messages hold no tokens, emails or IDs, so they may be passed on." by moving it to the top of
`coordinator.py`'s `_async_update_data`.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `uv run pytest tests/test_coordinator.py tests/test_init.py -q`
Expected: PASS. Then run the full gates. Coverage of `coordinator.py` must be 100%; if a branch is missed
(for example the early return in `_async_update_car_device`, hit by every test before Task 3 creates the
device), keep it and let the existing tests cover it.

- [ ] **Step 8: Commit**

`git add` the five files, then commit with `feat: coordinator for charger, car and prices (#8)` plus the
trailer.

---

### Task 3: Entities

**Model:** opus (the mapping of `pynortecgo` models to entities) · **Wave:** 3

**Files:**
- Create: `custom_components/nortec_go/entity.py`
- Create: `custom_components/nortec_go/sensor.py`
- Create: `custom_components/nortec_go/binary_sensor.py`
- Modify: `custom_components/nortec_go/__init__.py` (`PLATFORMS` only)
- Modify: `custom_components/nortec_go/strings.json`, `custom_components/nortec_go/translations/en.json`
- Create: `tests/test_sensor.py`, `tests/test_binary_sensor.py`

**Interfaces:**
- Consumes: Task 2's `NortecGoCoordinator` (`data`, `has_car`, `charger_id`, `known_prices`,
  `config_entry`), `car_device_identifier`, `NortecGoConfigEntry`; Task 1's `prices_today`,
  `prices_tomorrow`, `current_price` and fixtures.
- Produces: entity IDs used by the docs (Task 4), with the fixture names: `sensor.garage_charger_current_price`,
  `binary_sensor.garage_charger_cable_connected`, `binary_sensor.garage_charger_charging`,
  `sensor.family_car_battery`, `sensor.family_car_charge_limit`, `sensor.family_car_last_seen`,
  `binary_sensor.family_car_plugged_in`, `binary_sensor.family_car_connected_to_charger`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sensor.py`:

```python
"""Tests for the Nortec Go sensors."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.sensor import (
    ATTR_STATE_CLASS,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_UNIT_OF_MEASUREMENT,
    PERCENTAGE,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    EntityCategory,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pynortecgo import NortecGoConnectionError, VehicleNotFoundError
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.nortec_go.const import DOMAIN, MISSING_SLOT_PRICE

from .conftest import (
    FAKE_CHARGER_ID,
    FAKE_LAST_SEEN,
    make_charger,
    make_forecast,
    make_vehicle,
    setup_integration,
)

MIDNIGHT = datetime(2026, 9, 26, 22, 0, tzinfo=UTC)  # 00:00 local on 27 Sep
PRICE = "sensor.garage_charger_current_price"


@pytest.fixture(autouse=True)
async def copenhagen(hass: HomeAssistant) -> None:
    """Run every test in the owner's time zone, with DKK."""
    await hass.config.async_set_time_zone("Europe/Copenhagen")
    hass.config.currency = "DKK"


async def test_current_price(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """State is the current slot's price; attributes are the two lists; unit is DKK/kWh."""
    freezer.move_to(MIDNIGHT + timedelta(minutes=20))  # 00:20 local
    mock_client.get_price_forecast.return_value = make_forecast(
        MIDNIGHT, [1.0, 2.0, 3.0]
    )
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(PRICE)
    assert state is not None
    assert state.state == "2.0"
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == "DKK/kWh"
    assert state.attributes[ATTR_STATE_CLASS] == SensorStateClass.MEASUREMENT
    assert ATTR_DEVICE_CLASS not in state.attributes
    today = state.attributes["prices_today"]
    assert len(today) == 96
    assert today[2]["price"] == 3.0
    assert state.attributes["prices_tomorrow"] == []


async def test_current_price_follows_the_tick(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """At :15 the state moves to the next slot without an API call."""
    freezer.move_to(MIDNIGHT + timedelta(minutes=10))
    mock_client.get_price_forecast.return_value = make_forecast(MIDNIGHT, [1.0, 2.0])
    await setup_integration(hass, mock_config_entry)
    assert hass.states.get(PRICE).state == "1.0"  # type: ignore[union-attr]

    when = MIDNIGHT + timedelta(minutes=15)
    freezer.move_to(when)
    async_fire_time_changed(hass, when)
    await hass.async_block_till_done()
    assert hass.states.get(PRICE).state == "2.0"  # type: ignore[union-attr]
    assert mock_client.get_price_forecast.await_count == 1


async def test_current_price_with_nothing_known(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Late evening, no stored prices, forecast failing: available, unknown, 96 padded slots."""
    freezer.move_to(MIDNIGHT + timedelta(hours=21, minutes=30))  # 21:30 local
    mock_client.get_price_forecast.side_effect = NortecGoConnectionError("network down")
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(PRICE)
    assert state is not None
    assert state.state == STATE_UNKNOWN
    today = state.attributes["prices_today"]
    assert len(today) == 96
    assert today[-1]["price"] == MISSING_SLOT_PRICE


async def test_current_price_stays_available_when_charger_fails(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A failing charger read leaves Current price and its lists in place."""
    freezer.move_to(MIDNIGHT + timedelta(minutes=5))
    mock_client.get_price_forecast.return_value = make_forecast(MIDNIGHT, [1.0])
    await setup_integration(hass, mock_config_entry)

    mock_client.get_charger.side_effect = NortecGoConnectionError("network down")
    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    state = hass.states.get(PRICE)
    assert state is not None
    assert state.state == "1.0"
    assert len(state.attributes["prices_today"]) == 96
    assert hass.states.get("sensor.family_car_battery").state == STATE_UNAVAILABLE  # type: ignore[union-attr]
    cable = hass.states.get("binary_sensor.garage_charger_cable_connected")
    assert cable is not None
    assert cable.state == STATE_UNAVAILABLE


def test_price_lists_not_recorded() -> None:
    """The recorder leaves the two lists out."""
    from custom_components.nortec_go.sensor import NortecGoPriceSensor  # noqa: PLC0415

    assert {
        "prices_today",
        "prices_tomorrow",
    } <= NortecGoPriceSensor._unrecorded_attributes  # noqa: SLF001


async def test_car_sensors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Battery, Charge limit and Last seen on the car device."""
    await setup_integration(hass, mock_config_entry)

    battery = hass.states.get("sensor.family_car_battery")
    assert battery is not None
    assert battery.state == "55.0"
    assert battery.attributes[ATTR_DEVICE_CLASS] == SensorDeviceClass.BATTERY
    assert battery.attributes[ATTR_UNIT_OF_MEASUREMENT] == PERCENTAGE
    limit = hass.states.get("sensor.family_car_charge_limit")
    assert limit is not None
    assert limit.state == "80.0"
    assert ATTR_DEVICE_CLASS not in limit.attributes
    seen = hass.states.get("sensor.family_car_last_seen")
    assert seen is not None
    assert seen.state == FAKE_LAST_SEEN.isoformat()
    entry = entity_registry.async_get("sensor.family_car_last_seen")
    assert entry is not None
    assert entry.entity_category is EntityCategory.DIAGNOSTIC
    assert entry.unique_id == f"{FAKE_CHARGER_ID}_last_seen"


async def test_car_values_unknown(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A car that reports nothing shows unknown, not unavailable."""
    mock_client.get_vehicle.return_value = make_vehicle(
        battery_level=None, charge_limit=None, plugged_in=None, last_seen=None
    )
    await setup_integration(hass, mock_config_entry)
    for entity_id in (
        "sensor.family_car_battery",
        "sensor.family_car_charge_limit",
        "sensor.family_car_last_seen",
    ):
        assert hass.states.get(entity_id).state == STATE_UNKNOWN, entity_id  # type: ignore[union-attr]


def _device(
    device_registry: dr.DeviceRegistry, entry: MockConfigEntry, identifier: str
) -> dr.DeviceEntry | None:
    return device_registry.async_get_device_by_identifier(
        (DOMAIN, identifier), entry.entry_id
    )


async def test_devices(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    device_registry: dr.DeviceRegistry,
) -> None:
    """A charger device and a separate car device, not linked."""
    await setup_integration(hass, mock_config_entry)
    charger = _device(device_registry, mock_config_entry, str(FAKE_CHARGER_ID))
    car = _device(device_registry, mock_config_entry, f"{FAKE_CHARGER_ID}_car")
    assert charger is not None
    assert (charger.name, charger.manufacturer) == ("Garage charger", "Nortec")
    assert car is not None
    assert (car.name, car.manufacturer, car.model) == (
        "Family car",
        "Example",
        "Model E",
    )
    assert car.via_device_id is None


async def test_device_name_fallbacks(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    device_registry: dr.DeviceRegistry,
) -> None:
    """An empty charger name uses the entry title; an empty car name becomes "Car"."""
    mock_client.get_charger.return_value = make_charger(name="")
    await setup_integration(hass, mock_config_entry)
    charger = _device(device_registry, mock_config_entry, str(FAKE_CHARGER_ID))
    assert charger is not None
    assert charger.name == mock_config_entry.title

    mock_client.get_vehicle.return_value = make_vehicle(name="")
    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    car = _device(device_registry, mock_config_entry, f"{FAKE_CHARGER_ID}_car")
    assert car is not None
    assert car.name == "Car"


async def test_car_placeholder_until_first_read(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    device_registry: dr.DeviceRegistry,
) -> None:
    """A car read failing at setup: device "Car", entities unavailable; a good read fixes both."""
    mock_client.get_vehicle.side_effect = NortecGoConnectionError("network down")
    await setup_integration(hass, mock_config_entry)
    car = _device(device_registry, mock_config_entry, f"{FAKE_CHARGER_ID}_car")
    assert car is not None
    assert car.name == "Car"
    assert hass.states.get("sensor.car_battery").state == STATE_UNAVAILABLE  # type: ignore[union-attr]

    mock_client.get_vehicle.side_effect = None
    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    updated = device_registry.async_get(car.id, include_child_devices=False)
    assert updated is not None
    assert updated.name == "Family car"
    assert hass.states.get("sensor.car_battery").state == "55.0"  # type: ignore[union-attr]


async def test_no_car_no_car_entities(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    device_registry: dr.DeviceRegistry,
) -> None:
    """No car on the account: no car device and no car entities."""
    mock_client.get_vehicle.side_effect = VehicleNotFoundError("no car")
    await setup_integration(hass, mock_config_entry)
    assert _device(device_registry, mock_config_entry, f"{FAKE_CHARGER_ID}_car") is None
    assert hass.states.get(PRICE) is not None
    for entity_id in (
        "sensor.family_car_battery",
        "sensor.family_car_charge_limit",
        "sensor.family_car_last_seen",
        "binary_sensor.family_car_plugged_in",
        "binary_sensor.family_car_connected_to_charger",
    ):
        assert hass.states.get(entity_id) is None, entity_id
```

Create `tests/test_binary_sensor.py`:

```python
"""Tests for the Nortec Go binary sensors."""

from unittest.mock import AsyncMock

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import ATTR_DEVICE_CLASS, STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from pynortecgo import ChargeState
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import make_charger, make_vehicle, setup_integration


@pytest.mark.parametrize(
    ("charge_state", "charging"),
    [
        (None, STATE_OFF),
        (ChargeState.STARTING, STATE_OFF),
        (ChargeState.CHARGING, STATE_ON),
        (ChargeState.PAUSED, STATE_OFF),
    ],
)
async def test_charger_binary_sensors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    charge_state: ChargeState | None,
    charging: str,
) -> None:
    """Cable connected and Charging follow the charger."""
    mock_client.get_charger.return_value = make_charger(
        is_connected=True, charge_state=charge_state
    )
    await setup_integration(hass, mock_config_entry)

    cable = hass.states.get("binary_sensor.garage_charger_cable_connected")
    assert cable is not None
    assert cable.state == STATE_ON
    assert cable.attributes[ATTR_DEVICE_CLASS] == BinarySensorDeviceClass.PLUG
    state = hass.states.get("binary_sensor.garage_charger_charging")
    assert state is not None
    assert state.state == charging
    assert (
        state.attributes[ATTR_DEVICE_CLASS] == BinarySensorDeviceClass.BATTERY_CHARGING
    )


@pytest.mark.parametrize(
    ("is_connected", "plugged_in", "plugged", "connected"),
    [
        (False, True, STATE_ON, STATE_OFF),
        (False, None, STATE_UNKNOWN, STATE_OFF),
        (True, True, STATE_ON, STATE_ON),
        (True, False, STATE_OFF, STATE_OFF),
        (True, None, STATE_UNKNOWN, STATE_UNKNOWN),
    ],
)
async def test_car_binary_sensors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    is_connected: bool,
    plugged_in: bool | None,
    plugged: str,
    connected: str,
) -> None:
    """Plugged in follows the car; Connected to charger needs the cable and the car."""
    mock_client.get_charger.return_value = make_charger(is_connected=is_connected)
    mock_client.get_vehicle.return_value = make_vehicle(plugged_in=plugged_in)
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get("binary_sensor.family_car_plugged_in")
    assert state is not None
    assert state.state == plugged
    state = hass.states.get("binary_sensor.family_car_connected_to_charger")
    assert state is not None
    assert state.state == connected
    assert state.attributes[ATTR_DEVICE_CLASS] == BinarySensorDeviceClass.PLUG
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_sensor.py tests/test_binary_sensor.py -q`
Expected: FAIL (no entities: `PLATFORMS` is empty).

- [ ] **Step 3: Implement `entity.py`**

```python
"""Base entities for the Nortec Go charger and car devices."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import NortecGoCoordinator, car_device_identifier


class NortecGoEntity(CoordinatorEntity[NortecGoCoordinator]):
    """An entity with a translated name and the unique ID <charger id>_<key>."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: NortecGoCoordinator, key: str) -> None:
        """Name the entity by its key."""
        super().__init__(coordinator)
        self._attr_translation_key = key
        self._attr_unique_id = f"{coordinator.charger_id}_{key}"


class NortecGoChargerEntity(NortecGoEntity):
    """An entity on the charger device."""

    def __init__(self, coordinator: NortecGoCoordinator, key: str) -> None:
        """Attach the entity to the charger device."""
        super().__init__(coordinator, key)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.charger_id)},
            name=coordinator.data.charger.name or coordinator.config_entry.title,
            manufacturer="Nortec",
        )


class NortecGoCarEntity(NortecGoEntity):
    """An entity on the car device; unavailable until the car has been read."""

    def __init__(self, coordinator: NortecGoCoordinator, key: str) -> None:
        """Attach the entity to the car device, named "Car" until the car is known."""
        super().__init__(coordinator, key)
        vehicle = coordinator.data.vehicle
        device_info = DeviceInfo(
            identifiers={car_device_identifier(coordinator.charger_id)}
        )
        if vehicle is not None and vehicle.name:
            device_info["name"] = vehicle.name
        else:
            device_info["translation_key"] = "car"
        if vehicle is not None and vehicle.brand:
            device_info["manufacturer"] = vehicle.brand
        if vehicle is not None and vehicle.model:
            device_info["model"] = vehicle.model
        self._attr_device_info = device_info

    @property
    def available(self) -> bool:
        """Available when the last update worked and the car has been read."""
        return super().available and self.coordinator.data.vehicle is not None
```

- [ ] **Step 4: Implement `sensor.py`**

```python
"""Nortec Go sensors: the price for EV Smart Charging and the car's values."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util
from pynortecgo import Vehicle

from .coordinator import NortecGoCoordinator
from .entity import NortecGoCarEntity, NortecGoChargerEntity
from .entry import NortecGoConfigEntry
from .prices import current_price, prices_today, prices_tomorrow

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class NortecGoCarSensorDescription(SensorEntityDescription):
    """A car sensor and how to read it from the car."""

    value_fn: Callable[[Vehicle], StateType | datetime]


CAR_SENSORS: tuple[NortecGoCarSensorDescription, ...] = (
    NortecGoCarSensorDescription(
        key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda vehicle: vehicle.battery_level,
    ),
    NortecGoCarSensorDescription(
        key="charge_limit",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda vehicle: vehicle.charge_limit,
    ),
    NortecGoCarSensorDescription(
        key="last_seen",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda vehicle: vehicle.last_seen,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NortecGoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the price sensor, and the car sensors when the account has a car."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [NortecGoPriceSensor(coordinator)]
    if coordinator.has_car:
        entities.extend(
            NortecGoCarSensor(coordinator, description) for description in CAR_SENSORS
        )
    async_add_entities(entities)


class NortecGoPriceSensor(NortecGoChargerEntity, SensorEntity):
    """The current price, with EV Smart Charging's day lists (§3.4)."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _unrecorded_attributes = frozenset({"prices_today", "prices_tomorrow"})

    def __init__(self, coordinator: NortecGoCoordinator) -> None:
        """Set the unit from Home Assistant's currency."""
        super().__init__(coordinator, "current_price")
        self._attr_native_unit_of_measurement = (
            f"{coordinator.hass.config.currency}/kWh"
        )

    @property
    def available(self) -> bool:
        """Always available, so the lists are always there (§4.4)."""
        return True

    @property
    def native_value(self) -> float | None:
        """The known price of the current slot."""
        return current_price(self.coordinator.known_prices, dt_util.utcnow())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """prices_today and prices_tomorrow in EV Smart Charging's format."""
        now = dt_util.utcnow()
        time_zone = dt_util.get_default_time_zone()
        known = self.coordinator.known_prices
        return {
            "prices_today": prices_today(known, now, time_zone),
            "prices_tomorrow": prices_tomorrow(known, now, time_zone),
        }


class NortecGoCarSensor(NortecGoCarEntity, SensorEntity):
    """A sensor for one of the car's values."""

    entity_description: NortecGoCarSensorDescription

    def __init__(
        self,
        coordinator: NortecGoCoordinator,
        description: NortecGoCarSensorDescription,
    ) -> None:
        """Set up the sensor from its description."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType | datetime:
        """The car's value, or None when the car doesn't report it."""
        vehicle = self.coordinator.data.vehicle
        return None if vehicle is None else self.entity_description.value_fn(vehicle)
```

- [ ] **Step 5: Implement `binary_sensor.py`**

```python
"""Nortec Go binary sensors: the charger's cable and charge, and the car's plug."""

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pynortecgo import Charger, ChargeState, Vehicle

from .coordinator import NortecGoCoordinator
from .entity import NortecGoCarEntity, NortecGoChargerEntity
from .entry import NortecGoConfigEntry

PARALLEL_UPDATES = 0


def connected_to_charger(charger: Charger, vehicle: Vehicle) -> bool | None:
    """Our car at our charger: the cable is connected and the car says it's plugged in."""
    if not charger.is_connected:
        return False
    return vehicle.plugged_in


@dataclass(frozen=True, kw_only=True)
class NortecGoChargerBinarySensorDescription(BinarySensorEntityDescription):
    """A charger binary sensor and how to read it."""

    value_fn: Callable[[Charger], bool | None]


@dataclass(frozen=True, kw_only=True)
class NortecGoCarBinarySensorDescription(BinarySensorEntityDescription):
    """A car binary sensor and how to read it from the charger and the car."""

    value_fn: Callable[[Charger, Vehicle], bool | None]


CHARGER_BINARY_SENSORS: tuple[NortecGoChargerBinarySensorDescription, ...] = (
    NortecGoChargerBinarySensorDescription(
        key="cable_connected",
        device_class=BinarySensorDeviceClass.PLUG,
        value_fn=lambda charger: charger.is_connected,
    ),
    NortecGoChargerBinarySensorDescription(
        key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda charger: charger.charge_state is ChargeState.CHARGING,
    ),
)

CAR_BINARY_SENSORS: tuple[NortecGoCarBinarySensorDescription, ...] = (
    NortecGoCarBinarySensorDescription(
        key="plugged_in",
        device_class=BinarySensorDeviceClass.PLUG,
        value_fn=lambda charger, vehicle: vehicle.plugged_in,
    ),
    NortecGoCarBinarySensorDescription(
        key="connected_to_charger",
        device_class=BinarySensorDeviceClass.PLUG,
        value_fn=connected_to_charger,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NortecGoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the charger binary sensors, and the car ones when the account has a car."""
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [
        NortecGoChargerBinarySensor(coordinator, description)
        for description in CHARGER_BINARY_SENSORS
    ]
    if coordinator.has_car:
        entities.extend(
            NortecGoCarBinarySensor(coordinator, description)
            for description in CAR_BINARY_SENSORS
        )
    async_add_entities(entities)


class NortecGoChargerBinarySensor(NortecGoChargerEntity, BinarySensorEntity):
    """A binary sensor on the charger."""

    entity_description: NortecGoChargerBinarySensorDescription

    def __init__(
        self,
        coordinator: NortecGoCoordinator,
        description: NortecGoChargerBinarySensorDescription,
    ) -> None:
        """Set up the binary sensor from its description."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """The charger's value."""
        return self.entity_description.value_fn(self.coordinator.data.charger)


class NortecGoCarBinarySensor(NortecGoCarEntity, BinarySensorEntity):
    """A binary sensor on the car."""

    entity_description: NortecGoCarBinarySensorDescription

    def __init__(
        self,
        coordinator: NortecGoCoordinator,
        description: NortecGoCarBinarySensorDescription,
    ) -> None:
        """Set up the binary sensor from its description."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """The value from the charger and the car, or None before the car is read."""
        vehicle = self.coordinator.data.vehicle
        if vehicle is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data.charger, vehicle)
```

- [ ] **Step 6: Platforms and strings**

In `__init__.py`: `PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]`.

In `strings.json`, add after the `"config"` object (and copy the whole file to `translations/en.json`):

```json
  "device": {
    "car": {
      "name": "Car"
    }
  },
  "entity": {
    "binary_sensor": {
      "cable_connected": { "name": "Cable connected" },
      "charging": { "name": "Charging" },
      "plugged_in": { "name": "Plugged in" },
      "connected_to_charger": { "name": "Connected to charger" }
    },
    "sensor": {
      "current_price": { "name": "Current price" },
      "battery": { "name": "Battery" },
      "charge_limit": { "name": "Charge limit" },
      "last_seen": { "name": "Last seen" }
    }
  }
```

Format both files the way the existing `strings.json` is formatted (two-space indent, one key per line).

- [ ] **Step 7: Run the tests to verify they pass**

Run: `uv run pytest tests/test_sensor.py tests/test_binary_sensor.py -q`, then the full gates. Earlier tests
that set up the entry now also create entities; they must still pass.

- [ ] **Step 8: Commit**

`git add` the eight files, then commit with `feat: sensors and binary sensors for EV Smart Charging (#8)`
plus the trailer.

---

### Task 4: Quality scale, user docs, changelog, decisions and labels

**Model:** sonnet · **Wave:** 1 (docs, starting ahead of inputs from the names this plan fixes)

**Files:**
- Modify: `custom_components/nortec_go/quality_scale.yaml`
- Modify: `docs/user/nortec_go.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/decisions.md`
- Modify: `docs/way-of-working.md`

**Interfaces:**
- Consumes: the names fixed in this plan: device names (the charger's name; the car's name or "Car"),
  entity names in Task 3 Step 6, the intervals and price times in *Global Constraints*.
- Produces: docs only.

- [ ] **Step 1: Quality scale**

In `custom_components/nortec_go/quality_scale.yaml`, change these rules from `todo` to `done`:
`appropriate-polling`, `common-modules`, `entity-unique-id`, `has-entity-name`, `entity-unavailable`,
`log-when-unavailable`, `parallel-updates`, `devices`, `entity-device-class`, `entity-category`,
`entity-translations`, `docs-data-update`, `docs-supported-functions`, `docs-supported-devices`,
`docs-use-cases`, `docs-examples`. Change `entity-event-setup` to:

```yaml
  entity-event-setup:
    status: exempt
    comment: "Entities subscribe to no events; the coordinator owns the timers."
```

Run `uv run pytest tests/test_quality_scale.py -q`: PASS.

- [ ] **Step 2: User docs**

In `docs/user/nortec_go.md`:

- *Supported devices*: replace "Not available yet." with:

  ```markdown
  - A charger on a Nortec Go account.
  - The car linked to that account.
  ```

- *Unsupported devices*: replace "Not available yet." with "An account with more than one charger. With more
  than one car, the integration works without car entities."
- *Prerequisites*: replace the text with: "You need a Nortec Go account with exactly one charger. A car is
  optional: without one there is no car device. A car added later appears after you reload the integration."
- *Supported functionality*: replace "Not available yet." with two tables, one per device:

  ```markdown
  The integration adds two devices: the charger, and the car when the account has one.

  ### Charger

  | Entity | Type | Description |
  |---|---|---|
  | Current price | Sensor | The spot price for the current 15 minutes, per kWh, incl. VAT. Its `prices_today` and `prices_tomorrow` attributes are in the format EV Smart Charging reads |
  | Cable connected | Binary sensor | On when a cable is connected to the charger |
  | Charging | Binary sensor | On while the car draws power |

  ### Car

  | Entity | Type | Description |
  |---|---|---|
  | Battery | Sensor | The car's state of charge, in % |
  | Charge limit | Sensor | The charge limit set in the car, in % |
  | Last seen | Sensor (diagnostic) | When the car last reported its data |
  | Plugged in | Binary sensor | On when the car reports that it's plugged in, at any charger |
  | Connected to charger | Binary sensor | On when the charger's cable is connected and the car reports it's plugged in |

  Values the car doesn't report show as unknown. Until the car has been read once, the car device is called
  *Car* and its entities are unavailable.
  ```

- Add a new section *Use cases* after *Supported functionality*:

  ```markdown
  ## Use cases

  ### Smart charging with EV Smart Charging

  [EV Smart Charging](https://github.com/jonasbkarlsson/ev_smart_charging) plans charging in the cheapest
  hours. Set it up with these entities:

  | EV Smart Charging setting | Entity |
  |---|---|
  | Electricity price entity | Current price |
  | EV SOC entity | Battery |
  | EV target SOC entity | Charge limit |
  | EV connected entity | Connected to charger |

  *Connected to charger* is on only when your own car is at your charger. A guest car plugged into the
  charger leaves it off, so EV Smart Charging leaves the charger alone and the guest charges normally.
  ```

- *Automation examples*: replace "Not available yet." with:

  ````markdown
  ### Read the charger when you get home

  The charger is read once an hour while no cable is connected. To see a plugged-in car sooner, read it
  when you arrive:

  ```yaml
  automation:
    - alias: "Read the Nortec Go charger when I get home"
      triggers:
        - trigger: zone
          entity_id: person.me
          zone: zone.home
          event: enter
      actions:
        - delay: "00:05:00"
        - action: homeassistant.update_entity
          target:
            entity_id: binary_sensor.garage_charger_cable_connected
  ```

  Replace `person.me` and the entity ID with your own.
  ````

- *Data updates*: replace "Not available yet." with:

  ```markdown
  The integration reads the charger and the car:

  - every 60 minutes while no cable is connected,
  - every 15 minutes while a cable is connected,
  - every 5 minutes while a charge is starting, running or stopping.

  It reads the price forecast when it starts and at 00:05, 05:05, 10:05, 15:05 and 20:05. The current price
  moves to the next 15 minutes by itself, without a read.

  To read the charger and the car now, call the `homeassistant.update_entity` action on any Nortec Go entity
  (see *Automation examples*). It doesn't read the prices.
  ```

- *Known limitations*: remove the "No entities yet…" bullet and add:

  ```markdown
  - The price is the spot price including VAT, without fees or grid tariff, so it isn't what you pay in
    total.
  - The price is assumed to be in the currency set in Home Assistant. This has been checked only for DKK.
  - Tomorrow's prices are a forecast until the day-ahead prices come out, around 13:00; the 15:05 read
    replaces them.
  - Car data can be hours old (see *Last seen*), so *Connected to charger* can turn on late.
  - Days and the price times follow Home Assistant's time zone.
  - A car removed from the account stays until you reload the integration.
  ```

- [ ] **Step 3: Changelog**

In `CHANGELOG.md`, under *Unreleased → Added*, add:

```markdown
- Sensors and binary sensors for [EV Smart Charging](https://github.com/jonasbkarlsson/ev_smart_charging):
  the current price with today's and tomorrow's prices, the car's battery and charge limit, and whether
  your own car is connected to the charger.
```

- [ ] **Step 4: Decisions**

Append to `docs/decisions.md`:

```markdown

### D22: State-based polling, no polling settings
- **Date:** 2026-09-26 · **Status:** active
- **Decision:** The charger and car are read every 60 min unplugged, 15 min connected and 5 min while a
  charge is under way; prices at setup and at 00:05, 05:05, 10:05, 15:05 and 20:05. There is no options flow
  and no refresh button; `homeassistant.update_entity` reads the charger and car now.
- **Why:** Reads match how fast things change (the car mostly stands unplugged), and Home Assistant doesn't
  allow integrations to offer polling settings.
- **Source:** [read-only entities spec](superpowers/specs/2026-09-26-read-only-entities-design.md), Decisions

### D23: Padded price lists, predictions kept, prices stored
- **Date:** 2026-09-26 · **Status:** active
- **Decision:** EV Smart Charging's lists are padded to full days: 0 for a missing past slot, 10 for a
  missing current or future slot, and `[]` when no slot of tomorrow is known. Predicted prices are shown and
  replaced by later reads. Known slots are saved with Home Assistant's `Store`.
- **Why:** The API has no earlier hours of today and EV Smart Charging rejects a short day. Past prices never
  affect a plan, a high price keeps it away from unknown slots, and a forecast beats no prices.
- **Source:** [read-only entities spec](superpowers/specs/2026-09-26-read-only-entities-design.md), §3.3–3.4

### D24: Version labels on issues
- **Date:** 2026-09-26 · **Status:** active
- **Decision:** Each issue gets one of `v1` (needed for version 1), `v2` (can wait for version 2) or
  `enhancement` (an improvement with no version decided). Chores may have none. When in doubt, ask the owner.
- **Why:** Not every issue is an enhancement; the labels show what v1 needs.
- **Source:** owner request on 2026-09-26
```

- [ ] **Step 5: Way of working**

In `docs/way-of-working.md` §6, after the *Backlog* bullet, add:

```markdown
- **Labels:** each issue gets `v1`, `v2` or `enhancement`; chores may have none. When in doubt, ask the owner
  (D24).
```

- [ ] **Step 6: Check and commit**

Run the gates (only the quality-scale test is affected). `git add` the five files and commit with
`docs: quality scale, user docs, changelog and decisions D22-D24 (#8)` plus the trailer.
