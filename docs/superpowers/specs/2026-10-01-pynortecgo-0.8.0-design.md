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
- **Done when:** both pins and `uv.lock` say 0.8.0, the gates pass, the checks in §5 hold, the bump
  checklist in `docs/releasing.md` is worked through with its results in the PR description (§6), and D46
  is in `decisions.md` and `docs/releasing.md` (§7).

## Decisions

Answered by the PO, and for D46 by the owner through the PO (2026-10-01); the PO records its approval of
this spec on issue #81.

| Topic | Decision |
|---|---|
| Release level | Not releasing. The title is `chore(deps): move to pynortecgo 0.8.0 (#81)`: no changelog entry, no bump step |
| The diagnostics download | Its `charger` block changes shape (§4). That isn't a user-visible change: the user docs don't describe the block's keys, and it is a support file. The owner made this a lasting rule (D46, §7) |
| How the reads move | One helper for the charge's state, so every condition in the charge control keeps its shape (§2) |
| The test fixture | `make_charger` keeps its keyword arguments (§5) |
| Decision log | D46 (§7) |
| Who reviews and merges | The owner: the spec and the plan go to the owner through the PO, and the PR edits `charge_control.py`, so it is the owner's to merge (D45) |

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
- Three of the client's own warning texts name the new fields instead of the old ones. They are rare
  warnings from the `pynortecgo` logger that can show in the Home Assistant log. The user docs quote none of
  them and no test here matches on them, and the PO ruled that their wording isn't a user-visible change.

## 2. The charge's state: one helper

`charge_control.py` gets one public function:

```python
def charge_state(charger: Charger) -> ChargeState | None:
    """The open charge's state, or None when no charge is open."""
    active = charger.active_charge
    return None if active is None else active.state
```

Every read of `charger.charge_state` becomes a read of the helper's result, and nothing else in its
expression changes. The helper returns exactly what the old field held (§1), so each condition means what
it meant.

- **Six reads are plain swaps:** `charger.charge_state` becomes `charge_state(charger)`.
- **`charge_status` binds the result to one local** and uses it at its three sites:

  ```python
  state = charge_state(charger)
  if charger.state is ChargerState.UNKNOWN or state is ChargeState.UNKNOWN:
      return None
  if state in _STATUS_FROM_CHARGE:
      return state.value
  ```

  Its last read takes `.value` of the state after an `in` check. mypy narrows an attribute or a local after
  that check, but not a function call, so a bare swap there fails `mypy --strict`. The local goes right
  above the `UNKNOWN` check, after the three early returns, which don't read it.

| File | Reads | Where |
|---|---|---|
| `charge_control.py` | 7 | `charge_is_open`, `is_charge_on`, `charge_status` (3, through the local), `async_stop`, `on_charger_read` |
| `coordinator.py` | 1 | `interval_for` |
| `binary_sensor.py` | 1 | the *Charging* description's `value_fn` |

- `coordinator.py` and `binary_sensor.py` import the helper from `charge_control.py`; both already import
  from it or from its users, and it adds no import cycle (`charge_control.py` imports neither).
- Why a helper and not `charger.active_charge` at each site: a condition like
  `charger.charge_state in _CHARGE_ON` would become
  `charger.active_charge is not None and charger.active_charge.state in _CHARGE_ON`. That rewrites the
  logic next to start and stop, and each rewrite would need its own argument that it means the same. With
  the helper, the review of the charge control is a check of six swapped names and one local in
  `charge_status`.
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
- `docs/releasing.md`'s bump checklist names the models whose fields are pinned. It gets `ActiveCharge`,
  and the rule in §7.

## 5. Tests, and how the plan proves the behaviour is unchanged

This is a move with no behaviour change, so it adds no behaviour tests. The existing suite is the
description of the behaviour, and the proof is that it passes without being edited:

