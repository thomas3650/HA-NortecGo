"""The cost of the open charge and of the last completed one, as pynortecgo reports them (D42).

The one place that reads the charges' costs: ActiveCharge.cost and CompletedCharge.cost.
"""

from datetime import datetime

from pynortecgo import Charger


def charge_cost(charger: Charger) -> float | None:
    """The open charge's cost so far, or its billed total once it is the last completed charge."""
    active = charger.active_charge
    if active is None:
        return None
    last = charger.last_charge
    if last is not None and last.id == active.id:
        return last.cost
    return active.cost


def last_charge_cost(charger: Charger) -> float | None:
    """The last completed charge's billed total, or None without a last charge."""
    last = charger.last_charge
    return None if last is None else last.cost


def last_charge_completed_at(charger: Charger) -> datetime | None:
    """When the last completed charge ended, or None without a last charge."""
    last = charger.last_charge
    return None if last is None else last.completed_at
