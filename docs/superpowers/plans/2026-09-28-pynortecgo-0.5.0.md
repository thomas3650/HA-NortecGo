# pynortecgo 0.5.0: total price and the forecast's currency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. In this repo the flow in `docs/way-of-working.md` §1–2 applies (implementer and task-reviewer agents, waves, worktrees).

**Goal:** The integration runs on `pynortecgo` 0.5.0: the price is the total price in the forecast's currency, the old stored spot prices are dropped once, and a charge the car paused counts as open in every state the client treats as one.

**Architecture:** Task 1 bumps the pin and makes the test fixtures build 0.5.0 models. Then three disjoint tasks run in parallel: `charge_is_open` learns `BUSY_NON_CHARGING` (Task 2); the price store goes to version 2 with the currency, the coordinator keeps `price_currency`, and the price sensor's unit follows it (Task 3); the docs, changelog and decision log follow (Task 4).

**Tech Stack:** Python 3.14, Home Assistant custom integration, `pynortecgo` 0.5.0 (always mocked in tests), pytest with `pytest-homeassistant-custom-component` and freezegun, uv.

**Spec:** `docs/superpowers/specs/2026-09-28-pynortecgo-0.5.0-design.md` (issues #33, #20).

## Global Constraints

- TDD: write the failing test, see it fail, then the code. Tests always mock `pynortecgo`; fixtures come from `pynortecgo` model objects and `tests/conftest.py` helpers, never raw API JSON (hard rules 2, 7).
- Never start or stop a real charge (hard rule 2). Never retry `start_charge` (hard rule 6).
- Nothing private (hard rule 3): no IDs, tokens, emails, captures, raw endpoints, response shapes or links into the private client repo. Name only `pynortecgo`'s public API.
- Gates before every commit (`CLAUDE.md` → Commands): `uv run pytest -q`, `uv run ruff check && uv run ruff format --check && uv run mypy`; the coverage gate (`--cov-fail-under=95`) passes at the end of each task.
- Subagents write commit messages with the Write tool to a file outside the repo and commit with `git commit -F <file>` (no heredocs). End each message with the co-author trailer given in the dispatch.
- Match the surrounding code: comment density, one-line docstrings ending in a period, names. Exception tuples use the repo's Python 3.14 form `except KeyError, TypeError, ValueError:`.
- Pin: `pynortecgo==0.5.0`, in `manifest.json` and `pyproject.toml` (`tests/test_manifest.py` checks they match).
- The price is the total per kWh incl. VAT (`PriceSlot.price`); `PriceSlot.spot_price` and `PriceSlot.tariff_estimated` are not used in `custom_components/`.
- Price store: `PRICE_STORE_VERSION = 2`; data `{"currency": str | None, "slots": [{"start": <ISO>, "price": <float>}]}`; a version 1 file migrates to `{"currency": None, "slots": []}`.
- The charge-control store stays at version 1; its test data in `tests/test_init.py` doesn't change.
- Decision number: D34.

## Review Focus

1. The owner's dev config has a version 1 price store: setup must load the entry, save the store back as version 2 and refill the slots from the forecast (Task 3 test `test_version_1_store_migrates_at_setup`).
2. The first forecast ever read has `currency=None` and nothing is stored: the unit is Home Assistant's currency, not `None/kWh` (Task 3 test `test_price_unit_falls_back_to_home_assistant_currency`).
3. A stored currency of the wrong type (a number): the stored data is ignored with the warning, no crash (Task 3, a `test_store_wrong_shape` case).
4. A charge the car paused, seen through the whole integration: *Charge* on, *Charge status* `paused`, *Charging* off (Task 2 test `test_car_paused_charge_entities`).
5. `BUSY_NON_CHARGING` with no charge state: turning *Charge* on sends no start, so no card hold (Task 2 test `test_start_noop_while_busy_non_charging`).

## Waves

| Wave | Tasks | Notes |
|---|---|---|
| 1 | Task 1 (bump and fixtures) | Everything else needs 0.5.0 installed and the fixtures |
| 2 | Task 2 (paused charge), Task 3 (price store and currency), Task 4 (docs) | Disjoint files: three worktrees off the feature branch after Task 1. Task 4 is written against the names this plan fixes |

No task has guarded files.

---

### Task 1: Bump to 0.5.0 and the fixtures

**Model:** sonnet — a pin bump and test fixtures.
**Wave:** 1

**Files:**
- Modify: `custom_components/nortec_go/manifest.json` (line 11), `pyproject.toml` (line 15), `uv.lock`
- Modify: `tests/conftest.py` (`make_charger`, `make_forecast`)
- Test: `tests/test_prices.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `make_charger(...)` builds `Charger` with `charge_kwh=None, charge_kw=None` (signature unchanged). `make_forecast(start: datetime, prices: Sequence[float], currency: str | None = "DKK") -> PriceForecast`; each slot has `spot_price=price - 0.5` and `tariff_estimated=False`.

- [ ] **Step 1: Bump the pins and the lock**

In `pyproject.toml` change `"pynortecgo==0.2.0",` to `"pynortecgo==0.5.0",`. In `custom_components/nortec_go/manifest.json` change `"requirements": ["pynortecgo==0.2.0"],` to `"requirements": ["pynortecgo==0.5.0"],`. Then:

Run: `uv lock --upgrade-package pynortecgo && uv sync`
Expected: `uv.lock` pins `pynortecgo` 0.5.0; `uv run python -c "import importlib.metadata as m; print(m.version('pynortecgo'))"` prints `0.5.0`.

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest -q -x`
Expected: FAIL with `TypeError` about missing arguments `charge_kwh` / `charge_kw` (from `make_charger`) or `currency` / `spot_price` / `tariff_estimated` (from `make_forecast`).

- [ ] **Step 3: Update the fixtures**

In `tests/conftest.py`, in `make_charger`'s `Charger(...)` call, after `can_stop=...`, add:

```text
        charge_kwh=None,
        charge_kw=None,
```

Replace `make_forecast` with:

```python
def make_forecast(
    start: datetime, prices: Sequence[float], currency: str | None = "DKK"
) -> PriceForecast:
    """Return 15-minute slots from start, one per total price; the spot price is 0.5 less."""
    step = timedelta(minutes=15)
    return PriceForecast(
        area_id=99,
        area_name="Test area",
        currency=currency,
        slots=[
            PriceSlot(
                start=start + i * step,
                end=start + (i + 1) * step,
                price=price,
                spot_price=price - 0.5,
                tariff_estimated=False,
            )
            for i, price in enumerate(prices)
        ],
    )
```

- [ ] **Step 4: Pin that the total is stored**

In `tests/test_prices.py`, after `test_merge_normalises_to_utc`, add:

```python
def test_merge_stores_the_total_price() -> None:
    """A slot's total price is stored, not its spot price (D34)."""
    forecast = make_forecast(MIDNIGHT, [2.0])
    assert forecast.slots[0].spot_price != 2.0
    assert merge_forecast({}, forecast) == {MIDNIGHT: 2.0}
```

(`merge_forecast` already stores `slot.price`; this test pins its meaning, so it passes at once.)

- [ ] **Step 5: Run all gates**

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95 -q`
Expected: all pass. If `mypy` reports an error in `custom_components/` from the new client, stop and report it (the spec found no API change the code uses).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock custom_components/nortec_go/manifest.json tests/conftest.py tests/test_prices.py
git commit -F <message file>   # "chore: bump pynortecgo to 0.5.0 (#33)"
```

---

### Task 2: A charge the car paused

**Model:** opus — near charge start and stop, and the start guard.
**Wave:** 2

**Files:**
- Modify: `custom_components/nortec_go/charge_control.py:87-92` (`charge_is_open`)
- Test: `tests/test_charge_control.py`, new `tests/test_car_pause.py`

**Interfaces:**
- Consumes: Task 1's fixtures; `ChargerState.BUSY_NON_CHARGING` from `pynortecgo` 0.5.0.
- Produces: `charge_is_open(charger: Charger) -> bool` (same signature), true also for `ChargerState.BUSY_NON_CHARGING`.

- [ ] **Step 1: Write the failing test**

In `tests/test_charge_control.py`, in `test_charge_is_open`'s parametrize list, after the `BUSY_CHARGING` row, add:

```text
        (make_charger(is_connected=True, state=ChargerState.BUSY_NON_CHARGING), True),
```

and change its docstring to `"""A charge is open on a charge state, BUSY, BUSY_CHARGING or BUSY_NON_CHARGING."""`.

After `test_start_noop_while_charge_open`, add:

```python
async def test_start_noop_while_busy_non_charging(
    control: ChargeControl, client: AsyncMock
) -> None:
    """BUSY_NON_CHARGING without a charge state is a charge in progress: no API call."""
    charger = make_charger(is_connected=True, state=ChargerState.BUSY_NON_CHARGING)
    control.on_charger_read(charger, control.start_attempts)
    await control.async_start()
    client.start_charge.assert_not_awaited()
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_charge_control.py -q -k "test_charge_is_open or busy_non_charging"`
Expected: FAIL for the new `charge_is_open` row (`assert False is True`) and for `test_start_noop_while_busy_non_charging` (`start_charge` awaited once). Both use `charge_state=None`; with `PAUSED` they would pass without the change, so they can't be the red tests.

- [ ] **Step 3: Implement**

In `custom_components/nortec_go/charge_control.py`, in `charge_is_open`, change the tuple to:

```python
    return charger.charge_state is not None or charger.state in (
        ChargerState.BUSY,
        ChargerState.BUSY_CHARGING,
        ChargerState.BUSY_NON_CHARGING,
    )
```

- [ ] **Step 4: Run it to see it pass**

Run: `uv run pytest tests/test_charge_control.py -q -k "test_charge_is_open or busy_non_charging"`
Expected: PASS.

- [ ] **Step 5: Pin the status rows**

In `tests/test_charge_control.py`, in the `charge_status` table (the parametrize with `(CHARGING, BLOCKED, "start_blocked")`), after the `PAUSED` row, add:

```text
        (
            make_charger(
                is_connected=True,
                state=ChargerState.BUSY_NON_CHARGING,
                charge_state=ChargeState.PAUSED,
            ),
            IDLE,
            "paused",
        ),
        (
            make_charger(is_connected=True, state=ChargerState.BUSY_NON_CHARGING),
            IDLE,
            "idle",
        ),
```

(These pin spec §2: the first comes from the bump alone, the second shows `idle` as for `BUSY` with no charge state.)

Run: `uv run pytest tests/test_charge_control.py -q`
Expected: PASS.

- [ ] **Step 6: The whole-integration test**

Create `tests/test_car_pause.py`:

```python
"""A charge the car paused, as the owner saw it in Home Assistant (spec §2)."""

from unittest.mock import AsyncMock

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from pynortecgo import ChargerState, ChargeState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import make_charger, setup_integration


async def test_car_paused_charge_entities(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """Charge stays on, Charge status is paused, Charging is off."""
    mock_client.get_charger.return_value = make_charger(
        is_connected=True,
        state=ChargerState.BUSY_NON_CHARGING,
        charge_state=ChargeState.PAUSED,
    )
    await setup_integration(hass, mock_config_entry)

    switch = hass.states.get("switch.garage_charger_charge")
    status = hass.states.get("sensor.garage_charger_charge_status")
    charging = hass.states.get("binary_sensor.garage_charger_charging")
    assert switch is not None
    assert status is not None
    assert charging is not None
    assert switch.state == STATE_ON
    assert status.state == "paused"
    assert charging.state == STATE_OFF
```

Run: `uv run pytest tests/test_car_pause.py -q`
Expected: PASS.

- [ ] **Step 7: Run all gates and commit**

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95 -q`
Expected: all pass.

```bash
git add custom_components/nortec_go/charge_control.py tests/test_charge_control.py tests/test_car_pause.py
git commit -F <message file>   # "fix: BUSY_NON_CHARGING is a charge in progress (#33)"
```

---

### Task 3: The price store's version 2, the currency and the unit

**Model:** opus — maps `pynortecgo`'s `PriceForecast.currency` to the price entity's unit, and migrates stored data.
**Wave:** 2

**Files:**
- Modify: `custom_components/nortec_go/const.py:28` (`PRICE_STORE_VERSION`)
- Modify: `custom_components/nortec_go/prices.py` (`StoredPrices`, `_PriceData`, `PriceStore`)
- Modify: `custom_components/nortec_go/coordinator.py` (`__init__`, `async_load_prices`, `async_read_prices`)
- Modify: `custom_components/nortec_go/sensor.py` (`NortecGoPriceSensor`)
- Test: `tests/test_prices.py`, `tests/test_coordinator.py`, `tests/test_sensor.py`

**Interfaces:**
- Consumes: Task 1's `make_forecast(start, prices, currency="DKK")`.
- Produces:
  - `prices.StoredPrices` — `@dataclass(frozen=True)` with `slots: KnownSlots` and `currency: str | None`.
  - `PriceStore.async_load(self) -> StoredPrices`; `PriceStore.async_save(self, known: Mapping[datetime, float], currency: str | None) -> None`; `PriceStore.async_remove` unchanged.
  - `NortecGoCoordinator.price_currency: str | None` (starts `None`).
  - `NortecGoPriceSensor.native_unit_of_measurement` property: `f"{price_currency or hass.config.currency}/kWh"`.

- [ ] **Step 1: Write the failing store tests**

In `tests/test_prices.py`:

- Add `StoredPrices` to the import from `custom_components.nortec_go.prices`.
- Add `KEY = "nortec_go.entry1.prices"` to the module constants at the top, after `NOW`.
- Replace `test_store_round_trip`, `test_store_missing_file` and `test_store_wrong_shape` with:

```python
async def test_store_round_trip(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Saved slots and currency load back, with UTC keys; remove deletes the file."""
    store = PriceStore(hass, "entry1")
    known = _slots(MIDNIGHT, [1.0, 2.0])
    await store.async_save(known, "DKK")
    assert hass_storage[KEY]["version"] == 2
    assert hass_storage[KEY]["data"] == {
        "currency": "DKK",
        "slots": [
            {"start": "2026-09-26T22:00:00+00:00", "price": 1.0},
            {"start": "2026-09-26T22:15:00+00:00", "price": 2.0},
        ],
    }
    assert await PriceStore(hass, "entry1").async_load() == StoredPrices(known, "DKK")
    await store.async_remove()
    assert KEY not in hass_storage


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
```

Run: `uv run pytest tests/test_prices.py -q`
Expected: FAIL (`ImportError: cannot import name 'StoredPrices'`).

- [ ] **Step 2: Implement the store**

In `custom_components/nortec_go/const.py` set `PRICE_STORE_VERSION: Final = 2`.

In `custom_components/nortec_go/prices.py`:
- Add `from dataclasses import dataclass` to the imports.
- After the `KnownSlots` alias, add:

```python
@dataclass(frozen=True)
class StoredPrices:
    """The known slots and the prices' currency, as stored."""

    slots: KnownSlots
    currency: str | None
```

- Before `class PriceStore`, add:

```python
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
        return {"currency": None, "slots": []}
```

- In `PriceStore`, make `__init__` build `_PriceData(...)` instead of `Store(...)` (same arguments; annotate `self._store: _PriceData`), and replace its methods `async_load` and `async_save` with these (methods of `PriceStore`, indented as shown):

```python
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
```

Keep the `Store` import: `_PriceData` subclasses it.

So that setup keeps working with the new store API, make the minimal change in
`custom_components/nortec_go/coordinator.py` now (Step 4 completes it):
- In `async_load_prices`, pass `(await self._price_store.async_load()).slots` to `prune` instead of the
  whole result.
- In `async_read_prices`, change the save to `await self._price_store.async_save(self.known_prices, None)`.

In `tests/test_coordinator.py`, `test_stored_prices_loaded_at_setup` stores version 1 data, which would now
silently migrate to empty (spec §5). Replace its `hass_storage[key] = {...}` statement with:

```python
    hass_storage[key] = {
        "version": 2,
        "minor_version": 1,
        "key": key,
        "data": {
            "currency": "DKK",
            "slots": [
                {"start": "2026-09-26T21:45:00+00:00", "price": 9.0},
                {"start": "2026-09-26T22:00:00+00:00", "price": 1.0},
            ],
        },
    }
```

Run: `uv run pytest -q`
Expected: PASS, the whole suite. If `test_store_version_1_migrates_to_empty` fails only on the saved-back check, confirm with the installed `homeassistant/helpers/storage.py` that the migration calls `async_save` and adjust the waiting, not the assertion.

- [ ] **Step 3: Write the failing coordinator and sensor tests**

In `tests/test_coordinator.py`:
- In `test_price_read_merges_and_saves`, after the `stored = ...` line, add:

```python
    data = hass_storage[STORE_KEY.format(mock_config_entry.entry_id)]["data"]
    assert data["currency"] == "DKK"
    assert coordinator.price_currency == "DKK"
```

- In `test_stored_prices_loaded_at_setup` (its stored data moved to version 2 in Step 2), at the end add
  `assert _coordinator(mock_config_entry).price_currency == "DKK"`.
- Add after `test_stored_prices_loaded_at_setup`:

```python
async def test_version_1_store_migrates_at_setup(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """A version 1 store (spot prices) loads as empty; the setup's read refills it as version 2."""
    freezer.move_to(MIDNIGHT + timedelta(hours=10))
    key = STORE_KEY.format(mock_config_entry.entry_id)
    hass_storage[key] = {
        "version": 1,
        "minor_version": 1,
        "key": key,
        "data": {"slots": [{"start": "2026-09-26T22:00:00+00:00", "price": 9.0}]},
    }
    mock_client.get_price_forecast.return_value = make_forecast(
        MIDNIGHT + timedelta(hours=10), [2.0]
    )
    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    coordinator = _coordinator(mock_config_entry)
    assert coordinator.known_prices == {MIDNIGHT + timedelta(hours=10): 2.0}
    assert hass_storage[key]["version"] == 2
    assert hass_storage[key]["data"]["currency"] == "DKK"


async def test_price_currency_kept_when_forecast_has_none(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    hass_storage: dict[str, Any],
) -> None:
    """A forecast without a currency keeps the last known one, in memory and stored."""
    mock_client.get_price_forecast.return_value = make_forecast(MIDNIGHT, [1.0])
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)

    mock_client.get_price_forecast.return_value = make_forecast(
        MIDNIGHT, [1.0], currency=None
    )
    await coordinator.async_read_prices()
    assert coordinator.price_currency == "DKK"
    data = hass_storage[STORE_KEY.format(mock_config_entry.entry_id)]["data"]
    assert data["currency"] == "DKK"
```

In `tests/test_sensor.py`, after `test_current_price`, add:

```python
async def test_price_unit_follows_forecast_currency(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The unit is the forecast's currency, not Home Assistant's."""
    hass.config.currency = "EUR"
    freezer.move_to(MIDNIGHT + timedelta(minutes=5))
    mock_client.get_price_forecast.return_value = make_forecast(MIDNIGHT, [1.0])
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(PRICE)
    assert state is not None
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == "DKK/kWh"


async def test_price_unit_falls_back_to_home_assistant_currency(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """With no currency known, the unit is Home Assistant's currency."""
    hass.config.currency = "EUR"
    freezer.move_to(MIDNIGHT + timedelta(minutes=5))
    mock_client.get_price_forecast.return_value = make_forecast(
        MIDNIGHT, [1.0], currency=None
    )
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(PRICE)
    assert state is not None
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == "EUR/kWh"


async def test_price_unit_survives_a_reload_with_a_failing_read(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The stored currency is used when the price read fails after a reload."""
    hass.config.currency = "EUR"
    freezer.move_to(MIDNIGHT + timedelta(minutes=5))
    mock_client.get_price_forecast.return_value = make_forecast(MIDNIGHT, [1.0])
    await setup_integration(hass, mock_config_entry)

    mock_client.get_price_forecast.side_effect = NortecGoConnectionError("network down")
    assert await hass.config_entries.async_reload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(PRICE)
    assert state is not None
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == "DKK/kWh"
```

and, after it, the red test for the unit being a property rather than set once at creation (setup reads
the prices before the platforms, so the three tests above can't tell the two apart):

```python
async def test_price_unit_follows_a_currency_learned_after_setup(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A currency first seen in a later read changes the unit at the next state write."""
    hass.config.currency = "EUR"
    freezer.move_to(MIDNIGHT + timedelta(minutes=5))
    mock_client.get_price_forecast.return_value = make_forecast(
        MIDNIGHT, [1.0], currency=None
    )
    await setup_integration(hass, mock_config_entry)
    assert hass.states.get(PRICE).attributes[ATTR_UNIT_OF_MEASUREMENT] == "EUR/kWh"  # type: ignore[union-attr]

    mock_client.get_price_forecast.return_value = make_forecast(MIDNIGHT, [1.0])
    await mock_config_entry.runtime_data.async_read_prices()
    await hass.async_block_till_done()
    assert hass.states.get(PRICE).attributes[ATTR_UNIT_OF_MEASUREMENT] == "DKK/kWh"  # type: ignore[union-attr]
```

Run: `uv run pytest tests/test_coordinator.py tests/test_sensor.py -q`
Expected:
- FAIL: the coordinator tests on `price_currency` (`AttributeError`) or on the stored currency (`None`
  where `"DKK"` is expected).
- FAIL: `test_price_unit_follows_forecast_currency`, `test_price_unit_survives_a_reload_with_a_failing_read`
  and `test_price_unit_follows_a_currency_learned_after_setup`, with `'EUR/kWh' == 'DKK/kWh'`.
- PASS at once: `test_price_unit_falls_back_to_home_assistant_currency` (the old unit is already Home
  Assistant's currency); it pins the fallback.

- [ ] **Step 4: Implement the coordinator and the sensor**

In `custom_components/nortec_go/coordinator.py`:
- In `__init__`, after `self.known_prices: KnownSlots = {}`, add `self.price_currency: str | None = None`.
- Replace `async_load_prices` (Step 2's minimal version) with:

```python
    async def async_load_prices(self) -> None:
        """Load the stored slots, without yesterday's, and the prices' currency."""
        stored = await self._price_store.async_load()
        self.known_prices = prune(
            stored.slots, dt_util.utcnow(), dt_util.get_default_time_zone()
        )
        self.price_currency = stored.currency
```

- In `async_read_prices`, after the `self.known_prices = prune(...)` statement, add:

```python
        if forecast.currency is not None:
            self.price_currency = forecast.currency
```

  and change Step 2's save to `await self._price_store.async_save(self.known_prices, self.price_currency)`. Update its docstring to `"""Read the forecast, merge, prune and save it with its currency; keep the known slots on failure (§4.3)."""`.

In `custom_components/nortec_go/sensor.py`, in `NortecGoPriceSensor`:
- Change `__init__` to only call `super().__init__(coordinator, "current_price")`, with the docstring `"""Name the sensor Current price."""`.
- Add after `available`:

```python
    @property
    def native_unit_of_measurement(self) -> str:
        """The forecast's currency per kWh, or Home Assistant's while none is known (D34)."""
        currency = self.coordinator.price_currency or self.hass.config.currency
        return f"{currency}/kWh"
```

Run: `uv run pytest tests/test_prices.py tests/test_coordinator.py tests/test_sensor.py -q`
Expected: PASS.

- [ ] **Step 5: Run all gates and commit**

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95 -q`
Expected: all pass; `prices.py`, `coordinator.py` and `sensor.py` have no new uncovered lines. If
`ruff format --check` fails, run `uv run ruff format` and run the gates again.

```bash
git add custom_components/nortec_go/const.py custom_components/nortec_go/prices.py custom_components/nortec_go/coordinator.py custom_components/nortec_go/sensor.py tests/test_prices.py tests/test_coordinator.py tests/test_sensor.py
git commit -F <message file>   # "feat: price store version 2 and the unit from the forecast's currency (#33, #20)"
```

---

### Task 4: Docs, changelog and decision log

**Model:** opus — a docs task (D33).
**Wave:** 2 (written against this plan's names; re-checked against the code that lands)

**Files:**
- Modify: `CHANGELOG.md`, `docs/user/nortec_go.md`, `docs/decisions.md`

**Interfaces:**
- Consumes: the behaviour fixed in this plan's Global Constraints and Tasks 2–3 (no code).
- Produces: D34 in `docs/decisions.md`.

- [ ] **Step 1: Changelog**

In `CHANGELOG.md` under *Unreleased* → *Added*, change the EV Smart Charging bullet's `the current price with today's and tomorrow's prices` to `the current total price (spot, fees and grid tariff) in the price data's currency, with today's and tomorrow's prices`. Add no other entry: only the skeleton was released (spec §6).

- [ ] **Step 2: User docs**

In `docs/user/nortec_go.md`:
- The *Current price* row (line 74): `The total price (spot, fees and grid tariff) for the current 15 minutes, per kWh, incl. VAT, in the currency of the price data. Its prices_today and prices_tomorrow attributes are in the format EV Smart Charging reads` (keep the backticks on the two attribute names).
- *Known limitations*: remove the two bullets starting `The price is the spot price including VAT` and `The price is assumed to be in the currency set in Home Assistant`. In their place add:

```markdown
- The grid tariff is estimated for the hours beyond those the charger prices itself. The estimates improve
  as the integration keeps running, and start over after a Home Assistant restart or a reload of the
  integration.
- The prices have been checked only for the DK2 price area (DKK).
```

- Search the file for any other statement that the price is the spot price or in Home Assistant's currency (`grep -n -i "spot\|currency" docs/user/nortec_go.md`) and bring it in line.

- [ ] **Step 3: Decision log**

Append to `docs/decisions.md`, after D33, wrapped at the file's width:

```markdown
### D34: The total price, in the forecast's currency
- **Date:** 2026-09-28 · **Status:** active
- **Decision:** The price sensor and EV Smart Charging's lists use the total price per kWh incl. VAT
  (spot, fees and grid tariff); the unit is the forecast's currency per kWh, falling back to Home
  Assistant's currency.
- **Why:** The total is what the owner pays, and the hourly grid tariff changes which slots are cheapest;
  the forecast knows its own currency, so the unit is right without a Home Assistant setting (#20).
- **Source:** [pynortecgo 0.5.0 spec](superpowers/specs/2026-09-28-pynortecgo-0.5.0-design.md), Decisions
```

- [ ] **Step 4: Check and commit**

Run: `uv run pre-commit run --files CHANGELOG.md docs/user/nortec_go.md docs/decisions.md`
Expected: all pass.

```bash
git add CHANGELOG.md docs/user/nortec_go.md docs/decisions.md
git commit -F <message file>   # "docs: total price in the forecast's currency, D34 (#33, #20)"
```

---

## After the tasks

Not tasks, but part of the flow (`docs/way-of-working.md` §1) and spec §7:
- Before the PR is marked ready, `scripts/smoke` runs on the branch; the owner's dev config has a version 1
  price store, so the smoke run also shows the migration works without an error.
- The PR description records that the `docs/releasing.md` bump checklist was worked through (spec, Facts).
- After merge, #24 gets a comment: 0.5.0 unblocks it, with a measured power (`Charger.charge_kw`) instead of
  an average between reads.