1. **`make_charger` keeps its keyword arguments.** In `tests/conftest.py` only its body changes: with a
   `charge_state` it builds an `ActiveCharge` (`id` the fake charge ID, `state_raw` the state's value,
   `can_stop` true, and the given `kwh`, `kw` and `cost`), and without one `active_charge` is `None`. The
   fixture's fields are in the client's order: `id`, `name`, `max_kw`, `state`, `state_raw`, `is_connected`,
   `currency`, `active_charge`, `last_charge`. A `charge_kwh`, `charge_kw` or `charge_cost` given without a
   `charge_state` is dropped: no charge is open, which is what such a test means today (the cost tests use
   it for "a stale cost with no open charge"). Two cases build that state (`no_charge_ignores_cost` in
   `test_costs.py` and `no_charge_ignores_fields` in `test_sensor.py`). The new model can't hold it, so they
   now build the same charger as their plain no-charge neighbours and still pass. Removing them, and making
   `make_charger` refuse values it would drop, would edit those test files, so it is a follow-up issue and
   not part of this work.
2. **Acceptance check: the diff under `tests/` touches only `conftest.py` and `test_diagnostics.py`.** Every
   other test file, including all of `test_charge_control.py`, `test_switch.py`, `test_coordinator.py`,
   `test_sensor.py`, `test_binary_sensor.py` and `test_costs.py`, is byte-identical to `origin/main` and
   passes. Those tests state what the charge control, the switch, the polling and the entities do for each
   charger; the same assertions on the same chargers (but for the two cases in item 1) pass on the new
   client. The check, which prints exactly those two paths:

   ```bash
   git diff --name-only origin/main...HEAD -- tests
   ```
3. **mypy finds every read.** The project runs `mypy --strict` over the integration and the tests. A read of
   a removed field is a type error, so a clean mypy run on 0.8.0 means no read was missed. mypy can't see
   a read through `Any` (there are none today), so a search backs it up and prints nothing after the move:

   ```bash
   grep -rnE '\.(charge_id|charge_state|charge_state_raw|can_stop|charge_kwh|charge_kw|charge_cost)\b' custom_components tests
   ```
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
  docs (`docs/releasing.md` and `docs/decisions.md`, §4 and §7) are a second task.
- The checklist in `docs/releasing.md` (*Bumping `pynortecgo`*), with what was found when this spec was
  written. The task re-checks each against the installed 0.8.0, and the PR description carries the results:

| Item | Found |
|---|---|
| Exception messages hold no secrets | The client's exceptions are the same as in 0.7.0, and so is the layer that wraps lower-level errors |
| The diagnostics field pins | `Charger` changed and `ActiveCharge` is new; judged in §4 |
| New exception classes | None. The charger, car, price, start and stop calls raise what they raised |
| Breaking changes to the models | The one in §1. `ActiveCharge` is the only new public name |

## 7. Decision log

`docs/decisions.md` gets this entry. #86 carries D44 and isn't merged yet; whichever of the two PRs merges
second keeps D44 before D46 in the file.

### D46: The shape of the diagnostics download isn't user-visible
- **Date:** 2026-10-01 · **Status:** active
- **Decision:** A change that only moves, renames, adds or removes keys in the diagnostics download isn't a
  user-visible change: it needs no changelog entry and doesn't make a PR releasing. D38 still decides what
  the download may show.
- **Why:** The download is a support file. The user docs don't describe its keys, and nothing is meant to
  be built on them. Without the rule, every client release that changes a model would force a release of
  the integration.
- **Source:** this spec, *Decisions* and §4.

`docs/releasing.md`, *Bumping `pynortecgo`*, gets one sentence after "Title such a PR by what it changes for
users": a change only in the shape of the diagnostics download isn't something users see (D46).

## 8. Other branches

`feat/car-device-lifecycle` (#86) may land first. It changes `coordinator.py`, `binary_sensor.py`,
`diagnostics.py` and `tests/test_diagnostics.py`, the last in the same whole-output expectation whose
`charger` block §4 changes. This branch then merges `origin/main` in (no rebase), and that test file gets a
look in the merge. If #86 adds a `Charger` built outside `make_charger`, or a read of an old field, mypy on
the merged branch fails and it is moved here the same way. The check in §5 item 2 compares with the merge
base, so #86's own test changes don't show in it.
