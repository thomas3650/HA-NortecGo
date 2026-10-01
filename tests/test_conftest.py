"""Tests for the helpers in conftest.py."""

from typing import Any

from pynortecgo import ChargeState
import pytest

from .conftest import make_charger


@pytest.mark.parametrize("name", ["charge_kwh", "charge_kw", "charge_cost"])
def test_charge_value_without_a_charge_state_is_refused(name: str) -> None:
    """Each charge value alone is refused, and the message names exactly that one."""
    kwargs: dict[str, Any] = {name: 1.0}
    with pytest.raises(ValueError) as excinfo:
        make_charger(**kwargs)
    assert (
        str(excinfo.value)
        == f"{name} given without a charge_state: there is no open charge"
    )


def test_zero_counts_as_a_given_charge_value() -> None:
    """A value of 0.0 is a value, so it is refused too."""
    with pytest.raises(ValueError) as excinfo:
        make_charger(charge_cost=0.0)
    assert (
        str(excinfo.value)
        == "charge_cost given without a charge_state: there is no open charge"
    )


def test_every_refused_charge_value_is_named_in_signature_order() -> None:
    """All given values are named, in the signature's order, not the call's."""
    with pytest.raises(ValueError) as excinfo:
        make_charger(charge_cost=3.0, charge_kw=2.0, charge_kwh=1.0)
    assert str(excinfo.value) == (
        "charge_kwh, charge_kw, charge_cost given without a charge_state: "
        "there is no open charge"
    )


def test_no_charge_values_and_no_charge_state_gives_no_open_charge() -> None:
    """The plain call still builds a charger with no open charge."""
    assert make_charger().active_charge is None


def test_charge_values_with_a_charge_state_are_kept() -> None:
    """With a charge state, the open charge holds the three values."""
    charger = make_charger(
        charge_state=ChargeState.CHARGING,
        charge_kwh=1.5,
        charge_kw=2.3,
        charge_cost=4.0,
    )
    active = charger.active_charge
    assert active is not None
    assert (active.kwh, active.kw, active.cost) == (1.5, 2.3, 4.0)
