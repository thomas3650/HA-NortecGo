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
