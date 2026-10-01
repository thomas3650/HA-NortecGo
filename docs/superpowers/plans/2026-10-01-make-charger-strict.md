# `make_charger` refuses charge values without a charge state — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. In this repo the flow in `docs/way-of-working.md` §1–2 applies (implementer and task-reviewer agents, waves, worktrees).

**Goal:** The test fixture `make_charger` raises when it is given `charge_kwh`, `charge_kw` or `charge_cost` without a `charge_state`, and the two test cases that pass exactly that are removed.

**Architecture:** One task, one commit. A guard at the top of `make_charger` in `tests/conftest.py`, its tests in a new `tests/test_conftest.py`, and the removal of one parametrize case in each of `tests/test_costs.py` and `tests/test_sensor.py`. They land together because `make_charger` runs at import time inside `parametrize` lists: with the guard in and the two cases still there, both files fail to collect (spec §3).

**Tech Stack:** Python 3.14, pytest with `pytest-homeassistant-custom-component`, `pynortecgo` 0.8.0 model objects, uv, ruff, mypy (strict, covers `tests/`).

**Spec:** `docs/superpowers/specs/2026-10-01-make-charger-strict-design.md` (issue #93).

## Global Constraints

- Tests only: nothing under `custom_components/` changes, and no file outside `tests/` changes. No `CHANGELOG.md` entry, no `quality_scale.yaml`, user-doc or `decisions.md` change (spec, *Not in this work*).
- The files this plan touches, and no others: `tests/conftest.py`, `tests/test_conftest.py` (new), `tests/test_costs.py`, `tests/test_sensor.py`.
- The guard covers `charge_kwh`, `charge_kw` and `charge_cost` only. `charge_id`, `last_charge` and `currency` are not guarded, and `make_charger`'s signature doesn't change.
- The guard tests `is not None`, never truthiness: `0.0` counts as given.
- The exception is `ValueError`, and its message is exactly: the given arguments' names in the order of the signature (`charge_kwh`, `charge_kw`, `charge_cost`), joined with `, `, followed by ` given without a charge_state: there is no open charge`.
- Tests compare the whole message with `==`, never `pytest.raises(match=...)`: `charge_kw` is a prefix of `charge_kwh`.
- TDD: write the failing tests, see them fail, then write the guard. Fixtures come from `pynortecgo` model objects and the `tests/conftest.py` helpers, never raw API JSON, and test values are plainly fake (hard rules 3, 7).
- Gates before the commit, each run unpiped so its own exit code shows: `uv run pytest -q`, then `uv run ruff check && uv run ruff format --check && uv run mypy`, then the coverage gate `uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95` (the gates in `CLAUDE.md` → Commands without `actionlint` and `zizmor`: the task touches no workflow).
- One commit. The failing run of the new tests is observed, not committed.
- Subagents write the commit message with the Write tool to a file outside the repo, and commit with `git commit -F <file>` (no heredocs). End the message with the co-author trailer given in the dispatch.
- Match the surrounding code: one-line docstrings ending in a period, names, comment density. `ruff format` decides the layout; if it rewrites a line of this plan's code, keep ruff's version.

## Review Focus

Every item is pinned by a test in Task 1.

1. `0.0` is a given value, not a missing one: `make_charger(charge_cost=0.0)` is refused (`test_zero_counts_as_a_given_charge_value`).
2. The message names the right argument: `charge_kw` alone must not be reported as `charge_kwh`, and the other way round (`test_charge_value_without_a_charge_state_is_refused`, whole-message comparison).
3. The names come in the signature's order, whatever the order of the call (`test_every_refused_charge_value_is_named_in_signature_order`).
4. The allowed calls build the same charger as before: no values and no state gives `active_charge is None`; values with a state are kept (`test_no_charge_values_and_no_charge_state_gives_no_open_charge`, `test_charge_values_with_a_charge_state_are_kept`).
5. Each removed case goes with its own id: the id lists before and after differ by exactly the two removed ids (Step 6). Removing the wrong `ids=` entry would keep the lengths equal and mislabel cases without an error, so the task reviewer checks the diff of the two id lists.

## Waves

| Wave | Tasks | Notes |
|---|---|---|
| 1 | Task 1 | The only task; it runs in the issue worktree, no task worktree |

No task has guarded files.

---

### Task 1: The guard, its tests and the two removals

**Model:** sonnet — a test fixture and test cases; no auth, tokens or reauth, nothing near charge start or stop, and no mapping of `pynortecgo` models to entities.
**Wave:** 1

**Files:**
- Create: `tests/test_conftest.py`
- Modify: `tests/conftest.py` (`make_charger`, its docstring and the lines before `return Charger(`)
- Modify: `tests/test_costs.py` (the parametrize list and `ids=` of `test_charge_cost`)
- Modify: `tests/test_sensor.py` (the parametrize list and `ids=` of `test_charge_energy_and_power_values`)

**Interfaces:**
- Consumes: `make_charger` from `tests/conftest.py`, with its present signature (keyword-only `charge_state: ChargeState | None = None`, `charge_kwh: float | None = None`, `charge_kw: float | None = None`, `charge_cost: float | None = None`); `ChargeState` and `Charger.active_charge` (`ActiveCharge | None`, with `kwh`, `kw`, `cost`) from `pynortecgo`.
- Produces: `make_charger` raises `ValueError` as the Global Constraints say. Nothing else changes for its callers.

- [ ] **Step 1: Save the list of collected test ids, before any change**

Run: `uv run pytest --collect-only -q tests/test_costs.py tests/test_sensor.py > /tmp/make-charger-strict-task-1-ids-before.txt`

Expected: the file's last line says `61 tests collected`, and it lists `tests/test_costs.py::test_charge_cost[no_charge_ignores_cost]` and `tests/test_sensor.py::test_charge_energy_and_power_values[no_charge_ignores_fields]`.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_conftest.py` with exactly this content. The call is built in the test body from a `dict[str, Any]`: built in the `parametrize` list it would raise at import, and a narrower dict type fails strict mypy.

```python
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
```

- [ ] **Step 3: Run the new tests and see the refusal tests fail**

Run: `uv run pytest -q tests/test_conftest.py`

Expected: `5 failed, 2 passed`. The five failures are the three cases of `test_charge_value_without_a_charge_state_is_refused`, `test_zero_counts_as_a_given_charge_value` and `test_every_refused_charge_value_is_named_in_signature_order`, each with `Failed: DID NOT RAISE <class 'ValueError'>`. The two allowed-call tests pass already, and stay passing.

- [ ] **Step 4: Add the guard to `make_charger`**

In `tests/conftest.py`, replace `make_charger`'s one-line docstring

```text
    """Return a charger; idle and unplugged unless told otherwise."""
```

with this docstring and guard, directly above the unchanged `return Charger(`:

```text
    """Return a charger; idle and unplugged unless told otherwise.

    A charge value (`charge_kwh`, `charge_kw`, `charge_cost`) needs a `charge_state`:
    without one there is no open charge to hold it, so the call is refused.
    """
    if charge_state is None:
        given = [
            name
            for name, value in (
                ("charge_kwh", charge_kwh),
                ("charge_kw", charge_kw),
                ("charge_cost", charge_cost),
            )
            if value is not None
        ]
        if given:
            raise ValueError(
                f"{', '.join(given)} given without a charge_state: "
                "there is no open charge"
            )
```

The signature and the `return Charger(...)` expression stay as they are.

- [ ] **Step 5: Remove the two cases, each with its id**

At this point `tests/test_costs.py` and `tests/test_sensor.py` fail to collect: each holds a call the guard refuses. Remove them.

In `tests/test_costs.py`, in the `parametrize` of `test_charge_cost`, delete this tuple (the second in the list):

```text
        (make_charger(charge_cost=5.0, last_charge=make_completed_charge()), None),
```

and this entry in its `ids=` list (the second):

```text
        "no_charge_ignores_cost",
```

In `tests/test_sensor.py`, in the `parametrize` of `test_charge_energy_and_power_values`, delete this tuple (the second in the list):

```text
        (
            make_charger(is_connected=True, charge_kwh=5.0, charge_kw=6.0),
            STATE_UNKNOWN,
            "0.0",
        ),
```

and this entry in its `ids=` list (the second):

```text
        "no_charge_ignores_fields",
```

No import becomes unused: `make_completed_charge`, `ChargeState` and `STATE_UNKNOWN` are still used in the files that import them.

- [ ] **Step 6: Check the collected ids**

Run:

```bash
uv run pytest --collect-only -q tests/test_costs.py tests/test_sensor.py > /tmp/make-charger-strict-task-1-ids-after.txt
diff /tmp/make-charger-strict-task-1-ids-before.txt /tmp/make-charger-strict-task-1-ids-after.txt
```

Expected: `diff` exits with 1, since the files differ; that is the wanted result here. Beside its hunk markers (`2d1`, `33d31`, `63c61`, `---`), it shows exactly these lines and nothing else:
- `< tests/test_costs.py::test_charge_cost[no_charge_ignores_cost]`
- `< tests/test_sensor.py::test_charge_energy_and_power_values[no_charge_ignores_fields]`
- the summary line, from `61 tests collected` to `59 tests collected` (the timing in it may differ).

`tests/test_costs.py::test_charge_cost[no_charge]` and `tests/test_sensor.py::test_charge_energy_and_power_values[no_charge]` are in both files. Put the diff's output in the report.

- [ ] **Step 7: Run the new tests and see them pass**

Run: `uv run pytest -q tests/test_conftest.py`

Expected: `7 passed`.

- [ ] **Step 8: Run the gates**

Run each unpiped:

```bash
uv run pytest -q
uv run ruff check && uv run ruff format --check && uv run mypy
uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95
```

Expected: `714 passed` (709 before, minus the 2 removed cases, plus the 7 new tests), no ruff or mypy finding, and the coverage gate reached (99.92% before the change; it must not drop).

The full test run is the real check that no other call passes a charge value with a `charge_state` that is `None` at run time. If any other test now raises the guard's `ValueError`, or a file fails to collect, stop and report it as BLOCKED with the test's name: don't change that test and don't loosen the guard.

- [ ] **Step 9: Commit**

Write the message to `/tmp/make-charger-strict-task-1-msg.txt` with the Write tool:

```text
test: make_charger refuses charge values without a charge state (#93)

charge_kwh, charge_kw and charge_cost live on the open charge, so
without a charge_state the fixture had nowhere to put them and dropped
them. It now raises ValueError and names the arguments.

The two cases that passed such values are removed: they no longer
tested what their names said.

<the co-author trailer from the dispatch>
```

Then:

```bash
git add tests/conftest.py tests/test_conftest.py tests/test_costs.py tests/test_sensor.py
git commit -F /tmp/make-charger-strict-task-1-msg.txt
git status --short
```

Expected: one commit with those four files, and no change left in tracked files (an untracked `.superpowers/` is the controller's workspace, not the task's). Don't push.
