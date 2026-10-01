# Move to pynortecgo 0.8.0 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. In this repo the flow in `docs/way-of-working.md` §1–2 applies (implementer and task-reviewer agents, waves, worktrees).

**Goal:** the integration runs on `pynortecgo` 0.8.0, reading the open charge from `Charger.active_charge`, with no change in behaviour (#81).

**Architecture:**
- Task 1 is the whole code move in one commit: both pins and the lock, one helper `charge_state(charger)` in `charge_control.py`, every read of the removed fields, the test fixture `make_charger`, and the diagnostics field pins. It can't be split: the bump breaks mypy and the tests until every read has moved, and every commit passes the gates.
- Task 2 is the docs: D46 in `docs/decisions.md` and two passages in `docs/releasing.md`. It shares no file with Task 1, so both run in wave 1.

**Tech Stack:** Python 3.14, Home Assistant, `pynortecgo` 0.8.0, pytest with `pytest-homeassistant-custom-component`, mypy `--strict`, ruff, uv.

**Spec:** `docs/superpowers/specs/2026-10-01-pynortecgo-0.8.0-design.md` (issue #81). Read it with the task: this plan argues from it.

## Global Constraints

- **Behaviour is unchanged.** No entity, state, name, unit, attribute, error text or log line of the integration changes. Nothing changes in when a charge is started or stopped.
- **Test files.** Under `tests/`, only `tests/conftest.py` and `tests/test_diagnostics.py` change. Every other test file stays byte-identical. If one of them fails on the new client, the fix is in the integration code, never in that test: stop and report it.
- **`make_charger` keeps its keyword arguments**, names and defaults. Only its body changes.
- **Never start or stop a real charge** (hard rule 2). Tests mock `pynortecgo`; nothing here runs Home Assistant.
- **Nothing private (hard rule 3):** only `pynortecgo`'s public names appear in code, tests, docs and commit messages. No endpoints, headers or response shapes, also not when reporting what the client's source holds.
- **Fixtures are built from `pynortecgo` model objects** (hard rule 7), never from raw JSON.
- **Not in this work:** `CHANGELOG.md`, `version` in `manifest.json`, `switch.py`, `diagnostics.py`, `docs/user/nortec_go.md`, and any new entity or value. `ActiveCharge.can_stop` and `ActiveCharge.state_raw` stay unread.
- **Gates before every commit** (`CLAUDE.md` → Commands): `uv run pytest -q`, then `uv run ruff check && uv run ruff format --check && uv run mypy && uv run actionlint && uv run zizmor --offline .github/workflows`, then the coverage gate `uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95`.
- **Every command runs in the task's worktree:** `cd <worktree> && …`, or `git -C <worktree> …`. Edit files by absolute path under the worktree. Don't run `pre-commit install` there.
- **Commit messages:** write them with the Write tool to `/tmp/pynortecgo-080-task-<n>-msg.txt` and commit with `git commit -F <file>`. No heredocs. End each message with the co-author trailer given in the dispatch.
- **PR:** title `chore(deps): move to pynortecgo 0.8.0 (#81)`. It doesn't release: no changelog entry and no bump step. It edits `charge_control.py`, so it is the owner's to merge (D45).

## Review Focus

What the spec implies but no single test states, most likely first. Each line names what pins it.

1. **A read of a removed field that mypy can't see** (through `Any`). Expected: none is left. Pinned by
   Task 1, Step 9's grep, which prints nothing.
2. **A test edited to make it pass.** Expected: the existing tests pass untouched; that is the proof that
   behaviour is unchanged. Pinned by Task 1, Step 9's `git diff --name-only`, which prints exactly two paths.
3. **An open charge with no energy, power or cost reading** (`kwh`, `kw` or `cost` is `None` on the
   `ActiveCharge`). Expected: the sensor is unknown, as today, not 0 and not the no-charge value. Pinned by
   two existing cases, untouched: `test_charge_energy_and_power_values[open_charge_no_readings]` in
   `tests/test_sensor.py` and `test_charge_cost[open_no_cost_reading]` in `tests/test_costs.py`.
4. **No open charge in the charge control** (`active_charge` is `None`). Expected: `charge_is_open` goes by
   the charger's state alone, the switch is off unless a start is pending, and the status falls through to
   `not_released`, `unplugged` or `idle`. Pinned by the existing cases in `tests/test_charge_control.py`,
   untouched.
5. **Two things in the charge control that no existing test pins**, found by mutating the moved reads: a
   stop with a read charger and no open charge still sends the stop (every stop test reads a `CHARGING`
   charger first), and in `charge_status` the `UNKNOWN` check stays below the pending-start return. No test
   can be added in this work (the test files stay untouched), so the guard is the review: `task-reviewer`
   confirms, from the review package's diff of `charge_control.py` (Task 1, Step 9 names what it must
   hold), that the `async_stop` line is a literal name swap and that the local in `charge_status` sits
   after the three early returns. Both cases go in the follow-up issue.
6. **The lock moves more than the client.** Expected: `uv.lock` changes only the `pynortecgo` package entry
   (0.8.0 needs the same dependencies as 0.7.0). Pinned by Task 1, Step 2.

---

## Before wave 1 (the controller)

- [x] Merge `origin/main` in (no rebase), `uv sync`, the gates, push. Done when this plan was written: the
  branch holds `main` with #86 and #87. #86 changed `version` in `manifest.json`, next to the `requirements`
  line Task 1 changes, so the tasks start from a head that has it. If `main` moves again before the task
  worktrees are made, repeat this step first.

---

### Task 1: Move to `Charger.active_charge`

**Model:** opus — it edits the charge control, next to charge start and stop, and the mapping of `pynortecgo` models to entities.
**Wave:** 1

**Files:**
- Modify: `pyproject.toml` (the `pynortecgo` pin)
- Modify: `custom_components/nortec_go/manifest.json` (`requirements`)
- Modify: `uv.lock` (by `uv lock`, never by hand)
- Modify: `custom_components/nortec_go/charge_control.py`
- Modify: `custom_components/nortec_go/coordinator.py`
- Modify: `custom_components/nortec_go/binary_sensor.py`
- Modify: `custom_components/nortec_go/sensor.py`
- Modify: `custom_components/nortec_go/costs.py`
- Modify: `tests/conftest.py` (`make_charger`)
- Modify: `tests/test_diagnostics.py` (the pins and the expected `charger` block)

**Interfaces:**
- Consumes, from `pynortecgo` 0.8.0: `Charger.active_charge: ActiveCharge | None`, and
  `ActiveCharge(id: str, state: ChargeState, state_raw: str, can_stop: bool, kwh: float | None, kw: float | None, cost: float | None)`.
  `Charger`'s fields, in order: `id`, `name`, `max_kw`, `state`, `state_raw`, `is_connected`, `currency`,
  `active_charge`, `last_charge`. The flat fields `charge_id`, `charge_state`, `charge_state_raw`,
  `can_stop`, `charge_kwh`, `charge_kw` and `charge_cost` are gone from `Charger`.
- Produces: `charge_state(charger: Charger) -> ChargeState | None` in `charge_control.py`, imported by
  `coordinator.py` and `binary_sensor.py`. `NortecGoChargeSensorDescription.value_fn` becomes
  `Callable[[ActiveCharge], float | None]`.

- [ ] **Step 1: Bump both pins**

In `pyproject.toml` and in `custom_components/nortec_go/manifest.json`, change `pynortecgo==0.7.0` to
`pynortecgo==0.8.0`. Nothing else in either file changes; `version` in `manifest.json` stays.

- [ ] **Step 2: Update the lock and the environment**

```bash
uv lock --upgrade-package pynortecgo && uv sync
git diff --stat uv.lock
git diff uv.lock | grep '^[-+]' | grep -v '^[-+][-+]'
```

Expected: `uv lock` prints one `Updated` line, `Updated pynortecgo v0.7.0 -> v0.8.0`, and the diff has four
changed line pairs, all for `pynortecgo`: the specifier where the lock repeats the project's own
requirement, the package's version, its sdist and its wheel. If `uv lock` names any other package, stop and
report it.

- [ ] **Step 3: See it fail (the red state)**

```bash
uv run mypy
```

Expected: FAIL, with errors only in `charge_control.py`, `coordinator.py`, `binary_sensor.py`, `sensor.py`,
`costs.py` and `tests/conftest.py`. They say `"Charger" has no attribute "charge_…"`, or name an unexpected
keyword argument for `Charger`; a line with such an error can carry a second one that follows from it (a
`no-any-return`, in `costs.py` and in `charge_status`). Keep the list: every line in it is a read this task
moves. An error in any other file means the spec's inventory is wrong: stop and report it.

- [ ] **Step 4: The fixture, `tests/conftest.py`**

Add `ActiveCharge` to the `from pynortecgo import (…)` block (it sorts first). Keep `make_charger`'s
signature and docstring exactly as they are, and replace only the `return Charger(…)` statement:

```text
    return Charger(
        id=charger_id,
        name=name,
        max_kw=11.0,
        state=state,
        state_raw=state.value,
        is_connected=is_connected,
        currency=currency,
        active_charge=None
        if charge_state is None
        else ActiveCharge(
            id=FAKE_CHARGE_ID,
            state=charge_state,
            state_raw=charge_state.value,
            can_stop=True,
            kwh=charge_kwh,
            kw=charge_kw,
            cost=charge_cost,
        ),
        last_charge=last_charge,
    )
```

Without a `charge_state`, a given `charge_kwh`, `charge_kw` or `charge_cost` is dropped: no charge is open.
That is what the two tests that do this mean (spec §5 item 1). Let `ruff format` settle the layout.

- [ ] **Step 5: The charge control, `custom_components/nortec_go/charge_control.py`**

Add the helper right above `charge_is_open`:

```python
def charge_state(charger: Charger) -> ChargeState | None:
    """The open charge's state, or None when no charge is open."""
    active = charger.active_charge
    return None if active is None else active.state
```

Then move the seven reads. Six are plain swaps of `charger.charge_state` for `charge_state(charger)`, with
nothing else in the expression changed. Four of them are in this file:

```text
charge_is_open:
    return charger.charge_state is not None or charger.state in (
->  return charge_state(charger) is not None or charger.state in (

is_charge_on:
    return control.start_pending or charger.charge_state in _CHARGE_ON
->  return control.start_pending or charge_state(charger) in _CHARGE_ON

async_stop:
    if charger is not None and charger.charge_state is ChargeState.STOPPING:
->  if charger is not None and charge_state(charger) is ChargeState.STOPPING:

on_charger_read:
    and charger.charge_state not in _CHARGE_ON
->  and charge_state(charger) not in _CHARGE_ON
```

`charge_status` binds the result to one local, because mypy narrows a local after an `in` check but not a
function call, and the last read takes `.value`. The local goes after the three early returns and right
above the `UNKNOWN` check. The function's end becomes:

```text
    if control.start_pending and not charge_is_open(charger):
        return "stopping" if control.stop_asked else "starting"
    of_charge = charge_state(charger)
    if charger.state is ChargerState.UNKNOWN or of_charge is ChargeState.UNKNOWN:
        return None
    if of_charge in _STATUS_FROM_CHARGE:
        return of_charge.value
    if charger.state is ChargerState.BUSY_NON_RELEASED:
        return "not_released"
    if not charger.is_connected:
        return "unplugged"
    return "idle"
```

Nothing else in this file changes: not the order of the checks, not `_CHARGE_ON` or `_STATUS_FROM_CHARGE`,
not the start path, the stop path or the timers. Don't read `can_stop`.

- [ ] **Step 6: The other reads**

`custom_components/nortec_go/coordinator.py`: add `charge_state` to the existing import, and swap the one
read in `interval_for`:

```text
from .charge_control import ChargeControl, ChargeControlState, charge_status
->  from .charge_control import (
        ChargeControl,
        ChargeControlState,
        charge_state,
        charge_status,
    )

    if charger.charge_state is ChargeState.CHARGING:
->  if charge_state(charger) is ChargeState.CHARGING:
```

`custom_components/nortec_go/binary_sensor.py`: add `from .charge_control import charge_state` above
`from .coordinator import NortecGoCoordinator`, and swap the read in the *Charging* description:

```text
        value_fn=lambda charger: charger.charge_state is ChargeState.CHARGING,
->      value_fn=lambda charger: charge_state(charger) is ChargeState.CHARGING,
```

`custom_components/nortec_go/sensor.py`: import `ActiveCharge` (`from pynortecgo import ActiveCharge, Charger, Vehicle`).
The charge sensors' `value_fn` takes the open charge:

```text
class NortecGoChargeSensorDescription:
    value_fn: Callable[[Charger], float | None]
->  value_fn: Callable[[ActiveCharge], float | None]

charge_energy:
        value_fn=lambda charger: charger.charge_kwh,
->      value_fn=lambda active: active.kwh,

charging_power:
        value_fn=lambda charger: charger.charge_kw,
->      value_fn=lambda active: active.kw,
```

and the charge sensor's `native_value` becomes:

```text
    @property
    def native_value(self) -> float | None:
        """The charge's value, or the no-charge value when no charge is open."""
        active = self.coordinator.data.charger.active_charge
        if active is None:
            return self.entity_description.no_charge_value
        return self.entity_description.value_fn(active)
```

The `no_charge_value`s, the cost sensors and every other description stay as they are.

`custom_components/nortec_go/costs.py`: the module docstring's second paragraph and `charge_cost` become:

```text
The one place that reads ActiveCharge.cost and Charger.last_charge.
```

```python
def charge_cost(charger: Charger) -> float | None:
    """The open charge's cost so far, or its billed total once it is the last completed charge."""
    active = charger.active_charge
    if active is None:
        return None
    last = charger.last_charge
    if last is not None and last.id == active.id:
        return last.cost
    return active.cost
```

`last_charge_cost` and `last_charge_completed_at` don't change.

- [ ] **Step 7: The diagnostics pins, `tests/test_diagnostics.py`**

Add `ActiveCharge` to the `from pynortecgo import (…)` block. Replace `CHARGER_FIELDS` and add the new pin
right below it:

```python
CHARGER_FIELDS = {
    "id",
    "name",
    "max_kw",
    "state",
    "state_raw",
    "is_connected",
    "currency",
    "active_charge",
    "last_charge",
}
ACTIVE_CHARGE_FIELDS = {"id", "state", "state_raw", "can_stop", "kwh", "kw", "cost"}
```

In `test_client_model_fields_are_pinned`, add one assertion after the `Charger` one:

```text
    assert {f.name for f in fields(ActiveCharge)} == ACTIVE_CHARGE_FIELDS
```

In the whole-output test, the expected `"charger"` block replaces its seven flat keys (`charge_state`,
`charge_state_raw`, `charge_id`, `can_stop`, `charge_kwh`, `charge_kw`, `charge_cost`) with one nested
block, in the model's field order (`currency` moves up, before it):

```text
                "is_connected": True,
                "currency": "DKK",
                "active_charge": {
                    "id": FAKE_CHARGE_ID,
                    "state": "charging",
                    "state_raw": "charging",
                    "can_stop": True,
                    "kwh": 4.2,
                    "kw": 7.1,
                    "cost": 9.87,
                },
                "last_charge": {
```

The `make_charger(…)` call in that test doesn't change, and nothing else in the file does. D38's judgement
for the seven fields: the download showed the same values before under other keys, none is a sign-in secret,
and IDs stay, so `TO_REDACT` and `diagnostics.py` don't change.

- [ ] **Step 8: The gates**

```bash
uv run pytest -q
uv run ruff check && uv run ruff format --check && uv run mypy && uv run actionlint && uv run zizmor --offline .github/workflows
uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95
```

Expected: all pass. In the coverage report, `charge_control.py`, `costs.py`, `sensor.py`, `binary_sensor.py`
and `coordinator.py` show no missing line that this task wrote or changed (compare the *Missing* column with
the lines you edited; `binary_sensor.py` has one uncovered line today, in the car sensor, which isn't
yours). If `ruff format --check` fails, run `uv run ruff format` and rerun. A failing test in
a file other than `conftest.py` or `test_diagnostics.py` is a behaviour change: fix the integration code,
never that test.

- [ ] **Step 9: The acceptance checks (spec §5)**

```bash
git diff --name-only HEAD -- tests
grep -rnE '\.(charge_id|charge_state|charge_state_raw|can_stop|charge_kwh|charge_kw|charge_cost)\b' custom_components tests
git diff HEAD -- custom_components/nortec_go/manifest.json
git diff HEAD -- custom_components/nortec_go/charge_control.py
```

Expected: the first prints exactly `tests/conftest.py` and `tests/test_diagnostics.py`; the grep prints
nothing (exit status 1); the manifest diff is the one `requirements` line. The `charge_control.py` diff is
the new helper, four one-line swaps (`charge_is_open`, `is_charge_on`, `async_stop`, `on_charger_read`) and
the `charge_status` block (one added line for the local, and the `UNKNOWN` condition and the two lines
below it reading the local), and nothing else. Put that diff in the report.

- [ ] **Step 10: The bump checklist (`docs/releasing.md`, *Bumping `pynortecgo`*)**

Work through its four items against the installed 0.8.0 (`.venv/lib/python3.14/site-packages/pynortecgo/`)
and put the result of each in the report, in the integration's own words (public names only, no endpoints,
headers or response shapes):

