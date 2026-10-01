# Move to pynortecgo 0.8.0 — design

Date: 2026-10-01 · Branch: `chore/pynortecgo-0.8.0` · Issue: #81

## Goal

- **What:** the integration runs on `pynortecgo` 0.8.0. That version removes the seven flat open-charge
  fields on `Charger` and puts the open charge in `Charger.active_charge` (`ActiveCharge | None`). Every read
  of the old fields moves to the new one.
- **Why:** 0.8.0 has no aliases for the old fields, so the integration can't take any later client release
  until it has moved.
- **Behaviour is unchanged.** No entity, state, name, unit, attribute, error text or log line of the
  integration changes, and nothing changes in when it starts or stops a charge. §5 says how the plan proves
  that.
- **Not in this work:**
  - Any new entity or value. `ActiveCharge.can_stop` and `ActiveCharge.state_raw` stay unused, as
    `Charger.can_stop` and `Charger.charge_state_raw` were.
  - Any change to the start path, the stop path, the pending start, the pending stop or the polling
    intervals.
  - `CHANGELOG.md` and `version` in `manifest.json` (see *Decisions*, the release level).
- **Done when:** both pins and `uv.lock` say 0.8.0, the gates pass, the checks in §5 hold, and the bump
  checklist in `docs/releasing.md` is worked through with its results in the PR description (§6).

## Decisions

Answered by the PO (issue #81, 2026-10-01).

| Topic | Decision |
|---|---|
| Release level | Not releasing. The title is `chore(deps): move to pynortecgo 0.8.0 (#81)`: no changelog entry, no bump step |
| The diagnostics download | Its `charger` block changes shape (§4). That isn't a user-visible change: the user docs don't describe the block's keys, and it is a support file |
| How the reads move | One helper for the charge's state, so every condition in the charge control keeps its shape (§2) |
| The test fixture | `make_charger` keeps its keyword arguments (§5) |
| Decision log | No entry: nothing here sets a lasting rule |

The release level follows `docs/releasing.md` (*Bumping `pynortecgo`*): a client bump is titled by what it
changes for users, and this one changes nothing they see. Users get 0.8.0 with the next releasing PR.

## 1. What changes in the client

From `pynortecgo` 0.8.0's public models and their docstrings:

| 0.7.0, on `Charger` | 0.8.0, on `Charger.active_charge` |
|---|---|
| `charge_id` | `id` |
| `charge_state` | `state` |
| `charge_state_raw` | `state_raw` |
| `can_stop` | `can_stop` |
| `charge_kwh` | `kwh` |
| `charge_kw` | `kw` |
| `charge_cost` | `cost` |

- `active_charge` is `None` when no charge is open. On an `ActiveCharge`, `id`, `state`, `state_raw` and
  `can_stop` are always set; `kwh`, `kw` and `cost` can be `None`, as before.
- In 0.7.0 `charge_id`, `charge_state`, `charge_state_raw` and `can_stop` were all `None` or all set: the
  client built them from one open charge, and required all four on it. So the two tests the integration uses
  today for "a charge is open" (`charge_id is None` and `charge_state is not None`) always agreed, and both
  equal `active_charge is None` now. A charge with an incomplete state failed the charger read in 0.7.0 and
  fails it the same way in 0.8.0.
- `currency`, `is_connected`, `last_charge`, `CompletedCharge`, `Vehicle`, the `Charge` a start or a stop
  returns, the client's methods and its exceptions don't change.
- Three of the client's own log texts name the new fields. No test here matches on them, so nothing follows
  from that.

## 2. The charge's state: one helper

`charge_control.py` gets one public function:

```python
def charge_state(charger: Charger) -> ChargeState | None:
    """The open charge's state, or None when no charge is open."""
    active = charger.active_charge
    return None if active is None else active.state
```

Every read of `charger.charge_state` becomes `charge_state(charger)`, and nothing else in its expression
changes. The helper returns exactly what the old field held (§1), so each condition means what it meant.

| File | Reads | Where |
|---|---|---|
| `charge_control.py` | 7 | `charge_is_open`, `is_charge_on`, `charge_status` (3), `async_stop`, `on_charger_read` |
| `coordinator.py` | 1 | `interval_for` |
| `binary_sensor.py` | 1 | the *Charging* description's `value_fn` |

- `coordinator.py` and `binary_sensor.py` import the helper from `charge_control.py`; both already import
  from it or from its users, and it adds no import cycle (`charge_control.py` imports neither).
- Why a helper and not `charger.active_charge` at each site: a condition like
  `charger.charge_state in _CHARGE_ON` would become
  `charger.active_charge is not None and charger.active_charge.state in _CHARGE_ON`. That rewrites the
  logic next to start and stop, and each rewrite would need its own argument that it means the same. With
  the helper, the review of the charge control is a check that seven names were swapped.
- The integration doesn't read `can_stop` today (only the client does, inside its stop), and still doesn't.
  `switch.py` reads no `Charger` field and doesn't change.

## 3. The sensors and the costs

**`sensor.py`, the charge sensors (energy and power).**
- `NortecGoChargeSensorDescription.value_fn` takes the open charge: `Callable[[ActiveCharge], float | None]`.
  The two descriptions read `active.kwh` and `active.kw`.
- `native_value` returns `no_charge_value` when `charger.active_charge is None` (today: when
  `charger.charge_id is None`), and otherwise `value_fn` of the open charge. The no-charge values stay:
  unknown for the energy, 0 for the power.

**`costs.py`.** The same three functions with the same results (D42):
- `charge_cost`: `None` when `active_charge is None`; the last charge's billed cost when
  `last_charge.id == active_charge.id`; otherwise `active_charge.cost`.
- `last_charge_cost` and `last_charge_completed_at` read only `last_charge` and don't change.
- The module docstring names `ActiveCharge.cost` instead of `Charger.charge_cost`. It stays the one place
  that reads the costs.

## 4. Diagnostics

`diagnostics.py` doesn't change: it shows `asdict(charger)`, and `asdict` follows the new model.

- The `charger` block loses the seven flat keys and gains `active_charge`: an object with `id`, `state`,
  `state_raw`, `can_stop`, `kwh`, `kw` and `cost`, or `null` when no charge is open.
- **Redaction (D38).** The seven values are the ones the download showed before, under new keys. None is a
  sign-in secret, and D38 keeps IDs, so `TO_REDACT` doesn't change.
- **The pins.** In `tests/test_diagnostics.py`, `CHARGER_FIELDS` becomes the nine fields of the new
  `Charger`, a new `ACTIVE_CHARGE_FIELDS` pins `ActiveCharge`'s seven, and
  `test_client_model_fields_are_pinned` checks both. The whole-output test, the one test that looks at the
  `charger` block, expects the nested block.
- `docs/releasing.md`'s bump checklist names the models whose fields are pinned. It gets `ActiveCharge`.

## 5. Tests, and how the plan proves the behaviour is unchanged

This is a move with no behaviour change, so it adds no behaviour tests. The existing suite is the
description of the behaviour, and the proof is that it passes without being edited:

1. **`make_charger` keeps its keyword arguments.** In `tests/conftest.py` only its body changes: with a
   `charge_state` it builds an `ActiveCharge` (`id` the fake charge ID, `state_raw` the state's value,
   `can_stop` true, and the given `kwh`, `kw` and `cost`), and without one `active_charge` is `None`. The
   fixture's fields are in the client's order: `id`, `name`, `max_kw`, `state`, `state_raw`, `is_connected`,
   `currency`, `active_charge`, `last_charge`. A `charge_kwh`, `charge_kw` or `charge_cost` given without a
   `charge_state` is dropped: no charge is open, which is what such a test means today (the cost tests use
   it for "a stale cost with no open charge").
2. **Acceptance check: the diff under `tests/` touches only `conftest.py` and `test_diagnostics.py`.** Every
   other test file, including all of `test_charge_control.py`, `test_switch.py`, `test_coordinator.py`,
   `test_sensor.py`, `test_binary_sensor.py` and `test_costs.py`, is byte-identical to `origin/main` and
   passes. Those tests state what the charge control, the switch, the polling and the entities do for each
   charger; the same assertions on the same chargers pass on the new client.
3. **mypy finds every read.** The project runs `mypy --strict` over the integration and the tests. A read of
   a removed field is a type error, so a clean mypy run on 0.8.0 means no read was missed.
4. **The coverage gate (95%) holds**, and the helper's two branches are both run by the existing tests (a
   charger with and without an open charge).
