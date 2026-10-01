# The cost of a charge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. In this repo the flow in `docs/way-of-working.md` §1–2 applies (implementer and task-reviewer agents, waves, worktrees).

**Goal:** Two sensors on the charger device, *Cost this charge* and *Last charge cost*, showing the costs `pynortecgo` 0.7.0 reports, with the client bumped from 0.5.0 and its new start pre-check error given the existing message.

**Architecture:** Task 1 bumps the client and makes the test fixtures build the new `Charger`. Task 2 adds `costs.py` (pure reads of the cost fields) and the two sensors on top of it. Task 3 adds one entry to the start path's pre-check errors. Task 4 writes the docs, the changelog and D42; it runs in wave 1 next to Task 1, written against the names this plan fixes.

**Tech Stack:** Python 3.14, Home Assistant custom integration, `pynortecgo` 0.7.0 (always mocked in tests), pytest with `pytest-homeassistant-custom-component` and freezegun, uv.

**Spec:** `docs/superpowers/specs/2026-10-01-session-cost-design.md` (issue #76).

## Global Constraints

- TDD: write the failing test, see it fail, then write the code. Tests always mock `pynortecgo`, and fixtures come from `pynortecgo` model objects and the `tests/conftest.py` helpers, never raw API JSON (hard rules 2, 7).
- Never start or stop a real charge (hard rule 2). Never auto-retry `start_charge` (hard rule 6). Only Task 3 touches the start path, and only the one line it names.
- Nothing private (hard rule 3): no IDs, tokens, emails, captures, raw endpoints, response shapes, or links into the private client repo. Name only `pynortecgo`'s public API. Test values are plainly fake.
- No cost is computed from energy and price. Both sensors show the client's values (D42).
- Gates before every commit (`CLAUDE.md` → Commands): `uv run pytest -q`, then `uv run ruff check && uv run ruff format --check && uv run mypy`. The coverage gate (`uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95`) passes at the end of each task.
- Subagents write commit messages with the Write tool to a file outside the repo, and commit with `git commit -F <file>` (no heredocs). End each message with the co-author trailer given in the dispatch.
- Match the surrounding code: comment density, one-line docstrings ending in a period, names.
- Client version: `pynortecgo==0.7.0`, in `manifest.json` and `pyproject.toml`, the lock updated with `uv lock --upgrade-package pynortecgo`.
- Sensor keys and names, exactly: `charge_cost` → *Cost this charge*; `last_charge_cost` → *Last charge cost*. Entity IDs in tests: `sensor.garage_charger_cost_this_charge`, `sensor.garage_charger_last_charge_cost`.
- Unit order, exactly: `charger.currency`, then `coordinator.price_currency`, then `hass.config.currency`.
- Fixture names, exactly: `FAKE_CHARGE_ID = "fake-charge-id"`, `FAKE_LAST_CHARGE_ID = "fake-last-charge-id"`, `FAKE_COMPLETED_AT = datetime(2026, 9, 25, 6, 15, tzinfo=UTC)`, `make_completed_charge(*, charge_id, cost, kwh, completed_at)` with the defaults `FAKE_LAST_CHARGE_ID`, `42.5`, `18.4`, `FAKE_COMPLETED_AT`.
- Decision number: D42, placed after D41.

## Review Focus

1. A cost of `0.0` (a charge that has just started) shows as `0.0`, not unknown: the reads test `is None`, never truthiness (Task 2 test `test_charge_cost`, the `zero_cost` and `billed_zero` rows).
2. The swap to the billed total goes by the charge ID alone, not by the charge state: a charge still reported as charging whose ID equals the last completed charge's shows the billed total (Task 2 test `test_charge_cost`, the `billed_while_charging` row).
3. A restart or reload keeps the cycle: *Last charge cost* comes back with the same `last_reset` for the same charge, so the statistics count nothing twice (Task 2 test `test_last_charge_cost_keeps_its_cycle_over_a_reload`).
4. A failed charger read between two reads of the same charge: both sensors are unavailable, then come back with the same value and `last_reset` (Task 2 test `test_cost_sensors_unavailable_after_a_failed_read`).
5. A charger that names its currency only in a later read: the unit follows at the next state write (Task 2 test `test_cost_unit_follows_a_currency_learned_later`).

## Waves

| Wave | Tasks | Notes |
|---|---|---|
| 1 | Task 1 (client bump and fixtures), Task 4 (docs) | Disjoint files, two worktrees off the feature branch. Task 4 is written against this plan's names and re-checked against the code that lands |
| 2 | Task 2 (costs and sensors), Task 3 (start pre-check error) | Disjoint files, two worktrees. Both need Task 1 on the feature branch: the 0.7.0 models and exception, and the fixtures |

No task has guarded files.

---

### Task 1: The client bump and the test fixtures

**Model:** sonnet — a version pin, test helpers and pinned field sets; no auth, start or stop, or entity mapping.
**Wave:** 1

**Files:**
- Modify: `custom_components/nortec_go/manifest.json`, `pyproject.toml`, `uv.lock`
- Modify: `tests/conftest.py`
- Test: `tests/test_diagnostics.py`

**Interfaces:**
- Consumes: `pynortecgo` 0.7.0's public models. `Charger` has three new required fields: `charge_cost: float | None`, `currency: str | None`, `last_charge: CompletedCharge | None`. `CompletedCharge` is a frozen dataclass with `id: str`, `cost: float`, `kwh: float`, `completed_at: datetime`.
- Produces, in `tests/conftest.py`:
  - `FAKE_CHARGE_ID: str = "fake-charge-id"`, `FAKE_LAST_CHARGE_ID: str = "fake-last-charge-id"`, `FAKE_COMPLETED_AT: datetime = datetime(2026, 9, 25, 6, 15, tzinfo=UTC)`;
  - `make_completed_charge(*, charge_id: str = FAKE_LAST_CHARGE_ID, cost: float = 42.5, kwh: float = 18.4, completed_at: datetime = FAKE_COMPLETED_AT) -> CompletedCharge`;
  - `make_charger(...)` with three more keyword arguments: `charge_cost: float | None = None`, `currency: str | None = "DKK"`, `last_charge: CompletedCharge | None = None`. The open charge's ID stays `FAKE_CHARGE_ID`.

- [ ] **Step 1: Write the failing test**

In `tests/test_diagnostics.py`:

1. Add `CompletedCharge` to the import from `pynortecgo` (alphabetical: after `ChargeState`).
2. Delete the local `FAKE_CHARGE_ID = "fake-charge-id"  # make_charger's charge ID while a charge is open` line, and import `FAKE_CHARGE_ID`, `FAKE_LAST_CHARGE_ID` and `make_completed_charge` from `.conftest` (alphabetical in the existing import list).
3. Add the three new fields to `CHARGER_FIELDS`, after `"charge_kw"`:

```text
    "charge_cost",
    "currency",
    "last_charge",
```

4. Add the new pinned set after `CHARGER_FIELDS`:

```python
COMPLETED_CHARGE_FIELDS = {"id", "cost", "kwh", "completed_at"}
```

5. In `test_client_model_fields_are_pinned`, add one assertion after the `Charger` one:

```text
    assert {f.name for f in fields(CompletedCharge)} == COMPLETED_CHARGE_FIELDS
```

6. In `test_diagnostics_output`, give the charger a cost and a last charge, and expect them unredacted. The charger becomes:

```text
    mock_client.get_charger.return_value = make_charger(
        is_connected=True,
        state=ChargerState.BUSY_CHARGING,
        charge_state=ChargeState.CHARGING,
        charge_kwh=4.2,
        charge_kw=7.1,
        charge_cost=9.87,
        last_charge=make_completed_charge(),
    )
```

and the expected `"charger"` dict gets, after `"charge_kw": 7.1,`:

```text
                "charge_cost": 9.87,
                "currency": "DKK",
                "last_charge": {
                    "id": FAKE_LAST_CHARGE_ID,
                    "cost": 42.5,
                    "kwh": 18.4,
                    "completed_at": "2026-09-25T06:15:00+00:00",
                },
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_diagnostics.py -q`
Expected: an import error at collection, `cannot import name 'CompletedCharge' from 'pynortecgo'` (0.5.0 is still installed).

- [ ] **Step 3: Bump the client**

In `custom_components/nortec_go/manifest.json`, `"requirements": ["pynortecgo==0.5.0"]` becomes `"requirements": ["pynortecgo==0.7.0"]`. In `pyproject.toml`, `"pynortecgo==0.5.0",` becomes `"pynortecgo==0.7.0",`. Then:

```bash
uv lock --upgrade-package pynortecgo
uv sync
```

Check with `git diff --stat uv.lock` that the lock changed only for `pynortecgo` (and anything 0.7.0 itself needs).

- [ ] **Step 4: Run the tests to see the next failure**

Run: `uv run pytest tests/test_diagnostics.py -q`
Expected: an import error at collection, `cannot import name 'FAKE_CHARGE_ID' from 'tests.conftest'` (the helpers come next).

- [ ] **Step 5: Update the fixtures**

In `tests/conftest.py`, add `CompletedCharge` to the import from `pynortecgo` (after `ChargeState`), add the constants after `FAKE_LAST_SEEN`:

```python
FAKE_CHARGE_ID = "fake-charge-id"  # make_charger's charge ID while a charge is open
FAKE_LAST_CHARGE_ID = "fake-last-charge-id"  # differs, so no swap by accident
FAKE_COMPLETED_AT = datetime(2026, 9, 25, 6, 15, tzinfo=UTC)
```

Replace `make_charger` with:

```python
def make_charger(
    charger_id: int = FAKE_CHARGER_ID,
    name: str = FAKE_CHARGER_NAME,
    *,
    is_connected: bool = False,
    charge_state: ChargeState | None = None,
    state: ChargerState = ChargerState.AVAILABLE,
    charge_kwh: float | None = None,
    charge_kw: float | None = None,
    charge_cost: float | None = None,
    currency: str | None = "DKK",
    last_charge: CompletedCharge | None = None,
) -> Charger:
    """Return a charger; idle and unplugged unless told otherwise."""
    return Charger(
        id=charger_id,
        name=name,
        max_kw=11.0,
        state=state,
        state_raw=state.value,
        is_connected=is_connected,
        charge_state=charge_state,
        charge_state_raw=None if charge_state is None else charge_state.value,
        charge_id=None if charge_state is None else FAKE_CHARGE_ID,
        can_stop=None if charge_state is None else True,
        charge_kwh=charge_kwh,
        charge_kw=charge_kw,
        charge_cost=charge_cost,
        currency=currency,
        last_charge=last_charge,
    )
```

and add after it:

```python
def make_completed_charge(
    *,
    charge_id: str = FAKE_LAST_CHARGE_ID,
    cost: float = 42.5,
    kwh: float = 18.4,
    completed_at: datetime = FAKE_COMPLETED_AT,
) -> CompletedCharge:
    """Return a completed charge with fake values; its ID differs from an open charge's."""
    return CompletedCharge(id=charge_id, cost=cost, kwh=kwh, completed_at=completed_at)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest -q`
Expected: all pass. If another test in `tests/test_diagnostics.py` compares a whole `"charger"` dict, add `"charge_cost": None, "currency": "DKK", "last_charge": None` to it (those are `make_charger`'s defaults). No file under `custom_components/` other than `manifest.json` changes in this task.

- [ ] **Step 7: Run the gates**

Run: `uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95 -q`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add custom_components/nortec_go/manifest.json pyproject.toml uv.lock tests/conftest.py tests/test_diagnostics.py
git commit -F /tmp/session-cost-task-1-msg.txt
```

Message: `chore: pynortecgo 0.7.0, with fixtures for the new charger fields (#76)`, then the co-author trailer.

---

### Task 2: The cost reads and the two sensors

**Model:** opus — maps `pynortecgo` model fields to entities.
**Wave:** 2

**Files:**
- Create: `custom_components/nortec_go/costs.py`
- Create: `tests/test_costs.py`
- Modify: `custom_components/nortec_go/sensor.py`
- Modify: `custom_components/nortec_go/strings.json`, `custom_components/nortec_go/translations/en.json` (the two files are identical; keep them so)
- Test: `tests/test_sensor.py`

**Interfaces:**
- Consumes, from Task 1's `tests/conftest.py`: `FAKE_CHARGE_ID`, `FAKE_COMPLETED_AT`, `make_completed_charge(*, charge_id, cost, kwh, completed_at)`, and `make_charger(..., charge_cost=, currency=, last_charge=)`.
- Consumes, from `pynortecgo` 0.7.0: `Charger.charge_id`, `Charger.charge_cost`, `Charger.currency`, `Charger.last_charge` (`CompletedCharge` with `id`, `cost`, `completed_at`).
- Consumes, from the coordinator: `coordinator.data.charger`, `coordinator.price_currency` (`str | None`).
- Produces, in `custom_components/nortec_go/costs.py`:
  - `charge_cost(charger: Charger) -> float | None`
  - `last_charge_cost(charger: Charger) -> float | None`
  - `last_charge_completed_at(charger: Charger) -> datetime | None`
- Produces, in `sensor.py`: `NortecGoCostSensorDescription`, `COST_SENSORS`, `NortecGoCostSensor`.

- [ ] **Step 1: Write the failing tests for `costs.py`**

Create `tests/test_costs.py`:

```python
"""Tests for the cost reads: the open charge's cost and the last completed charge's (D42)."""

from pynortecgo import Charger, ChargeState
import pytest

from custom_components.nortec_go.costs import (
    charge_cost,
    last_charge_completed_at,
    last_charge_cost,
)

from .conftest import (
    FAKE_CHARGE_ID,
    FAKE_COMPLETED_AT,
    make_charger,
    make_completed_charge,
)

BILLED = make_completed_charge(charge_id=FAKE_CHARGE_ID, cost=13.07)


@pytest.mark.parametrize(
    ("charger", "expected"),
    [
        (make_charger(), None),
        (make_charger(charge_cost=5.0, last_charge=make_completed_charge()), None),
        (make_charger(charge_state=ChargeState.CHARGING, charge_cost=12.34), 12.34),
        (
            make_charger(
                charge_state=ChargeState.CHARGING,
                charge_cost=12.34,
                last_charge=make_completed_charge(),
            ),
            12.34,
        ),
        (
            make_charger(
                charge_state=ChargeState.STOPPING, charge_cost=12.34, last_charge=BILLED
            ),
            13.07,
        ),
        (
            make_charger(
                charge_state=ChargeState.CHARGING, charge_cost=12.34, last_charge=BILLED
            ),
            13.07,
        ),
        (make_charger(charge_state=ChargeState.CHARGING), None),
        (
            make_charger(
                charge_state=ChargeState.CHARGING, last_charge=make_completed_charge()
            ),
            None,
        ),
        (make_charger(charge_state=ChargeState.CHARGING, charge_cost=0.0), 0.0),
        (
            make_charger(
                charge_state=ChargeState.STOPPING,
                charge_cost=12.34,
                last_charge=make_completed_charge(charge_id=FAKE_CHARGE_ID, cost=0.0),
            ),
            0.0,
        ),
    ],
    ids=[
        "no_charge",
        "no_charge_ignores_cost",
        "open_no_last_charge",
        "open_other_last_charge",
        "billed_while_stopping",
        "billed_while_charging",
        "open_no_cost_reading",
        "open_no_cost_reading_other_last_charge",
        "zero_cost",
        "billed_zero",
    ],
)
def test_charge_cost(charger: Charger, expected: float | None) -> None:
    """The live cost of an open charge, or its billed total once it is the last completed charge."""
    assert charge_cost(charger) == expected


def test_last_charge_reads() -> None:
    """The last completed charge's billed total and completion time."""
    charger = make_charger(last_charge=make_completed_charge())
    assert last_charge_cost(charger) == 42.5
    assert last_charge_completed_at(charger) == FAKE_COMPLETED_AT


def test_last_charge_reads_without_a_last_charge() -> None:
    """None when the client gives no last charge."""
    charger = make_charger()
    assert last_charge_cost(charger) is None
    assert last_charge_completed_at(charger) is None


def test_last_charge_cost_of_zero() -> None:
    """A billed total of 0 is a value, not a missing one."""
    charger = make_charger(last_charge=make_completed_charge(cost=0.0))
    assert last_charge_cost(charger) == 0.0
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_costs.py -q`
Expected: an import error, `No module named 'custom_components.nortec_go.costs'`.

- [ ] **Step 3: Write `costs.py`**

Create `custom_components/nortec_go/costs.py`:

```python
"""The cost of the open charge and of the last completed one, as pynortecgo reports them (D42).

The one place that reads Charger.charge_cost and Charger.last_charge.
"""

from datetime import datetime

from pynortecgo import Charger


def charge_cost(charger: Charger) -> float | None:
    """The open charge's cost so far, or its billed total once it is the last completed charge."""
    if charger.charge_id is None:
        return None
    last = charger.last_charge
    if last is not None and last.id == charger.charge_id:
        return last.cost
    return charger.charge_cost


def last_charge_cost(charger: Charger) -> float | None:
    """The last completed charge's billed total, or None without a last charge."""
    last = charger.last_charge
    return None if last is None else last.cost


def last_charge_completed_at(charger: Charger) -> datetime | None:
    """When the last completed charge ended, or None without a last charge."""
    last = charger.last_charge
    return None if last is None else last.completed_at
```

- [ ] **Step 4: Run them to verify they pass**

Run: `uv run pytest tests/test_costs.py -q`
Expected: 13 passed.

- [ ] **Step 5: Write the failing sensor tests**

In `tests/test_sensor.py`:

1. Add `ATTR_LAST_RESET` to the import from `homeassistant.components.sensor` (before `ATTR_STATE_CLASS`).
2. Add `FAKE_CHARGE_ID`, `FAKE_COMPLETED_AT` and `make_completed_charge` to the import from `.conftest` (alphabetical).
3. Add after `test_charge_energy_starts_a_new_cycle_per_charge` (before `test_car_sensors`):

```python
COST = "sensor.garage_charger_cost_this_charge"
LAST_COST = "sensor.garage_charger_last_charge_cost"


async def test_cost_sensors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Cost this charge and Last charge cost: classes, unit, precision, charger device."""
    mock_client.get_charger.return_value = make_charger(
        is_connected=True,
        charge_state=ChargeState.CHARGING,
        charge_cost=12.34,
        last_charge=make_completed_charge(),
    )
    await setup_integration(hass, mock_config_entry)
    charger = _device(device_registry, mock_config_entry, str(FAKE_CHARGER_ID))
    assert charger is not None

    for entity_id, key, value, state_class, last_reset in (
        (COST, "charge_cost", "12.34", None, None),
        (
            LAST_COST,
            "last_charge_cost",
            "42.5",
            SensorStateClass.TOTAL,
            FAKE_COMPLETED_AT.isoformat(),
        ),
    ):
        state = hass.states.get(entity_id)
        assert state is not None, entity_id
        assert state.state == value
        assert state.attributes[ATTR_DEVICE_CLASS] == SensorDeviceClass.MONETARY
        assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == "DKK"
        assert state.attributes.get(ATTR_STATE_CLASS) == state_class
        assert state.attributes.get(ATTR_LAST_RESET) == last_reset
        entry = entity_registry.async_get(entity_id)
        assert entry is not None
        assert entry.unique_id == f"{FAKE_CHARGER_ID}_{key}"
        assert entry.device_id == charger.id
        assert entry.entity_category is None
        assert entry.disabled_by is None
        assert entry.options["sensor"]["suggested_display_precision"] == 2


@pytest.mark.parametrize(
    ("charger", "cost", "last_cost"),
    [
        (
            make_charger(is_connected=True, last_charge=make_completed_charge()),
            STATE_UNKNOWN,
            "42.5",
        ),
        (
            make_charger(
                is_connected=True,
                charge_state=ChargeState.CHARGING,
                charge_cost=12.34,
                last_charge=make_completed_charge(),
            ),
            "12.34",
            "42.5",
        ),
        (
            make_charger(
                is_connected=True,
                charge_state=ChargeState.STOPPING,
                charge_cost=12.34,
                last_charge=make_completed_charge(charge_id=FAKE_CHARGE_ID, cost=13.07),
            ),
            "13.07",
            "13.07",
        ),
        (
            make_charger(
                is_connected=True,
                charge_state=ChargeState.CHARGING,
                last_charge=make_completed_charge(),
            ),
            STATE_UNKNOWN,
            "42.5",
        ),
        (
            make_charger(
                is_connected=True, charge_state=ChargeState.CHARGING, charge_cost=0.0
            ),
            "0.0",
            STATE_UNKNOWN,
        ),
    ],
    ids=[
        "no_charge",
        "open_charge",
        "stopping_already_billed",
        "open_charge_no_cost_reading",
        "no_last_charge",
    ],
)
async def test_cost_values(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    charger: Charger,
    cost: str,
    last_cost: str,
) -> None:
    """The rows of the spec's table (§3): what each sensor shows in each situation."""
    mock_client.get_charger.return_value = charger
    await setup_integration(hass, mock_config_entry)
    assert _state(hass, COST) == cost
    assert _state(hass, LAST_COST) == last_cost


@pytest.mark.parametrize(
    ("charger_currency", "forecast_currency", "unit"),
    [("SEK", "DKK", "SEK"), (None, "DKK", "DKK"), (None, None, "EUR")],
    ids=["the_chargers", "the_forecasts", "home_assistants"],
)
async def test_cost_unit(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    charger_currency: str | None,
    forecast_currency: str | None,
    unit: str,
) -> None:
    """The unit is the charger's currency, then the forecast's, then Home Assistant's."""
    hass.config.currency = "EUR"
    freezer.move_to(MIDNIGHT + timedelta(minutes=5))
    mock_client.get_price_forecast.return_value = make_forecast(
        MIDNIGHT, [1.0], currency=forecast_currency
    )
    mock_client.get_charger.return_value = make_charger(
        is_connected=True,
        charge_state=ChargeState.CHARGING,
        charge_cost=12.34,
        currency=charger_currency,
        last_charge=make_completed_charge(),
    )
    await setup_integration(hass, mock_config_entry)

    for entity_id in (COST, LAST_COST):
        state = hass.states.get(entity_id)
        assert state is not None, entity_id
        assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == unit


async def test_cost_unit_follows_a_currency_learned_later(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A charger that names its currency in a later read changes the unit at that read."""
    hass.config.currency = "EUR"
    freezer.move_to(MIDNIGHT + timedelta(minutes=5))
    mock_client.get_price_forecast.return_value = make_forecast(
        MIDNIGHT, [1.0], currency=None
    )
    mock_client.get_charger.return_value = make_charger(
        currency=None, last_charge=make_completed_charge()
    )
    await setup_integration(hass, mock_config_entry)
    state = hass.states.get(LAST_COST)
    assert state is not None
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == "EUR"

    mock_client.get_charger.return_value = make_charger(
        last_charge=make_completed_charge()
    )
    freezer.tick(timedelta(seconds=1))
    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    state = hass.states.get(LAST_COST)
    assert state is not None
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == "DKK"


def _cost_state(hass: HomeAssistant, entity_id: str) -> tuple[str, str | None]:
    """A cost sensor's state and its last_reset attribute."""
    state = hass.states.get(entity_id)
    assert state is not None, entity_id
    return state.state, state.attributes.get(ATTR_LAST_RESET)


async def test_cost_sensors_unavailable_after_a_failed_read(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A failed charger read makes both unavailable; the same charge comes back with the same cycle."""
    charger = make_charger(
        is_connected=True,
        charge_state=ChargeState.CHARGING,
        charge_cost=12.34,
        last_charge=make_completed_charge(),
    )
    mock_client.get_charger.return_value = charger
    await setup_integration(hass, mock_config_entry)
    before = _cost_state(hass, LAST_COST)
    assert before == ("42.5", FAKE_COMPLETED_AT.isoformat())

    mock_client.get_charger.side_effect = NortecGoConnectionError("network down")
    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, COST) == STATE_UNAVAILABLE
    assert _state(hass, LAST_COST) == STATE_UNAVAILABLE

    mock_client.get_charger.side_effect = None
    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, COST) == "12.34"
    assert _cost_state(hass, LAST_COST) == before


async def test_last_charge_cost_starts_a_new_cycle_per_completed_charge(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """Unknown and back keeps the cycle; a new charge with the same cost is a new cycle."""
    first = make_completed_charge()
    later = FAKE_COMPLETED_AT + timedelta(days=1)
    second = make_completed_charge(charge_id="fake-newer-charge-id", completed_at=later)
    later_reads = (
        make_charger(is_connected=True),
        make_charger(is_connected=True, last_charge=first),
        make_charger(is_connected=True, last_charge=second),
    )
    mock_client.get_charger.return_value = make_charger(
        is_connected=True, last_charge=first
    )
    await setup_integration(hass, mock_config_entry)
    seen = [_cost_state(hass, LAST_COST)]
    for charger in later_reads:
        mock_client.get_charger.return_value = charger
        await mock_config_entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        seen.append(_cost_state(hass, LAST_COST))

    assert seen == [
        ("42.5", FAKE_COMPLETED_AT.isoformat()),
        (STATE_UNKNOWN, None),
        ("42.5", FAKE_COMPLETED_AT.isoformat()),
        ("42.5", later.isoformat()),
    ]
    state = hass.states.get(LAST_COST)
    assert state is not None
    assert state.attributes[ATTR_STATE_CLASS] == SensorStateClass.TOTAL


async def test_last_charge_cost_keeps_its_cycle_over_a_reload(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """After a reload the same charge has the same last_reset: nothing is stored, nothing counted twice."""
    mock_client.get_charger.return_value = make_charger(
        is_connected=True, last_charge=make_completed_charge()
    )
    await setup_integration(hass, mock_config_entry)
    before = _cost_state(hass, LAST_COST)

    assert await hass.config_entries.async_reload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert _cost_state(hass, LAST_COST) == before
    assert before == ("42.5", FAKE_COMPLETED_AT.isoformat())
```

- [ ] **Step 6: Run them to verify they fail**

Run: `uv run pytest tests/test_sensor.py -q -k "cost"`
Expected: FAIL; the first assertion to fail is `assert state is not None, entity_id` (the sensors don't exist yet).

- [ ] **Step 7: Add the sensors**

In `custom_components/nortec_go/sensor.py`:

1. The module docstring becomes:

```python
"""Nortec Go sensors: the price for EV Smart Charging, the charge status, the open charge's energy, power and cost, the last charge's cost, the last read and the car's values."""
```

2. Add the import, after the `.coordinator` import:

```python
from .costs import charge_cost, last_charge_completed_at, last_charge_cost
```

3. Add after `CHARGE_SENSORS`:

```python
@dataclass(frozen=True, kw_only=True)
class NortecGoCostSensorDescription(SensorEntityDescription):
    """A cost sensor: how to read it from the charger, and when its cycle started, if it has cycles."""

    value_fn: Callable[[Charger], float | None]
    last_reset_fn: Callable[[Charger], datetime | None] | None = None


# Cost this charge has no state class: a per-charge value without last_reset would give a
# wrong statistics sum. Last charge cost starts a new cycle per completed charge (D42).
COST_SENSORS: tuple[NortecGoCostSensorDescription, ...] = (
    NortecGoCostSensorDescription(
        key="charge_cost",
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        value_fn=charge_cost,
    ),
    NortecGoCostSensorDescription(
        key="last_charge_cost",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        value_fn=last_charge_cost,
        last_reset_fn=last_charge_completed_at,
    ),
)
```

4. In `async_setup_entry`, after the `CHARGE_SENSORS` `entities.extend(...)`:

```text
    entities.extend(
        NortecGoCostSensor(coordinator, description) for description in COST_SENSORS
    )
```

and its docstring stays as it is.

5. Add after the `NortecGoChargeSensor` class:

```python
class NortecGoCostSensor(NortecGoChargerEntity, SensorEntity):
    """A cost the client reports, in the charger's currency (D42)."""

    entity_description: NortecGoCostSensorDescription

    def __init__(
        self,
        coordinator: NortecGoCoordinator,
        description: NortecGoCostSensorDescription,
    ) -> None:
        """Set up the sensor from its description."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_unit_of_measurement(self) -> str:
        """The charger's currency, then the forecast's, then Home Assistant's (D34, D42)."""
        return (
            self.coordinator.data.charger.currency
            or self.coordinator.price_currency
            or self.hass.config.currency
        )

    @property
    def native_value(self) -> float | None:
        """The cost, or None (unknown) when the client has none."""
        return self.entity_description.value_fn(self.coordinator.data.charger)

    @property
    def last_reset(self) -> datetime | None:
        """When the sensor's cycle started: the last charge's completion time, if it has cycles."""
        last_reset_fn = self.entity_description.last_reset_fn
        if last_reset_fn is None:
            return None
        return last_reset_fn(self.coordinator.data.charger)
```

6. In `custom_components/nortec_go/strings.json` and in `custom_components/nortec_go/translations/en.json`, under `entity` → `sensor`, after the `charging_power` entry (add a comma after its closing brace):

```text
      "charge_cost": {
        "name": "Cost this charge"
      },
      "last_charge_cost": {
        "name": "Last charge cost"
      }
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `uv run pytest tests/test_sensor.py tests/test_costs.py -q`
Expected: all pass. Then `diff custom_components/nortec_go/strings.json custom_components/nortec_go/translations/en.json` prints nothing.

- [ ] **Step 9: Run the gates**

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95 -q`
Expected: all pass, with `costs.py` and the new sensor code fully covered. If another test fails because it lists or counts the charger's entities, add the two sensors to its expectation.

- [ ] **Step 10: Commit**

```bash
git add custom_components/nortec_go/costs.py custom_components/nortec_go/sensor.py custom_components/nortec_go/strings.json custom_components/nortec_go/translations/en.json tests/test_costs.py tests/test_sensor.py
git commit -F /tmp/session-cost-task-2-msg.txt
```

Message: `feat: Cost this charge and Last charge cost sensors (#76)`, then the co-author trailer.

---

### Task 3: The start path's new pre-check error

**Model:** opus — the start path of the charge control (the owner approved this one change on #76).
**Wave:** 2

**Files:**
- Modify: `custom_components/nortec_go/charge_control.py` (the `pynortecgo` import and `_PRE_CHECK_ERRORS` only)
- Test: `tests/test_charge_control.py`

**Interfaces:**
- Consumes: `pynortecgo.UnknownChargerStateError` (0.7.0, on the feature branch after Task 1), a `NortecGoError` that `start_charge()` raises before any payment request. Its constructor takes the charger's raw state: `UnknownChargerStateError("mystery")`.
- Produces: nothing other tasks use.

This task changes nothing else in `charge_control.py`: not the start guard, the block, the hold handling, the stop path or any log line. `start_charge` is still called once per start and never retried.

- [ ] **Step 1: Write the failing test**

In `tests/test_charge_control.py`, add `UnknownChargerStateError` to the import from `pynortecgo` (alphabetical: after `UnexpectedResponseError`), and add one row to the parameters of `test_pre_check_errors`, after the `ChargerNotReleasedError` row:

```text
        (UnknownChargerStateError("mystery"), "charger_state_unknown"),
```

The test already asserts, for every row: a `ServiceValidationError` with that translation key, no chained cause, the control's state still idle (no block, no pending start), no repair issue, and `start_charge` awaited once.

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_charge_control.py -q -k test_pre_check_errors`
Expected: the new row fails with `HomeAssistantError` raised where `ServiceValidationError` was expected (the catch-all's "start failed"); the other six rows pass.

- [ ] **Step 3: Add the entry**

In `custom_components/nortec_go/charge_control.py`, add `UnknownChargerStateError` to the import from `pynortecgo` (alphabetical), and add one entry to `_PRE_CHECK_ERRORS`, after `ChargerNotReleasedError`:

```text
    UnknownChargerStateError: "charger_state_unknown",
```

The translation key `charger_state_unknown` already exists in `strings.json`; no string changes.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_charge_control.py -q`
Expected: all pass.

- [ ] **Step 5: Run the gates**

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95 -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add custom_components/nortec_go/charge_control.py tests/test_charge_control.py
git commit -F /tmp/session-cost-task-3-msg.txt
```

Message: `feat: a start refused for an unknown charger state says so (#76)`, then the co-author trailer.

---

### Task 4: Docs, changelog and decision log

**Model:** opus — a docs task (D33).
**Wave:** 1 (written against this plan's names; re-checked against the code that lands)

**Files:**
- Modify: `docs/user/nortec_go.md`
- Modify: `docs/manual-testing.md`
- Modify: `docs/releasing.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/decisions.md`

**Interfaces:**
- Consumes: the sensor names *Cost this charge* and *Last charge cost*, and the decision number D42.
- Produces: nothing other tasks use.

No test covers these files; the check is reading the result against the spec (§7, §8, §9). Lines wrap at about 110 characters, as the files do; table rows stay on one line.

- [ ] **Step 1: `docs/user/nortec_go.md`, the entity table**

In *Supported functionality* → *Charger*, add two rows after the *Charging power* row:

```markdown
| Cost this charge | Sensor | What the open charge costs so far, incl. VAT, fees and the grid tariff, in the charger's currency. Unknown when no charge is open. It can lag *Energy this charge* by a reading, and its last value can be below the billed total; while a charge is stopping it can already show the billed total |
| Last charge cost | Sensor | The billed total of the most recent completed charge on the charger. Its long-term statistics add up the charges completed after the sensor's first value. Unknown if the charge isn't among the charger's newest, or if it couldn't be read |
```

- [ ] **Step 2: `docs/user/nortec_go.md`, *Data updates***

The paragraph

```markdown
*Energy this charge* and *Charging power* come from the last charger read, so while charging they can be up
to 5 minutes old.
```

becomes

```markdown
*Energy this charge*, *Charging power* and *Cost this charge* come from the last charger read, so while
charging they can be up to 5 minutes old. *Last charge cost* follows at the first read after a charge ends,
or the one after it (up to 60 minutes later); press *Refresh* to read it sooner.
```

- [ ] **Step 3: `docs/user/nortec_go.md`, *Known limitations***

Add one item at the end of the list (after the *Charging power* item):

```markdown
- *Last charge cost* misses a charge when two charges end between two reads, or when a charge that ended
  while Home Assistant was off is no longer the most recent one. Its statistics then lack that charge.
  They also lack the charge the sensor first showed: usually one from before you added the sensor, but
  the first one after it if the sensor was unknown until then.
```

- [ ] **Step 4: `docs/user/nortec_go.md`, *Diagnostics***

In the paragraph that starts "The file leaves out your email", the sentence

```markdown
It keeps your charger's and car's names and IDs, and Home Assistant adds its own
information, such as its version, your installed custom integrations and your time zone.
```

becomes (re-wrap the paragraph)

```markdown
It keeps your charger's and car's names and IDs, and the last charge's ID, cost and time, and Home
Assistant adds its own information, such as its version, your installed custom integrations and your time
zone.
```

- [ ] **Step 5: `docs/manual-testing.md`**

In *Entities*, under *Charger*, add two lines after `- [ ] *Charging power*.`:

```markdown
- [ ] *Cost this charge*.
- [ ] *Last charge cost*.
```

- [ ] **Step 6: `docs/releasing.md`**

In *Bumping `pynortecgo`*, the checklist item on `test_client_model_fields_are_pinned` says "a changed `Charger` or `Vehicle` field". It becomes "a changed `Charger`, `CompletedCharge` or `Vehicle` field" (re-wrap the item; nothing else in it changes).

- [ ] **Step 7: `CHANGELOG.md`**

Under `## [Unreleased]` (empty today), add:

```markdown
### Added

- *Cost this charge*: what the open charge costs so far.
- *Last charge cost*: the billed total of the most recent completed charge. Its long-term statistics add
  up what the charges completed from then on cost.

### Changed

- `pynortecgo` 0.7.0. Each charger read makes one more request.
- A start refused because the charger reports an unknown state says so, instead of showing a general
  failure.
```

Keep one blank line between this block and `## [0.1.1] - 2026-09-29`.

- [ ] **Step 8: `docs/decisions.md`**

Add at the end of the file, after D41, with one blank line before it:

```markdown
### D42: Charge costs are the client's exact values
- **Date:** 2026-10-01 · **Status:** active
- **Decision:** *Cost this charge* shows the open charge's cost as `pynortecgo` reports it, with no state
  class; *Last charge cost* shows the last completed charge's billed total as `total`, with `last_reset` at
  the charge's completion time. No cost is computed from energy and price, and the unit is the charger's
  currency, then D34's order.
- **Why:** The owner chose exact values over estimates (#75). A per-charge value without `last_reset` gives a
  wrong statistics sum, and the live value ends below the bill, so only the billed totals are summed.
- **Source:** [session cost spec](superpowers/specs/2026-10-01-session-cost-design.md), Decisions and §3
```

No earlier decision changes its status.

- [ ] **Step 9: Check and commit**

Run: `uv run pytest -q` and `git diff --stat`.
Expected: the tests pass (no test reads these texts, so this only shows nothing else changed), and only the five files above changed.

```bash
git add docs/user/nortec_go.md docs/manual-testing.md docs/releasing.md CHANGELOG.md docs/decisions.md
git commit -F /tmp/session-cost-task-4-msg.txt
```

Message: `docs: the cost sensors, pynortecgo 0.7.0 and D42 (#76)`, then the co-author trailer.