1. Exception messages, including errors wrapped from lower layers: read `exceptions.py` and the places that
   raise, and confirm no message holds an email, a password, a token, the device ID or a request body.
2. The diagnostics field pins: done in Step 7; say which fields were judged and that none is a secret.
3. New exception classes the charger, car, price, start and stop calls can raise: compare the names
   `pynortecgo/__init__.py` exports with the ones the integration handles (`grep -rn "Error" custom_components/nortec_go/*.py`).
   Expected: none is new.
4. Breaking changes to the models the entities use: the one this task moves; `ActiveCharge` is the only new
   public name.

- [ ] **Step 11: Commit**

Write `/tmp/pynortecgo-080-task-1-msg.txt` with the Write tool:

```text
chore(deps): move to pynortecgo 0.8.0 (#81)

The open charge is read from Charger.active_charge. Behaviour is unchanged:
under tests/ only the make_charger fixture and the diagnostics field pins
change.

<the co-author trailer from the dispatch>
```

```bash
git add pyproject.toml uv.lock custom_components/nortec_go tests/conftest.py tests/test_diagnostics.py
git commit -F /tmp/pynortecgo-080-task-1-msg.txt
git status --short
```

Expected: one commit, and a clean tree.

---

### Task 2: D46 and the bump docs

**Model:** opus — a docs task (D33).
**Wave:** 1