5. **In `test_diagnostics.py`** only the pins and the expected `charger` block change (§4).

If one of the untouched tests fails on the new client, the move changed behaviour: the fix is in the
integration code, never in that test.

## 6. The bump

- `pyproject.toml` and `requirements` in `manifest.json` pin `pynortecgo==0.8.0`; the lock is updated with
  `uv lock --upgrade-package pynortecgo`, which leaves the other pins alone.
- The bump breaks mypy and the tests until every read has moved, and every commit passes the gates. So the
  pins, the lock, the reads, the fixture and the diagnostics pins are **one task and one commit**. The
  `docs/releasing.md` line is a second task.
- The checklist in `docs/releasing.md` (*Bumping `pynortecgo`*), with what was found when this spec was
  written. The task re-checks each against the installed 0.8.0, and the PR description carries the results:

| Item | Found |
|---|---|
| Exception messages hold no secrets | The client's exceptions are the same as in 0.7.0, and so is the layer that wraps lower-level errors |
| The diagnostics field pins | `Charger` changed and `ActiveCharge` is new; judged in §4 |
| New exception classes | None. The charger, car, price, start and stop calls raise what they raised |
| Breaking changes to the models | The one in §1. `ActiveCharge` is the only new public name |

## 7. Other branches

`feat/car-device-lifecycle` (#86) changes `coordinator.py` and may land first. This branch then merges
`origin/main` in (no rebase). If #86 adds a `Charger` built outside `make_charger`, or a read of an old
field, mypy on the merged branch fails and it is moved here the same way.
