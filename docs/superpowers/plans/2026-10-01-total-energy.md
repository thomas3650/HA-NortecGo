# Total energy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. In this repo the flow in `docs/way-of-working.md` §1–2 applies (implementer and task-reviewer agents, waves, worktrees).

**Goal:** A *Total energy* sensor on the charger device: the energy the charger has delivered since the integration was added, summed per charge in a stored ledger, for the Energy dashboard.

**Architecture:** Task 1 adds `energy.py`: the ledger, the pure counting rule (`advance`) and its store. Task 2 makes the coordinator load, advance and save the ledger and carry the total in its data, and shows the ledger in the diagnostics. Task 3 adds the sensor on top of the coordinator's data. Task 4 writes the docs, the changelog and D47; it runs in wave 1 next to Task 1, written against the names this plan fixes.

**Tech Stack:** Python 3.14, Home Assistant custom integration, `pynortecgo` 0.8.0 (always mocked in tests), pytest with `pytest-homeassistant-custom-component` and freezegun, uv.

**Spec:** `docs/superpowers/specs/2026-10-01-total-energy-design.md` (issue #75).

## Global Constraints

- TDD: write the failing test, see it fail, then write the code. Tests always mock `pynortecgo`, and fixtures come from `pynortecgo` model objects and the `tests/conftest.py` helpers, never raw API JSON (hard rules 2, 7).
- Never start or stop a real charge (hard rule 2). No task touches `charge_control.py`, the switch or anything on the start or stop path.
- Nothing private (hard rule 3): no IDs, tokens, emails, captures, raw endpoints, response shapes, or links into the private client repo. Name only `pynortecgo`'s public API. Test values are plainly fake.
- No client bump: `pynortecgo==0.8.0` stays in `manifest.json`, `pyproject.toml` and `uv.lock`.
- Gates before every commit: `uv run pytest -q`, then `uv run ruff check && uv run ruff format --check && uv run mypy` (the gates in `CLAUDE.md` → Commands without `actionlint` and `zizmor`: no task touches a workflow). The coverage gate (`uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95`) passes at the end of each code task.
- Subagents write commit messages with the Write tool to a file outside the repo, and commit with `git commit -F <file>` (no heredocs). End each message with the co-author trailer given in the dispatch.
- Match the surrounding code: comment density, one-line docstrings ending in a period, names. `ruff format` decides the layout; if it rewrites a line of this plan's code, keep ruff's version.
- Names, exactly:
  - module `custom_components/nortec_go/energy.py` with `ProvisionalCharge`, `EnergyLedger`, `new_ledger`, `total_kwh`, `advance`, `EnergyStore`;
  - constants `ENERGY_STORE_VERSION = 1` and `ENERGY_STORE_KEY = "nortec_go.{entry_id}.energy"`;
  - coordinator: `async_load_energy()`, the property `energy_ledger`, and `NortecGoData.total_energy_kwh`;
  - sensor key `total_energy` → the name *Total energy*; entity ID in tests `sensor.garage_charger_total_energy`; class `NortecGoTotalEnergySensor`.
- The total never goes down: an open charge keeps the highest reading seen, and a completed charge counts at the higher of its final energy and that reading (spec §2).
- State class `total_increasing`, device class `energy`, unit kWh, display precision 2; the state is the total rounded to 3 decimals.
- Decision number: D47, placed after D46.

## Review Focus

1. A reading of `0.0` kWh is a reading, not a missing one: a charge that has just started counts as 0.0 and a later `None` keeps what was there (Task 1, the `zero_then_none` row of `test_advance`, a behaviour test). No test can tell `is None` from a truthiness test here, since readings aren't negative, so the task reviewer checks by reading that `advance` tests `is None`.
2. A reload or restart in the middle of a charge counts nothing twice: the stored ledger carries the open charge (Task 1 `test_restart_with_a_charge_open`; Task 3 `test_total_energy_survives_a_reload`, which reads a lower value after the reload and expects the carried one).
3. The same charger answer read many times in a row (a *Refresh* press, the 30-second reads while stopping) leaves the total where it was (Task 1, the `same_read_three_times` row of `test_advance`).
4. A stored file written with whole numbers (`40` for 40.0 kWh) loads as floats, and a boolean is refused (Task 1 `test_store_accepts_whole_numbers` and the `bool_kwh` row of `test_store_wrong_shape`).
5. Before any charge, the sensor shows `0.0`, not unknown, so the statistics get their zero point at once (Task 3 `test_total_energy_sensor`).

## Waves

| Wave | Tasks | Notes |
|---|---|---|
| 1 | Task 1 (`energy.py`), Task 4 (docs) | Disjoint files, two worktrees off the feature branch. Task 4 is written against this plan's names. Its commit is held until Tasks 2 and 3 are on the feature branch, re-checked against that code, and picked then (*Starting ahead of inputs*) |
| 2 | Task 2 (coordinator, setup, diagnostics) | Needs Task 1 on the feature branch |
| 3 | Task 3 (the sensor) | Needs Task 2 on the feature branch |

No task has guarded files.

---

### Task 1: The ledger, the counting rule and the store

**Model:** opus — maps `pynortecgo` model fields (the open and the last completed charge) to the value an entity shows.
**Wave:** 1

**Files:**
- Create: `custom_components/nortec_go/energy.py`
- Modify: `custom_components/nortec_go/const.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_energy.py` (new)

**Interfaces:**
- Consumes: `pynortecgo` 0.8.0's public models. `Charger.active_charge: ActiveCharge | None` with `id: str` and `kwh: float | None`. `Charger.last_charge: CompletedCharge | None` with `id: str`, `kwh: float`, `completed_at: datetime` (UTC).
- Produces, in `custom_components/nortec_go/energy.py`:
  - `ProvisionalCharge(id: str, kwh: float, seen_at: datetime)`, a frozen dataclass;
  - `EnergyLedger(since: datetime, settled_kwh: float, settled_id: str | None, settled_at: datetime | None, provisional: tuple[ProvisionalCharge, ...])`, a frozen dataclass;
  - `new_ledger(now: datetime) -> EnergyLedger`;
  - `total_kwh(ledger: EnergyLedger) -> float`;
  - `advance(ledger: EnergyLedger, charger: Charger, now: datetime) -> EnergyLedger`, which returns the same object when nothing changes;
  - `EnergyStore(hass: HomeAssistant, entry_id: str)` with `async_load() -> EnergyLedger | None`, `async_save(ledger: EnergyLedger) -> None`, `async_remove() -> None`.
- Produces, in `custom_components/nortec_go/const.py`: `ENERGY_STORE_VERSION: Final = 1`, `ENERGY_STORE_KEY: Final = "nortec_go.{entry_id}.energy"`.
- Produces, in `tests/conftest.py`: `make_charger(...)` with one more keyword argument, `charge_id: str = FAKE_CHARGE_ID`, used as the open charge's ID.

- [ ] **Step 1: Let `make_charger` name the open charge**

In `tests/conftest.py`, add the keyword argument after `last_charge` in `make_charger`'s signature:

```text
    last_charge: CompletedCharge | None = None,
    charge_id: str = FAKE_CHARGE_ID,
```

and use it in the `ActiveCharge` it builds: replace `id=FAKE_CHARGE_ID,` with `id=charge_id,`.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_energy.py`:

```python
"""Tests for the Total energy ledger: the counting rule and its store (D47)."""

from datetime import UTC, datetime, timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from pynortecgo import Charger, ChargeState, CompletedCharge
import pytest

from custom_components.nortec_go.energy import (
    EnergyLedger,
    EnergyStore,
    ProvisionalCharge,
    advance,
    new_ledger,
    total_kwh,
)

from .conftest import make_charger, make_completed_charge

# The ledger's start; a read's time is given in minutes after it.
T0 = datetime(2026, 9, 27, 8, 0, tzinfo=UTC)
KEY = "nortec_go.entry1.energy"
WARNING = "Ignoring the stored energy total: it has an unexpected shape"


def _at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


def _done(charge_id: str, kwh: float, minutes: float) -> CompletedCharge:
    """A completed charge that ended the given minutes after T0."""
    return make_completed_charge(
        charge_id=charge_id, kwh=kwh, completed_at=_at(minutes)
    )


# The charge the charger listed before the ledger existed.
OLD = _done("old", 18.4, -60)


def _open(
    charge_id: str,
    kwh: float | None,
    last: CompletedCharge | None = OLD,
    state: ChargeState = ChargeState.CHARGING,
) -> Charger:
    """A charger with an open charge."""
    return make_charger(
        is_connected=True,
        charge_state=state,
        charge_kwh=kwh,
        charge_id=charge_id,
        last_charge=last,
    )


def _idle(last: CompletedCharge | None = OLD) -> Charger:
    """A charger with no open charge."""
    return make_charger(last_charge=last)


def _run(
    reads: list[tuple[float, Charger]], ledger: EnergyLedger | None = None
) -> tuple[EnergyLedger, list[float]]:
    """Advance through the reads; the totals after each, as the sensor rounds them.

    Also checks, for every read of every test, that the total never goes down.
    """
    if ledger is None:
        ledger = new_ledger(T0)
    totals = []
    for minutes, charger in reads:
        before = round(total_kwh(ledger), 3)
        ledger = advance(ledger, charger, _at(minutes))
        after = round(total_kwh(ledger), 3)
        assert after >= before, minutes
        totals.append(after)
    return ledger, totals


def test_new_ledger_and_total() -> None:
    """A new ledger counts nothing; the total is the settled sum plus the provisional charges."""
    ledger = new_ledger(T0)
    assert ledger == EnergyLedger(
        since=T0, settled_kwh=0.0, settled_id=None, settled_at=None, provisional=()
    )
    assert total_kwh(ledger) == 0.0
    assert (
        total_kwh(
            EnergyLedger(
                since=T0,
                settled_kwh=40.0,
                settled_id="a",
                settled_at=_at(5),
                provisional=(
                    ProvisionalCharge("b", 2.5, _at(10)),
                    ProvisionalCharge("c", 1.0, _at(20)),
                ),
            )
        )
        == 43.5
    )


@pytest.mark.parametrize(
    ("reads", "totals", "waiting"),
    [
        pytest.param(
            [
                (5, _open("a", 2.0)),
                (10, _open("a", 5.0)),
                (15, _idle(_done("a", 5.4, 12))),
            ],
            [2.0, 5.0, 5.4],
            [],
            id="normal_charge",
        ),
        pytest.param(
            [(5, _open("a", 5.0)), (10, _idle()), (70, _idle(_done("a", 5.4, 8)))],
            [5.0, 5.0, 5.4],
            [],
            id="closed_and_listed_late",
        ),
        pytest.param(
            [
                (5, _open("a", 5.0)),
                (10, _open("a", 5.0, _done("a", 5.4, 9), ChargeState.STOPPING)),
                (10.5, _open("a", 5.0, _done("a", 5.4, 9), ChargeState.STOPPING)),
                (11, _open("a", 5.0, None, ChargeState.STOPPING)),
                (12, _idle(_done("a", 5.4, 9))),
            ],
            [5.0, 5.4, 5.4, 5.4, 5.4],
            [],
            id="stopping_and_already_listed",
        ),
        pytest.param(
            [(5, _open("a", 3.0)), (65, _idle(_done("b", 7.0, 60)))],
            [3.0, 10.0],
            [],
            id="two_charges_end_between_reads",
        ),
        pytest.param(
            [(5, _idle()), (500, _idle(_done("a", 6.0, 400)))],
            [0.0, 6.0],
            [],
            id="ran_while_off_and_still_the_newest",
        ),
        pytest.param(
            [(5, _idle()), (500, _idle(_done("b", 7.0, 450)))],
            [0.0, 7.0],
            [],
            id="never_seen_and_a_later_one_completed",
        ),
        pytest.param(
            [(5, _idle()), (500, _open("b", 1.0, _done("a", 6.0, 400)))],
            [0.0, 7.0],
            ["b"],
            id="never_seen_but_the_later_one_still_open",
        ),
        pytest.param(
            [
                (5, _open("p", 4.0)),
                (10, _idle()),
                (40, _open("x", 1.0)),
                (45, _idle()),
                (50, _idle(_done("p", 4.5, 8))),
                (55, _idle(_done("x", 1.2, 43))),
            ],
            [4.0, 4.0, 5.0, 5.0, 5.5, 5.7],
            [],
            id="older_charge_listed_late",
        ),
        pytest.param(
            [
                (5, _open("p", 4.0)),
                (10, _idle()),
                (40, _open("x", 1.0)),
                (45, _open("x", 2.0, _done("p", 4.5, 8))),
                (50, _open("x", 3.0, _done("p", 4.5, 8))),
            ],
            [4.0, 4.0, 5.0, 6.5, 7.5],
            ["x"],
            id="previous_charge_listed_during_the_next",
        ),
        pytest.param(
            [
                (5, _open("a", 5.0)),
                (10, _open("a", 4.0)),
                (15, _idle(_done("a", 4.8, 12))),
            ],
            [5.0, 5.0, 5.0],
            [],
            id="reading_and_final_below_the_highest",
        ),
        pytest.param(
            [
                (5, _open("a", 5.0)),
                (10, _idle(None)),
                (70, _idle(_done("a", 5.4, 8))),
                (130, _idle(None)),
                (190, _idle(_done("a", 5.4, 8))),
            ],
            [5.0, 5.0, 5.4, 5.4, 5.4],
            [],
            id="last_charge_read_fails_for_a_while",
        ),
        pytest.param(
            [(5, _open("a", None)), (10, _open("a", 2.0)), (15, _open("a", None))],
            [0.0, 2.0, 2.0],
            ["a"],
            id="no_energy_reading",
        ),
        pytest.param(
            [(5, _open("a", 0.0)), (10, _open("a", None))],
            [0.0, 0.0],
            ["a"],
            id="zero_then_none",
        ),
        pytest.param(
            [(5, _idle(None)), (65, _idle())],
            [0.0, 0.0],
            [],
            id="completed_before_the_ledger_and_listed_later",
        ),
        pytest.param(
            [(5, _idle(_done("a", 6.0, 0)))],
            [0.0],
            [],
            id="completed_exactly_at_since",
        ),
        pytest.param(
            [
                (1, _open("a", 5.0, _done("a", 5.4, -1), ChargeState.STOPPING)),
                (2, _idle(_done("a", 5.4, -1))),
                (500, _idle(_done("b", 7.0, 400))),
            ],
            [5.0, 5.0, 12.0],
            [],
            id="ended_before_the_ledger_but_still_shown_open",
        ),
        pytest.param(
            [
                (5, _open("a", 1.0)),
                (10, _idle(None)),
                (20, _open("b", 2.0, None)),
                (25, _idle(None)),
            ],
            [1.0, 1.0, 3.0, 3.0],
            ["a", "b"],
            id="nothing_listed_so_both_wait",
        ),
        pytest.param(
            [
                (5, _open("a", 1.0)),
                (10, _idle(None)),
                (20, _open("b", 2.0, None)),
                (25, _idle(None)),
                (30, _idle(_done("b", 2.2, 24))),
            ],
            [1.0, 1.0, 3.0, 3.0, 3.2],
            [],
            id="the_first_listed_charge_folds_the_older_ones",
        ),
        pytest.param(
            [(5, _open("a", 2.0)), (5.5, _open("a", 2.0)), (6, _open("a", 2.0))],
            [2.0, 2.0, 2.0],
            ["a"],
            id="same_read_three_times",
        ),
        pytest.param(
            [
                (5, _open("a", 5.0)),
                (15, _idle(_done("a", 5.4, 12))),
                (20, _idle(_done("a", 5.4, 13))),
            ],
            [5.0, 5.4, 5.4],
            [],
            id="listed_again_with_a_later_time",
        ),
        pytest.param(
            [(5, _open("a", 1.0)), (10, _idle(_done("b", 7.0, 5)))],
            [1.0, 8.0],
            ["a"],
            id="seen_open_at_the_completion_time_is_not_folded",
        ),
    ],
)
def test_advance(
    reads: list[tuple[float, Charger]], totals: list[float], waiting: list[str]
) -> None:
    """The total after each read, and the charges still provisional at the end (spec §2)."""
    ledger, seen = _run(reads)
    assert seen == totals
    assert [charge.id for charge in ledger.provisional] == waiting


def test_advance_returns_the_same_ledger_when_nothing_changes() -> None:
    """With no charge open and nothing new listed, the ledger object itself comes back."""
    ledger, _ = _run([(5, _idle(_done("a", 6.0, 3)))])
    assert advance(ledger, _idle(_done("a", 6.0, 3)), _at(65)) is ledger
    assert advance(ledger, _idle(None), _at(125)) is ledger


def test_the_open_charge_is_never_folded() -> None:
    """An open charge last seen before another charge completed stays provisional, counted once."""
    start = EnergyLedger(
        since=T0,
        settled_kwh=0.0,
        settled_id=None,
        settled_at=None,
        provisional=(ProvisionalCharge("x", 1.0, _at(5)),),
    )
    ledger, totals = _run([(20, _open("x", 1.5, _done("p", 4.0, 10)))], start)
    assert totals == [5.5]
    assert ledger.settled_kwh == 4.0
    assert ledger.provisional == (ProvisionalCharge("x", 1.5, _at(20)),)


def test_settling_moves_the_ledger_on() -> None:
    """A counted charge becomes the settled one; seeing a charge open moves its seen_at."""
    ledger, _ = _run([(5, _open("a", 2.0)), (10, _open("a", 3.0))])
    assert ledger.provisional == (ProvisionalCharge("a", 3.0, _at(10)),)
    ledger, _ = _run([(15, _idle(_done("a", 3.4, 12)))], ledger)
    assert ledger == EnergyLedger(
        since=T0,
        settled_kwh=3.4,
        settled_id="a",
        settled_at=_at(12),
        provisional=(),
    )


STORED = EnergyLedger(
    since=T0,
    settled_kwh=40.5,
    settled_id="a",
    settled_at=_at(12),
    provisional=(
        ProvisionalCharge("b", 2.5, _at(20)),
        ProvisionalCharge("c", 0.0, _at(30)),
    ),
)
STORED_DATA: dict[str, Any] = {
    "since": "2026-09-27T08:00:00+00:00",
    "settled_kwh": 40.5,
    "settled_id": "a",
    "settled_at": "2026-09-27T08:12:00+00:00",
    "provisional": [
        {"id": "b", "kwh": 2.5, "seen_at": "2026-09-27T08:20:00+00:00"},
        {"id": "c", "kwh": 0.0, "seen_at": "2026-09-27T08:30:00+00:00"},
    ],
}


def _file(data: Any) -> dict[str, Any]:
    return {"version": 1, "minor_version": 1, "key": KEY, "data": data}


async def test_store_round_trip(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """A ledger with a settled charge and two provisional ones survives save and load."""
    store = EnergyStore(hass, "entry1")
    await store.async_save(STORED)
    assert hass_storage[KEY]["version"] == 1
    assert hass_storage[KEY]["data"] == STORED_DATA
    assert await EnergyStore(hass, "entry1").async_load() == STORED
    await store.async_remove()
    assert KEY not in hass_storage


async def test_store_round_trip_of_a_new_ledger(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """A ledger with no settled charge keeps its two None fields."""
    await EnergyStore(hass, "entry1").async_save(new_ledger(T0))
    assert hass_storage[KEY]["data"] == {
        "since": "2026-09-27T08:00:00+00:00",
        "settled_kwh": 0.0,
        "settled_id": None,
        "settled_at": None,
        "provisional": [],
    }
    assert await EnergyStore(hass, "entry1").async_load() == new_ledger(T0)


async def test_store_missing_file(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """No file gives None, without a warning."""
    assert await EnergyStore(hass, "entry1").async_load() is None
    assert WARNING not in caplog.text


async def test_store_accepts_whole_numbers(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Energy stored as a whole number loads as a float."""
    data = {**STORED_DATA, "settled_kwh": 40}
    hass_storage[KEY] = _file(data)
    ledger = await EnergyStore(hass, "entry1").async_load()
    assert ledger is not None
    assert ledger.settled_kwh == 40.0
    assert isinstance(ledger.settled_kwh, float)


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(
            {k: v for k, v in STORED_DATA.items() if k != "settled_kwh"},
            id="missing_key",
        ),
        pytest.param({**STORED_DATA, "settled_kwh": "40.5"}, id="text_kwh"),
        pytest.param({**STORED_DATA, "settled_kwh": True}, id="bool_kwh"),
        pytest.param({**STORED_DATA, "settled_id": 5}, id="number_as_id"),
        pytest.param({**STORED_DATA, "since": "nonsense"}, id="time_does_not_parse"),
        pytest.param(
            {**STORED_DATA, "since": "2026-09-27T08:00:00"}, id="time_without_zone"
        ),
        pytest.param({**STORED_DATA, "settled_at": 12}, id="number_as_time"),
        pytest.param({**STORED_DATA, "provisional": None}, id="no_provisional_list"),
        pytest.param(
            {**STORED_DATA, "provisional": [{"id": "b", "seen_at": "nonsense"}]},
            id="provisional_item_missing_kwh",
        ),
        pytest.param(
            {**STORED_DATA, "provisional": [{"id": 7, "kwh": 1.0, "seen_at": None}]},
            id="provisional_item_wrong_types",
        ),
        pytest.param([], id="not_an_object"),
    ],
)
async def test_store_wrong_shape(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
    data: Any,
) -> None:
    """A file of the wrong shape gives None and one warning."""
    hass_storage[KEY] = _file(data)
    with caplog.at_level(logging.WARNING):
        assert await EnergyStore(hass, "entry1").async_load() is None
    assert caplog.text.count(WARNING) == 1


async def test_restart_with_a_charge_open(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """A ledger saved with a charge open and loaded again counts the charge once."""
    ledger, totals = _run([(5, _open("a", 2.0)), (10, _open("a", 3.0))])
    await EnergyStore(hass, "entry1").async_save(ledger)
    loaded = await EnergyStore(hass, "entry1").async_load()
    assert loaded is not None
    assert loaded == ledger
    _, later = _run([(15, _open("a", 4.0)), (20, _idle(_done("a", 4.3, 18)))], loaded)
    assert totals + later == [2.0, 3.0, 4.0, 4.3]
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_energy.py -q`
Expected: an import error at collection, `No module named 'custom_components.nortec_go.energy'`.

- [ ] **Step 4: Add the constants**

In `custom_components/nortec_go/const.py`, after the `PRICE_STORE_KEY` line, with a blank line before the block:

```python
# The Total energy ledger (D47).
ENERGY_STORE_VERSION: Final = 1
ENERGY_STORE_KEY: Final = "nortec_go.{entry_id}.energy"
```

- [ ] **Step 5: Write `energy.py`**

Create `custom_components/nortec_go/energy.py`:

```python
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
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/test_energy.py -q`
Expected: all pass.

If a `test_store_wrong_shape` row passes a shape through instead of raising (for example a `provisional` that is a text), make the parser refuse it with a `TypeError`; don't loosen the test.

- [ ] **Step 7: Run the gates**

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run mypy`
Then: `uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95`
Expected: all pass, and `energy.py` has no missed lines. If `ruff format --check` fails, run `uv run ruff format` and keep its layout.

- [ ] **Step 8: Commit**

```bash
git add custom_components/nortec_go/energy.py custom_components/nortec_go/const.py tests/conftest.py tests/test_energy.py
git commit -F <message file>
```

Message: `feat: the Total energy ledger and its store (#75)`, then the co-author trailer.

---

### Task 2: The coordinator, setup and diagnostics

**Model:** opus — carries the mapped client values into the coordinator's data, in the read path next to the charge control.
**Wave:** 2

**Files:**
- Modify: `custom_components/nortec_go/coordinator.py`
- Modify: `custom_components/nortec_go/__init__.py`
- Modify: `custom_components/nortec_go/diagnostics.py`
- Modify: `custom_components/nortec_go/costs.py` (the module docstring only)
- Test: `tests/test_coordinator.py`, `tests/test_init.py`, `tests/test_diagnostics.py`

**Interfaces:**
- Consumes, from `custom_components/nortec_go/energy.py` (Task 1): `EnergyLedger`, `EnergyStore(hass, entry_id)` with `async_load() -> EnergyLedger | None`, `async_save(ledger) -> None`, `async_remove() -> None`; `new_ledger(now) -> EnergyLedger`; `advance(ledger, charger, now) -> EnergyLedger` (the same object when nothing changes); `total_kwh(ledger) -> float`. The store's key is `nortec_go.<entry id>.energy`, and its data has the keys `since`, `settled_kwh`, `settled_id`, `settled_at`, `provisional` (a list of objects with `id`, `kwh`, `seen_at`), times as ISO 8601 strings.
- Produces:
  - `NortecGoData.total_energy_kwh: float`, a required field after `read_at`;
  - `NortecGoCoordinator.async_load_energy() -> None`, called by `async_setup_entry` before the first refresh;
  - `NortecGoCoordinator.energy_ledger`, a read-only property returning the `EnergyLedger`;
  - the diagnostics download's top-level `energy` key, for a loaded entry.

- [ ] **Step 1: Write the failing coordinator tests**

In `tests/test_coordinator.py`:

1. Add `import copy` at the top (alphabetical: after `import asyncio`).
2. Add `from custom_components.nortec_go.energy import EnergyStore` after the `coordinator` import block.
3. Add `ENERGY_STORE_KEY = "nortec_go.{}.energy"` after the `STORE_KEY` line.
4. Add these tests at the end of the file:

```python
def _charging(kwh: float) -> Charger:
    """A charger with a charge open at the given energy."""
    return make_charger(
        is_connected=True, charge_state=ChargeState.CHARGING, charge_kwh=kwh
    )


async def test_first_setup_creates_and_saves_the_energy_ledger(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """With no stored ledger, setup makes one that starts now and saves it before any charge."""
    freezer.move_to(MIDNIGHT)
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    key = ENERGY_STORE_KEY.format(mock_config_entry.entry_id)
    assert hass_storage[key]["version"] == 1
    assert hass_storage[key]["data"] == {
        "since": "2026-09-26T22:00:00+00:00",
        "settled_kwh": 0.0,
        "settled_id": None,
        "settled_at": None,
        "provisional": [],
    }
    assert coordinator.energy_ledger.since == MIDNIGHT
    assert coordinator.data.total_energy_kwh == 0.0


async def test_stored_energy_ledger_loaded_at_setup(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """A stored ledger is loaded, and a charge open across the restart carries on from it."""
    freezer.move_to(MIDNIGHT)
    key = ENERGY_STORE_KEY.format(mock_config_entry.entry_id)
    hass_storage[key] = {
        "version": 1,
        "minor_version": 1,
        "key": key,
        "data": {
            "since": "2026-09-20T08:00:00+00:00",
            "settled_kwh": 40.0,
            "settled_id": "fake-earlier-charge-id",
            "settled_at": "2026-09-25T06:15:00+00:00",
            "provisional": [
                {
                    "id": FAKE_CHARGE_ID,
                    "kwh": 2.0,
                    "seen_at": "2026-09-26T21:55:00+00:00",
                }
            ],
        },
    }
    mock_client.get_charger.return_value = _charging(3.5)
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    assert coordinator.data.total_energy_kwh == 43.5
    assert coordinator.energy_ledger.since == datetime(2026, 9, 20, 8, 0, tzinfo=UTC)
    assert hass_storage[key]["data"]["provisional"] == [
        {"id": FAKE_CHARGE_ID, "kwh": 3.5, "seen_at": "2026-09-26T22:00:00+00:00"}
    ]


async def test_energy_ledger_saved_only_when_it_changes(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A read that changes nothing doesn't save; a read with an open charge does."""
    freezer.move_to(MIDNIGHT)
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    with patch.object(EnergyStore, "async_save", autospec=True) as save:
        freezer.tick(INTERVAL_IDLE)
        await coordinator.async_refresh()
        save.assert_not_awaited()
        assert coordinator.data.total_energy_kwh == 0.0

        mock_client.get_charger.return_value = _charging(1.0)
        freezer.tick(INTERVAL_IDLE)
        await coordinator.async_refresh()
        save.assert_awaited_once()
        assert coordinator.data.total_energy_kwh == 1.0


async def test_failed_reads_leave_the_energy_ledger(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """A failed charger read, and a read whose car read is rejected, move nothing."""
    freezer.move_to(MIDNIGHT)
    mock_client.get_charger.return_value = _charging(1.0)
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    key = ENERGY_STORE_KEY.format(mock_config_entry.entry_id)
    ledger = coordinator.energy_ledger
    stored = copy.deepcopy(hass_storage[key]["data"])

    freezer.tick(INTERVAL_CHARGING)
    mock_client.get_charger.side_effect = NortecGoConnectionError("network down")
    await coordinator.async_refresh()
    assert not coordinator.last_update_success
    assert coordinator.energy_ledger is ledger
    assert hass_storage[key]["data"] == stored

    mock_client.get_charger.side_effect = None
    mock_client.get_charger.return_value = _charging(2.0)
    mock_client.get_vehicle.side_effect = AuthError("token rejected")
    freezer.tick(INTERVAL_CHARGING)
    with patch.object(ConfigEntry, "async_start_reauth"):
        await coordinator.async_read_now(with_car=True)
    assert coordinator.energy_ledger is ledger
    assert hass_storage[key]["data"] == stored
    assert coordinator.data.total_energy_kwh == 1.0


async def test_wrong_shaped_energy_store_starts_a_new_ledger(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A stored ledger of the wrong shape is replaced by a new one that starts at 0."""
    freezer.move_to(MIDNIGHT)
    key = ENERGY_STORE_KEY.format(mock_config_entry.entry_id)
    hass_storage[key] = {
        "version": 1,
        "minor_version": 1,
        "key": key,
        "data": {"since": "nonsense"},
    }
    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert _coordinator(mock_config_entry).data.total_energy_kwh == 0.0
    assert hass_storage[key]["data"]["since"] == "2026-09-26T22:00:00+00:00"
    assert "Ignoring the stored energy total" in caplog.text
```

5. Add `Charger` to the import from `pynortecgo` (alphabetical: before `ChargerNotFoundError`), and `FAKE_CHARGE_ID` to the import from `.conftest` (before `FAKE_CHARGER_ID`).

- [ ] **Step 2: Write the failing setup and diagnostics tests**

In `tests/test_init.py`, after `test_remove_entry_removes_stored_prices`:

```python
async def test_remove_entry_removes_the_stored_energy_ledger(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    hass_storage: dict[str, Any],
) -> None:
    """Deleting the entry deletes its stored Total energy ledger."""
    await setup_integration(hass, mock_config_entry)
    key = f"nortec_go.{mock_config_entry.entry_id}.energy"
    assert key in hass_storage
    assert await hass.config_entries.async_remove(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert key not in hass_storage
```

In `tests/test_diagnostics.py`, in `test_diagnostics_output`, add the expected `energy` key after the `"prices": {...},` item of the expected dict. The test's clock is frozen at `NOON` (2026-09-27 10:00 UTC), its last charge completed before that, and its open charge reads 4.2 kWh:

```text
        "energy": {
            "since": "2026-09-27T10:00:00+00:00",
            "settled_kwh": 0.0,
            "settled_id": None,
            "settled_at": None,
            "provisional": [
                {
                    "id": FAKE_CHARGE_ID,
                    "kwh": 4.2,
                    "seen_at": "2026-09-27T10:00:00+00:00",
                }
            ],
        },
```

`test_failed_setup` and `test_unloaded_entry` compare the whole download of an entry that isn't loaded, so they already pin that it has no `energy` key; they don't change.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_coordinator.py tests/test_init.py tests/test_diagnostics.py -q`
Expected: the five new coordinator tests fail (`AttributeError`: no `energy_ledger`, or a `KeyError` on the storage key), `test_remove_entry_removes_the_stored_energy_ledger` fails on `assert key in hass_storage`, and `test_diagnostics_output` fails on the missing `energy` key. Everything else passes.

- [ ] **Step 4: The coordinator**

In `custom_components/nortec_go/coordinator.py`:

1. Add the import, after the `.const` import block and before the `.prices` import (alphabetical by module):

```python
from .energy import EnergyLedger, EnergyStore, advance, new_ledger, total_kwh
```

2. `NortecGoData` gets the total. Its docstring and fields become:

```text
    """One read of the charger and the car, with the charge control's state.

    vehicle is None when the account has no single car, at setup or since (D44). read_at is
    when the charger was last read successfully. total_energy_kwh is the energy ledger's total
    after this read (D47).
    """

    charger: Charger
    vehicle: Vehicle | None
    control: ChargeControlState
    read_at: datetime
    total_energy_kwh: float
```

3. In `__init__`, after the `self._price_store = PriceStore(hass, entry.entry_id)` line:

```text
        self._energy_store = EnergyStore(hass, entry.entry_id)
        # A placeholder until async_load_energy; nothing reads or saves it.
        self._energy = new_ledger(dt_util.utcnow())
```

4. After the `price_retry_pending` property, add:

```text
    @property
    def energy_ledger(self) -> EnergyLedger:
        """The ledger Total energy is summed from (D47)."""
        return self._energy
```

5. At the end of `_async_update_data`, the last lines become:

```text
        control = self.charge_control.state
        self.update_interval = interval_for(charger, control, timedelta(0))
        # Last: every read that can fail this update is done, so a failed update moves nothing.
        await self._async_advance_energy(charger, read_at)
        return NortecGoData(
            charger=charger,
            vehicle=vehicle,
            control=control,
            read_at=read_at,
            total_energy_kwh=total_kwh(self._energy),
        )
```

6. After `_async_read_charger`, add:

```text
    async def _async_advance_energy(self, charger: Charger, read_at: datetime) -> None:
        """Count the read in the energy ledger, and save the ledger when it changed (D47)."""
        advanced = advance(self._energy, charger, read_at)
        if advanced is not self._energy:
            self._energy = advanced
            await self._energy_store.async_save(advanced)
```

7. Before `async_load_prices`, add:

```text
    async def async_load_energy(self) -> None:
        """Load the stored energy ledger, or start a new one (D47).

        A new one is saved at once, so its start survives a restart that comes before the first
        charge: a charge that then runs while Home Assistant is off still counts.
        """
        ledger = await self._energy_store.async_load()
        if ledger is None:
            ledger = new_ledger(dt_util.utcnow())
            await self._energy_store.async_save(ledger)
        self._energy = ledger
```

- [ ] **Step 5: Setup and removal**

In `custom_components/nortec_go/__init__.py`:

1. Add `from .energy import EnergyStore` after the `.coordinator` import (alphabetical by module: before `.entry`).
2. In `async_setup_entry`, after `await coordinator.async_load_prices()`:

```text
    await coordinator.async_load_energy()
```

3. `async_remove_entry` becomes:

```python
async def async_remove_entry(hass: HomeAssistant, entry: NortecGoConfigEntry) -> None:
    """Delete the entry's stored prices, energy ledger and charge control, and its repair issue."""
    await PriceStore(hass, entry.entry_id).async_remove()
    await EnergyStore(hass, entry.entry_id).async_remove()
    await async_remove_charge_control(hass, entry.entry_id)
```

- [ ] **Step 6: Diagnostics and the `costs.py` docstring**

In `custom_components/nortec_go/diagnostics.py`, in the dict passed to `diagnostics.update`, after the `"prices": {...},` item:

```text
            # The Total energy ledger; charge IDs aren't secrets (D38).
            "energy": asdict(coordinator.energy_ledger),
```

In `custom_components/nortec_go/costs.py`, the module docstring becomes:

```python
"""The cost of the open charge and of the last completed one, as pynortecgo reports them (D42).

The one place that reads the charges' costs: ActiveCharge.cost and CompletedCharge.cost.
"""
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `uv run pytest tests/test_coordinator.py tests/test_init.py tests/test_diagnostics.py -q`
Expected: all pass.

- [ ] **Step 8: Run the gates**

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run mypy`
Then: `uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95`
Expected: all pass. If `ruff format --check` fails, run `uv run ruff format` and keep its layout.

- [ ] **Step 9: Commit**

```bash
git add custom_components/nortec_go/coordinator.py custom_components/nortec_go/__init__.py custom_components/nortec_go/diagnostics.py custom_components/nortec_go/costs.py tests/test_coordinator.py tests/test_init.py tests/test_diagnostics.py
git commit -F <message file>
```

Message: `feat: the coordinator keeps the Total energy ledger (#75)`, then the co-author trailer.

---

### Task 3: The sensor

**Model:** sonnet — an entity that shows one float from the coordinator's data; no auth, start or stop, and no mapping of client models (Task 1 did that).
**Wave:** 3

**Files:**
- Modify: `custom_components/nortec_go/sensor.py`
- Modify: `custom_components/nortec_go/strings.json`, `custom_components/nortec_go/translations/en.json`
- Test: `tests/test_sensor.py`

**Interfaces:**
- Consumes: `NortecGoData.total_energy_kwh: float` (Task 2), read as `coordinator.data.total_energy_kwh`. `make_charger(..., charge_id: str = FAKE_CHARGE_ID)` and `make_completed_charge(*, charge_id, cost, kwh, completed_at)` from `tests/conftest.py`.
- Produces: the entity `sensor.garage_charger_total_energy` (in tests), unique ID `<charger id>_total_energy`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_sensor.py`, after `test_charge_energy_starts_a_new_cycle_per_charge` and before the `COST = ...` line:

```python
TOTAL = "sensor.garage_charger_total_energy"


async def test_total_energy_sensor(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Total energy: classes, unit, precision, charger device; 0.0 before any charge."""
    await setup_integration(hass, mock_config_entry)
    charger = _device(device_registry, mock_config_entry, str(FAKE_CHARGER_ID))
    assert charger is not None

    state = hass.states.get(TOTAL)
    assert state is not None
    assert state.state == "0.0"
    assert state.attributes[ATTR_DEVICE_CLASS] == SensorDeviceClass.ENERGY
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfEnergy.KILO_WATT_HOUR
    assert state.attributes[ATTR_STATE_CLASS] == SensorStateClass.TOTAL_INCREASING
    assert ATTR_LAST_RESET not in state.attributes
    entry = entity_registry.async_get(TOTAL)
    assert entry is not None
    assert entry.unique_id == f"{FAKE_CHARGER_ID}_total_energy"
    assert entry.device_id == charger.id
    assert entry.entity_category is None
    assert entry.disabled_by is None
    assert entry.options["sensor"]["suggested_display_precision"] == 2


async def _read(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    minutes: float,
    charger: Charger,
) -> str:
    """Read the given charger at MIDNIGHT plus the minutes; Total energy's state after it."""
    freezer.move_to(MIDNIGHT + timedelta(minutes=minutes))
    mock_client.get_charger.return_value = charger
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    return _state(hass, TOTAL)


async def test_total_energy_across_a_charge(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """It grows while the charge is open, holds when it closed, and takes the final energy."""
    freezer.move_to(MIDNIGHT)
    await setup_integration(hass, mock_config_entry)
    done = make_completed_charge(
        charge_id=FAKE_CHARGE_ID,
        kwh=5.4,
        completed_at=MIDNIGHT + timedelta(minutes=12),
    )
    seen = [
        await _read(hass, mock_config_entry, mock_client, freezer, minutes, charger)
        for minutes, charger in (
            (
                5,
                make_charger(
                    is_connected=True, charge_state=ChargeState.CHARGING, charge_kwh=2.0
                ),
            ),
            (
                10,
                make_charger(
                    is_connected=True, charge_state=ChargeState.CHARGING, charge_kwh=5.0
                ),
            ),
            (15, make_charger(is_connected=True)),
            (20, make_charger(is_connected=True, last_charge=done)),
            (80, make_charger(is_connected=True, last_charge=done)),
        )
    ]
    assert seen == ["2.0", "5.0", "5.0", "5.4", "5.4"]


async def test_total_energy_is_rounded(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The state is rounded to 3 decimals, so it carries no noise from adding floats."""
    freezer.move_to(MIDNIGHT)
    await setup_integration(hass, mock_config_entry)
    earlier = make_completed_charge(
        kwh=0.1, completed_at=MIDNIGHT + timedelta(minutes=5)
    )
    assert (
        await _read(
            hass,
            mock_config_entry,
            mock_client,
            freezer,
            10,
            make_charger(last_charge=earlier),
        )
        == "0.1"
    )
    # 0.1 + 0.2 is 0.30000000000000004 as floats.
    assert (
        await _read(
            hass,
            mock_config_entry,
            mock_client,
            freezer,
            20,
            make_charger(
                is_connected=True,
                charge_state=ChargeState.CHARGING,
                charge_kwh=0.2,
                last_charge=earlier,
            ),
        )
        == "0.3"
    )
    assert (
        await _read(
            hass,
            mock_config_entry,
            mock_client,
            freezer,
            25,
            make_charger(
                is_connected=True,
                charge_state=ChargeState.CHARGING,
                charge_kwh=1.23456,
                last_charge=earlier,
            ),
        )
        == "1.335"
    )


async def test_total_energy_unavailable_after_a_failed_read(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A failed charger read makes it unavailable; the next good read brings the total back."""
    mock_client.get_charger.return_value = make_charger(
        is_connected=True, charge_state=ChargeState.CHARGING, charge_kwh=2.0
    )
    await setup_integration(hass, mock_config_entry)
    assert _state(hass, TOTAL) == "2.0"
    mock_client.get_charger.side_effect = NortecGoConnectionError("network down")
    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, TOTAL) == STATE_UNAVAILABLE
    mock_client.get_charger.side_effect = None
    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, TOTAL) == "2.0"


async def test_total_energy_survives_a_reload(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A reload in the middle of a charge carries the charge: its highest reading stays."""
    mock_client.get_charger.return_value = make_charger(
        is_connected=True, charge_state=ChargeState.CHARGING, charge_kwh=2.0
    )
    await setup_integration(hass, mock_config_entry)
    assert _state(hass, TOTAL) == "2.0"
    # A lower reading after the reload: a ledger that wasn't saved and loaded would show 1.5.
    mock_client.get_charger.return_value = make_charger(
        is_connected=True, charge_state=ChargeState.CHARGING, charge_kwh=1.5
    )
    await hass.config_entries.async_reload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert _state(hass, TOTAL) == "2.0"
```

`_device` is defined further down in the file; that is fine, it is looked up when the test runs.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_sensor.py -q -k total_energy`
Expected: the five tests fail on `assert state is not None` (no such entity).

- [ ] **Step 3: The names**

In `custom_components/nortec_go/strings.json` and in `custom_components/nortec_go/translations/en.json`, under `entity` → `sensor`, add after the `charge_energy` entry:

```text
      "total_energy": {
        "name": "Total energy"
      },
```

The two files stay equal (`tests/test_init.py::test_translations_match_strings`).

- [ ] **Step 4: The sensor**

In `custom_components/nortec_go/sensor.py`:

1. The module docstring becomes:

```python
"""Nortec Go sensors: the price for EV Smart Charging, the charge status, the open charge's energy, power and cost, the total energy, the last charge's cost, the last read and the car's values."""
```

2. In `async_setup_entry`, the first list becomes:

```text
    entities: list[SensorEntity] = [
        NortecGoPriceSensor(coordinator),
        NortecGoChargeStatusSensor(coordinator),
        NortecGoLastReadSensor(coordinator),
        NortecGoTotalEnergySensor(coordinator),
    ]
```

3. After the `NortecGoChargeSensor` class, add:

```python
class NortecGoTotalEnergySensor(NortecGoChargerEntity, SensorEntity):
    """The energy delivered since the integration was added, summed per charge (D47)."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    # total_increasing: a restart from 0 (a lost store, a re-added entry) is a new cycle.
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: NortecGoCoordinator) -> None:
        """Name the sensor Total energy."""
        super().__init__(coordinator, "total_energy")

    @property
    def native_value(self) -> float:
        """The ledger's total, rounded so the state carries no noise from adding floats."""
        return round(self.coordinator.data.total_energy_kwh, 3)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_sensor.py tests/test_init.py -q`
Expected: all pass.

- [ ] **Step 6: Run the gates**

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run mypy`
Then: `uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95`
Expected: all pass. If another test pins the list of the integration's entities and now fails, add `sensor.garage_charger_total_energy` to its list; change nothing else in it.

- [ ] **Step 7: Commit**

```bash
git add custom_components/nortec_go/sensor.py custom_components/nortec_go/strings.json custom_components/nortec_go/translations/en.json tests/test_sensor.py
git commit -F <message file>
```

Message: `feat: the Total energy sensor (#75)`, then the co-author trailer.

---

### Task 4: Docs, changelog and decision log

**Model:** opus — a docs task (D33).
**Wave:** 1 (written against this plan's names; re-checked against the code that lands)

**Files:**
- Modify: `docs/user/nortec_go.md`
- Modify: `docs/manual-testing.md`
- Modify: `docs/ha-notes.md`
- Modify: `docs/decisions.md`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: the names in *Global Constraints*: the sensor *Total energy*, D47, the spec's path.
- Produces: nothing other tasks use.

No tests: the gate for this task is `uv run pre-commit run --files <the five files>`, and the re-check against the landed code. No hook checks links: the task reviewer checks the one new link (D47's Source) by hand.

- [ ] **Step 1: The user docs, *Supported functionality***

In `docs/user/nortec_go.md`, in the *Charger* table:

1. In the *Energy this charge* row, replace the last sentence, `It can be added to the Energy dashboard as an individual device; each charge counts as a new cycle`, with `For the Energy dashboard, use *Total energy*`.
2. Add a row right after the *Energy this charge* row:

```text
| Total energy | Sensor | The energy the charger has delivered since you added the integration, in kWh, kept across restarts. Use it for the Energy dashboard (see *Use cases*) |
```

- [ ] **Step 2: The user docs, *Use cases***

After the *Smart charging with EV Smart Charging* section (its last paragraph ends "planning one continuous session suits it best.") and before `## Starting a charge`, add:

```markdown
### The charger in the Energy dashboard

In **Settings** > **Dashboards** > **Energy**, add an individual device with *Total energy* as its energy
sensor and, if you like, *Charging power* as its power sensor.

Don't add *Energy this charge* as well: the charger would be counted twice. If you added it before *Total
energy* existed, replace it.
```

- [ ] **Step 3: The user docs, *Data updates***

After the sentence that ends "press *Refresh* to read it sooner." (the paragraph on *Energy this charge*, *Charging power*, *Cost this charge* and *Last charge cost*), add to the same paragraph:

```text
*Total energy* follows the same reads. While a charge runs it grows with *Energy this charge*. When the
charge ends, it moves up to the charge's final energy at the read that first lists the charge as completed
(see *Known limitations* for when that doesn't happen).
```

- [ ] **Step 4: The user docs, *Known limitations***

Replace the item that starts "The Energy dashboard sees a new charge only when *Energy this charge* starts well below" (four lines, ending "Energy delivered after the last read of a charge isn't counted either.") with these five items:

```markdown
- *Total energy* misses the end of a charge when a newer charge has completed before the charger was read
  again (two charges end between two reads, or a newer charge ends while Home Assistant is off). The older
  charge then keeps its highest reading, and the energy delivered after that reading isn't counted.
- A charge that the integration never read while it was open (it started and ended between two reads, which
  are up to 60 minutes apart, or while Home Assistant was off) is counted only if it is still the charger's
  most recent completed charge at the next read.
- *Total energy* starts at 0 when you add the integration, and again if you remove the integration and add
  it back. The Energy dashboard keeps its history.
- *Total energy* never goes down. In the rare case that a charge's final energy is below a reading taken
  while it ran, the reading counts.
- *Energy this charge* restarts with every charge, so it isn't meant for the Energy dashboard: a charge that
  follows a very short one, or that is first read late, can be missed there.
```

- [ ] **Step 5: The user docs, *Diagnostics***

Replace the sentence `It keeps your charger's and car's names and IDs, and the last charge's ID, cost, energy and time.` (it starts in the middle of a line, after "password is never stored.", and wraps over two lines) with the text below, and reflow the paragraph to the file's line width:

```text
It keeps your charger's and car's names and IDs, the last charge's ID, cost, energy and time, and the IDs,
energy and times behind *Total energy*.
```

- [ ] **Step 6: The manual test guide**

In `docs/manual-testing.md`:

1. Under *Entities* → *Charger*, add after the `- [ ] *Energy this charge*.` line:

```text
- [ ] *Total energy*.
```

2. In *Pitfalls*, the first item's last clause, `which are there to prevent a second card hold.`, becomes `which are there to prevent a second card hold, and restarts *Total energy* at 0.`

- [ ] **Step 7: The HA notes**

In `docs/ha-notes.md`, replace the item that starts "For a sensor with `state_class` `total_increasing`, the recorder's statistics skip non-numeric states" (four lines) with these two items:

```markdown
- For a sensor with `state_class` `total_increasing`, the recorder's statistics skip non-numeric states
  (unknown, unavailable) and start a new cycle only when the value drops below 90% of the previous one: the
  sum carries on, and the new value is added in full. The test is against the sensor's whole value, so on a
  small total a small drop is a new cycle too. A drop to 90% or more is a dip: its negative change is added
  to the sum, and from an entity's second dip after a start Home Assistant logs a warning, once per run,
  that asks the user to report it to the integration. So a per-charge counter may go unknown between
  charges, but a new cycle whose first value is at least 90% of the last one is missed, and a
  `total_increasing` value should never go down by itself.
- A value that can restart from 0 outside the integration's control (a lost store, an entry removed and
  added again) is `total_increasing`: plain `total` would count the restart as a negative change.
```

- [ ] **Step 8: The changelog**

In `CHANGELOG.md`, under `## [Unreleased]`:

```markdown
### Added

- *Total energy*: the energy the charger has delivered since you added the integration, kept across
  restarts. Use it as the charger's individual device in the Energy dashboard, instead of *Energy this
  charge*.
```

- [ ] **Step 9: The decision log**

At the end of `docs/decisions.md`, after D46:

```markdown
### D47: Total energy is summed in the integration
- **Date:** 2026-10-01 · **Status:** active
- **Decision:** *Total energy* is summed by the integration from the per-charge energy `pynortecgo`
  reports, in a stored ledger that starts at 0: each completed charge once, by its charge ID, at its final
  energy, and the open charge at its live reading. It is `total_increasing` and never goes down: a charge
  whose final record never arrives, or is lower, keeps its highest live reading.
- **Why:** The client can't expose a lifetime meter (the owner, #75), and *Energy this charge* restarts
  with every charge, so the Energy dashboard can miss charges. This replaces the owner's earlier answer on
  #75 to wait for the client.
- **Source:** [total energy spec](superpowers/specs/2026-10-01-total-energy-design.md), Decisions and §2
```

- [ ] **Step 10: Check and commit**

Run: `uv run pre-commit run --files docs/user/nortec_go.md docs/manual-testing.md docs/ha-notes.md docs/decisions.md CHANGELOG.md`
Expected: all hooks pass. If a hook reformats a file, run it again until it passes without changes.

```bash
git add docs/user/nortec_go.md docs/manual-testing.md docs/ha-notes.md docs/decisions.md CHANGELOG.md
git commit -F <message file>
```

Message: `docs: Total energy in the user docs, the notes, the changelog and D47 (#75)`, then the co-author trailer.
