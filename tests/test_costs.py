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