**Files:**
- Modify: `docs/decisions.md` (a new entry at the end)
- Modify: `docs/releasing.md` (*Bumping `pynortecgo`*: one checklist item and the paragraph below the checklist)

**Interfaces:**
- Consumes: the public name `ActiveCharge` (fixed by this plan; the code lands with Task 1), and the number
  D46, handed out by the PO. The task starts ahead of that input (`docs/way-of-working.md`, *Starting ahead
  of inputs*): its commit is picked only once Task 1 is on the feature branch.
- Produces: nothing other tasks use.

- [ ] **Step 1: The decision entry**

Append to `docs/decisions.md`, after D45, with one blank line before the heading. Only the heading and the
four bullets go in; the spec's sentence under the entry ("This move stays inside the rule…") is the spec's
own reasoning and stays out.

```markdown
### D46: The shape of the diagnostics download isn't user-visible
- **Date:** 2026-10-01 · **Status:** active
- **Decision:** A change that only moves, renames, adds or removes keys in the diagnostics download isn't a
  user-visible change, as long as what the user docs say the file keeps and leaves out stays true: it needs
  no changelog entry and doesn't make a PR releasing. D38 still decides what the download may show.
- **Why:** The owner's ruling (#81): the download is a support file, the user docs don't name its keys, and
  nothing is meant to be built on them. Without the rule, every client release that changes a model would
  force a release of the integration.
- **Source:** [pynortecgo 0.8.0 spec](superpowers/specs/2026-10-01-pynortecgo-0.8.0-design.md), Decisions
  and §4
```

