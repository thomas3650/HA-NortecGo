# `make_charger` refuses charge values without a charge state — design

Date: 2026-10-01 · Branch: `chore/make-charger-strict` · Issue: #93

## Goal

- **What:** the test fixture `make_charger` (`tests/conftest.py`) raises when it is given `charge_kwh`,
  `charge_kw` or `charge_cost` without a `charge_state`, and the two test cases that pass exactly that are
  removed.
- **Why:** since `pynortecgo` 0.8.0 (#81) the open charge's values live on `Charger.active_charge`. Without a
  `charge_state` the fixture builds no `ActiveCharge`, so those three values have nowhere to go and are
  dropped without a word. A test can then build a different charger than it reads: the two cases below
  stopped testing what their names say that way (§2).
- **Behaviour is unchanged.** Only files under `tests/` change. Nothing under `custom_components/` changes.
- **Not in this work:**
  - `charge_id`. It is also unused without a `charge_state`, but it has a default (`FAKE_CHARGE_ID`), so the
    fixture can't tell "given" from "left out" without changing that default, and the issue names only the
    three values. No call in `tests/` passes `charge_id` without a `charge_state` today.
  - `last_charge` and `currency`. They don't depend on an open charge.
  - Any other change to `make_charger`'s arguments, or to how tests call it.
  - `CHANGELOG.md`, `quality_scale.yaml`, `docs/user/nortec_go.md` and `decisions.md`: nothing is
    user-visible, no quality-scale rule moves, and no lasting decision is made.
- **Done when:** the guard is in `make_charger` with its own tests, the two cases are gone, and the gates
  pass (`CLAUDE.md` → Commands).

## Decisions

Answered by the PO (2026-10-01); the PO records its approval of this spec on issue #93.

| Topic | Decision |
|---|---|
| Release level | Not releasing. The title is `test: make_charger refuses charge values without a charge state (#93)`: no changelog entry, no bump step |
| Which arguments the guard covers | `charge_kwh`, `charge_kw` and `charge_cost` only (see *Not in this work*) |
| Where the guard's tests live | A new `tests/test_conftest.py`. The coverage gate stays on `custom_components.nortec_go` only |
| Decision log | No entry |

## 1. The guard

In `make_charger`, before the `Charger` is built:

- When `charge_state is None`, collect the names of the arguments among `charge_kwh`, `charge_kw` and
  `charge_cost` whose value `is not None`. The test is `is not None`, not truthiness: `0.0` is a real value
  (the `zero_cost` case in `tests/test_costs.py` relies on it), so it counts as given.
- If any were collected, raise `ValueError`. The message is the collected names in the order of the
  signature, joined with `, `, followed by ` given without a charge_state: there is no open charge`. For
  example: `charge_kwh, charge_kw given without a charge_state: there is no open charge`.
- Otherwise the fixture builds the same `Charger` as today. With a `charge_state`, all three values stay
  optional (`None` means the open charge has no such reading).

The docstring gains one sentence that says so.

## 2. The two removed cases

Each is removed whole: the parameter tuple and its entry in `ids=`.

| File | Test | Case id | The tuple |
|---|---|---|---|
| `tests/test_costs.py` | `test_charge_cost` | `no_charge_ignores_cost` | `make_charger(charge_cost=5.0, last_charge=make_completed_charge())`, expected `None` |
| `tests/test_sensor.py` | `test_charge_energy_and_power_values` | `no_charge_ignores_fields` | `make_charger(is_connected=True, charge_kwh=5.0, charge_kw=6.0)`, expected `STATE_UNKNOWN` and `"0.0"` |

- They are the only calls of `make_charger` in `tests/` that pass one of the three values without a
  `charge_state` keyword (a scan of every call, 2026-10-01).
- `no_charge_ignores_fields` builds the same charger as the `no_charge` case next to it, which stays.
- `no_charge_ignores_cost` differs from its `no_charge` neighbour only by its `last_charge`. Nothing is lost
  with it:
  - `charge_cost` in `custom_components/nortec_go/costs.py` returns `None` when there is no open charge,
    before it reads `last_charge`, so the code path is the one `no_charge` takes;
  - the combination (no open charge, and a completed one) stays tested through the sensor: the `no_charge`
    case of `test_cost_values` in `tests/test_sensor.py` builds
    `make_charger(is_connected=True, last_charge=make_completed_charge())` and expects the cost sensor to be
    unknown.
- No import is left unused in either file (`make_completed_charge` and `ChargeState` are still used).

## 3. Order of the work

`make_charger` is called inside `@pytest.mark.parametrize` lists, so it runs when a test module is imported.
Once the guard is in, each of the two cases raises at import, and its whole file fails to collect, not just
that case. So the guard, its tests (`tests/test_conftest.py`) and the two removals land in **one commit**,
and the plan has one task. The failing run of the new tests is observed, not committed.

## 4. Tests

A new `tests/test_conftest.py`, written before the guard (TDD). The refusal tests compare the whole message
(`str(excinfo.value) == ...`), not a `match=` pattern: `charge_kw` is a prefix of `charge_kwh`, so a regex
search for the name would pass on the wrong argument.

- **Each value alone is refused:** parametrized over `charge_kwh`, `charge_kw` and `charge_cost`, each given
  a non-zero value and no `charge_state`; the message names exactly that argument.
- **Zero counts as given:** one of the three given `0.0` and no `charge_state` raises too.
- **Every offending argument is named, in the signature's order:** all three given, in another order than
  the signature's; the message is
  `charge_kwh, charge_kw, charge_cost given without a charge_state: there is no open charge`.
- **The allowed calls still work:** `make_charger()` returns a charger with `active_charge is None`; and
  `make_charger(charge_state=ChargeState.CHARGING, charge_kwh=1.5, charge_kw=2.3, charge_cost=4.0)` returns
  one whose `active_charge` holds those three values.

The parametrized test gets the argument's name and builds the call in the test body, never in the
`parametrize` list (it would raise at import, §3). The keyword arguments go in a `dict[str, Any]`:
`make_charger(**{name: 1.0})` with a narrower dict type fails strict mypy, which covers `tests/`.

The plan verifies the change with:

- the refusal tests failing before the guard and passing after it; the allowed-call tests pass both before
  and after;
- `uv run pytest --collect-only -q tests/test_costs.py tests/test_sensor.py` before and after: the two files
  go from 61 collected tests to 59, and a diff of the two id lists shows exactly the two removed ids
  (removing the wrong `ids=` entry would keep the lengths equal and mislabel cases without an error);
- the full `uv run pytest -q`. This is the real check that no other call passes a charge value with a
  `charge_state` that is `None` at run time (a helper that forwards a variable, say): the scan in §2 sees
  only whether the keyword is written;
- the other gates, including the coverage gate.

## 5. Docs

No doc describes `make_charger`'s arguments, so none changes. Learnings, if any, go through
`way-of-working.md` §1 step 8.