The file's last entry is D45, with D44 before it.

- [ ] **Step 2: The checklist item in `docs/releasing.md`**

In *Bumping `pynortecgo`*, the second checklist item names the models whose fields are pinned. Add
`ActiveCharge`:

```text
  a changed `Charger`, `CompletedCharge` or `Vehicle` field: decide for each new field whether it is a
->  a changed `Charger`, `ActiveCharge`, `CompletedCharge` or `Vehicle` field: decide for each new field
```

and rewrap that item to the file's width (about 110 characters). Its other words don't change.

- [ ] **Step 3: The titling paragraph in `docs/releasing.md`**

Right below the checklist, the paragraph is:

```text
Title such a PR by what it changes for users (*PR titles*). If users see a difference, it's a `feat` or
`fix` with a changelog entry and the bump step. If they don't, it's `chore(deps): …`.
```

Add one sentence at its end, and rewrap:

```text
A change only in the shape of the diagnostics download isn't something users see, as long as what the user
docs say the file keeps and leaves out stays true (D46).
```

Only this paragraph under *Bumping `pynortecgo`* changes; the one with the same opening under *Bumping Home
Assistant* stays.

- [ ] **Step 4: Check**

```bash
grep -n "D46" docs/decisions.md docs/releasing.md
grep -n "ActiveCharge" docs/releasing.md
git diff --stat
uv run pytest -q
uv run ruff check && uv run ruff format --check && uv run mypy && uv run actionlint && uv run zizmor --offline .github/workflows
uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95
```

Expected: D46 once as a heading in `decisions.md` and once in `releasing.md`; `ActiveCharge` once in
`releasing.md`; only those two files changed; the gates pass (this task's worktree is still on
`pynortecgo` 0.7.0, which is fine: it changes no code).

- [ ] **Step 5: Commit**

Write `/tmp/pynortecgo-080-task-2-msg.txt` with the Write tool:

```text
docs: D46, the diagnostics download's shape isn't user-visible (#81)

The bump checklist names ActiveCharge among the pinned models.

<the co-author trailer from the dispatch>
```

```bash
git add docs/decisions.md docs/releasing.md
git commit -F /tmp/pynortecgo-080-task-2-msg.txt
```

---

## After the last task (the controller)

- [ ] On the feature branch with both tasks picked: `uv sync`, the gates, and the four checks of Task 1,
  Step 9, with the three diffs against the merge base instead of `HEAD` (the tasks are committed by then):
  `git diff --name-only origin/main...HEAD -- tests`, and `git diff origin/main...HEAD --` for
  `manifest.json` and for `charge_control.py`. The expected output is Step 9's.
- [ ] Task 2 started from names this plan fixes: re-check `docs/releasing.md`'s `ActiveCharge` against the
  code that landed (`grep -n "ACTIVE_CHARGE_FIELDS" tests/test_diagnostics.py`).
- [ ] File the follow-up issue (label `v3`), and name it in the PR description. It holds:
  - the two test cases that became duplicates (`no_charge_ignores_cost`, `no_charge_ignores_fields`), and
    `make_charger` dropping charge values given without a state;
  - two missing tests in the charge control (Review Focus 5): a stop with a read charger and no open charge
    sends the stop, and `charge_status` with a pending start and an unknown charger state.
- [ ] If `main` moved again: merge `origin/main` in (no rebase), and rerun the gates and the checks.
- [ ] The PR description: the bump checklist's four results (Task 1, Step 10), the rulings (the release
  level; the client's changed warning wording isn't user-visible; D46), the learnings or that there are none,
  the follow-up issue, and that the PR is the owner's to merge (D45).
