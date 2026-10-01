# The cost of a charge — design

Date: 2026-10-01 · Branch: `feat/session-cost` · Issue: #76

## Goal

- **What:** two sensors on the charger device. *Cost this charge* shows what the open charge costs so far.
  *Last charge cost* shows the billed total of the most recent completed charge. Both are the values
  `pynortecgo` reports; nothing is computed from kWh × price. The client goes from 0.5.0 to 0.7.0, which
  has those values.
- **Why:** the owner wants to see the price of the current charging session (#76), as exact values (the
  owner's answer on #75). The live value ends below the bill, so the billed total needs its own sensor.
- **Not in this work:**
  - a total energy sensor for the Energy dashboard (#75; it waits for a lifetime meter in the client);
  - any change to the polling intervals (§5);
  - moving the existing reads of the open charge's fields (see *Decisions*, the 0.8.0 row).
- **Done when:** built TDD with `pynortecgo` mocked in every test; the gates pass; user docs, the manual
  test guide, the changelog and the decision log updated.

## Decisions

Proposed by the team lead; the owner answered the two questions on #76 through the PO (2026-10-01).

| Topic | Decision |
|---|---|
| Which sensors | *Cost this charge* and *Last charge cost* (the owner's answer: option B) |
| Exact values | Both show the client's values. No cost is computed from energy and price |
| *Cost this charge* | Monetary, no state class: history only, no long-term statistics. Unknown when no charge is open, as *Energy this charge* |
| While stopping | When the last completed charge is the open charge (same ID), *Cost this charge* shows its billed total instead of the live value |
| *Last charge cost* | Monetary, `total`, with `last_reset` = the charge's completion time. Each completed charge is a new cycle, so the long-term statistics sum is the money billed for the charges completed after the sensor's first value |
| Unit | `Charger.currency`, then the price forecast's currency, then Home Assistant's (D34's order, with the charger's own first). `sensor.py` reads the currency: it is a field of the charger, not of the open charge |
| Polling | Unchanged (D29, D31). A charger read now costs one more request (§5) |
| The start path | `UnknownChargerStateError` (new in the client) is a pre-check error: it shows the existing "charger state unknown" message (the owner's answer: yes, in this PR). Nothing else near start or stop changes |
| Diagnostics | The new fields are shown, none redacted (D38: only the sign-in secrets). The pinned field sets grow, and the completed charge's fields are pinned too |
| `pynortecgo` 0.8.0 | It will replace the charger's flat open-charge fields with one object. So the new reads (`charge_cost`, `last_charge`, and `charge_id` for the swap) sit in one new module (§2), and the move is a small follow-up. The existing reads of `charge_id`, `charge_state`, `charge_kwh` and `charge_kw` stay where they are in this PR |
| Decision log | D42 (§9) |
| PR title | `feat`, releasing: a minor version |

Facts used, public-safe:

- `pynortecgo` 0.7.0, from its docstrings:
  - `Charger.charge_cost`: what the account pays for the open charge so far, incl. VAT, fees and the grid
    tariff. It can trail `charge_kwh` by a reading, and its last value before a charge closes was seen
    below the billed total. `None` when no charge is open, or when an open charge has no cost reading.
  - `Charger.currency`: the ISO 4217 code of the charger's prices, set with or without an open charge;
    `None` when the charger gives none or not 3 letters.
  - `Charger.last_charge`: a `CompletedCharge` (`id`, `cost`, `kwh`, `completed_at` in UTC), the most recent
    completed charge on the charger, with its billed cost. During a charge it is the previous one; while
    stopping it can already be the open charge (`charge_id == last_charge.id`). `None` when none is among
    the newest charges, or when its read failed.
  - `get_charger()` makes one more request on every call, for the last completed charge: 2 requests with no
    open charge, 3 with one. If that request fails, `last_charge` is `None`, the client logs it once until a
    later read succeeds, and the rest of the charger is returned. An authentication failure still raises.
  - `start_charge()` raises `UnknownChargerStateError` (a `NortecGoError`) before any payment request when
    the charger reports a state the client doesn't know. So no card hold.
  - The three new `Charger` fields are required, so every `Charger` a test builds must pass them.
- Home Assistant 2026.9.3, the sensor recorder (read in the installed version):
  - `monetary` allows only the state class `total`, or none.
  - For `total` without `last_reset`, a drop counts as a negative change. A per-charge value that restarts
    would give a sum that is just the current value. That is why *Cost this charge* has no state class.
  - For `total` with `last_reset`, a changed `last_reset` starts a new cycle from 0: the new value is added
    in full. The same `last_reset` adds only the change in value. The first value ever recorded sets the zero
    point and isn't added. Unknown and unavailable states are skipped.
- `pynortecgo` 0.7.0's log lines and the new exception's text hold no email, password, token or device ID
  (checked for the bump, `docs/releasing.md` → *Bumping `pynortecgo`*). `UnknownChargerStateError`'s text
  names the charger's raw state, an API enum value.

## 1. Files

| File | Change |
|---|---|
| `custom_components/nortec_go/manifest.json`, `pyproject.toml`, `uv.lock` | `pynortecgo==0.7.0` (§6) |
| `custom_components/nortec_go/costs.py` | New: the cost reads (§2) |
| `custom_components/nortec_go/sensor.py` | The two sensors (§3) |
| `custom_components/nortec_go/charge_control.py` | One entry in `_PRE_CHECK_ERRORS` (§4) |
| `custom_components/nortec_go/strings.json`, `translations/en.json` | The two names (§3) |
| `docs/user/nortec_go.md` | §7 |
| `docs/manual-testing.md` | §7 |
| `docs/releasing.md` | §7 |
| `CHANGELOG.md` | §8 |
| `docs/decisions.md` | D42 (§9) |
| `tests/conftest.py` | `make_charger` passes the new fields (§10) |
| `tests/test_costs.py` (new), `tests/test_sensor.py`, `tests/test_charge_control.py`, `tests/test_diagnostics.py` | §10 |

`coordinator.py`, `diagnostics.py`, `const.py` and `quality_scale.yaml` don't change. The diagnostics dump
the charger with `asdict`, which also covers the new fields and the nested completed charge. No rule in
`quality_scale.yaml` changes status, and the comment on `appropriate-polling` names only intervals.

## 2. `costs.py`

Pure functions over a `Charger`; no Home Assistant imports. This is the one place that reads `charge_cost`
and `last_charge`.

- `charge_cost(charger: Charger) -> float | None`: the open charge's cost.
  - `None` when `charger.charge_id` is `None`.
  - `charger.last_charge.cost` when `last_charge` is not `None` and its `id` equals `charger.charge_id`
    (the charge is already billed).
  - Otherwise `charger.charge_cost`, which can be `None`.
- `last_charge_cost(charger: Charger) -> float | None`: `charger.last_charge.cost`, or `None` without a
  last charge.
- `last_charge_completed_at(charger: Charger) -> datetime | None`: `charger.last_charge.completed_at`, or
  `None` without a last charge.

## 3. The sensors

Both are `NortecGoChargerEntity` sensors on the charger device, from one class `NortecGoCostSensor` with a
description (`NortecGoCostSensorDescription`) that holds `value_fn` and an optional `last_reset_fn`, both
taking the `Charger`. `async_setup_entry` always adds both.

| Key | Name | Device class | State class | `value_fn` | `last_reset_fn` |
|---|---|---|---|---|---|
| `charge_cost` | Cost this charge | `monetary` | none | `costs.charge_cost` | none |
| `last_charge_cost` | Last charge cost | `monetary` | `total` | `costs.last_charge_cost` | `costs.last_charge_completed_at` |

- **Unique IDs** follow the base entity: `<charger id>_<key>`.
- **Value:** `value_fn(coordinator.data.charger)`. `None` shows as unknown.
- **Unit:** a `native_unit_of_measurement` property:
  `charger.currency or coordinator.price_currency or hass.config.currency`. The charger's currency comes
  with every read, so the fallbacks matter only when the charger names none.
- **`last_reset`:** a property; `last_reset_fn(charger)` when the description has one, else `None`.
- **Precision:** `suggested_display_precision=2`.
- **Availability:** the base behaviour: unavailable after a failed charger read, like *Energy this charge*.
- **Category and default:** no entity category, enabled by default.

What the user sees:

| Situation | *Cost this charge* | *Last charge cost* |
|---|---|---|
| No charge open | Unknown | The last completed charge's billed total |
| A charge is open | The cost so far | The previous charge's billed total |
| Stopping, and the charge is already the last completed one | Its billed total | The same billed total |
| An open charge without a cost reading | Unknown | As above |
| The client gives no last charge (none among the newest, or its read failed) | As above | Unknown |

A *Last charge cost* that turns unknown and comes back with the same charge has the same `last_reset`, so
the statistics add nothing twice. The design assumes that `last_charge` never goes back to an older charge;
if it did, the changed `last_reset` would count that charge again. No guard is added for it.

## 4. The start path

`_PRE_CHECK_ERRORS` in `charge_control.py` gets `UnknownChargerStateError: "charger_state_unknown"`. A
start that the client refuses for an unknown charger state then raises `ServiceValidationError` with the
existing text, as the integration's own check on the last read already does, instead of the generic "start
failed". No string is added. The start guard, the block, the hold handling and the stop path don't change,
and nothing is retried (hard rule 6).

## 5. Requests and polling

`get_charger()` now makes 2 requests with no open charge and 3 with one (it was 1 and 2). With D29's
intervals:

| Charge status | Interval | Requests per read | Before |
|---|---|---|---|
| Charging | 5 min | 3 | 2 |
| Starting or stopping | 30 s | 3 (2 while a start is pending and no charge is open yet) | 2 (1) |
| Anything else | 60 min | 2 (3 while a paused charge is open) | 1 (2) |

So an idle day goes from 24 to 48 requests, an hour of charging from 24 to 36, and the 30-second reads,
which D29 and D31 bound to a few minutes, from 4 to 6 a minute. The car and price reads don't change. Outside
those few minutes that is under one request a minute, so the intervals stay, and D29 and D31 keep their
status.

No read is added after a charge closes. The read that first sees no open charge usually carries the charge
as `last_charge`. If the charger doesn't list it yet, *Last charge cost* follows at the next read (up to 60
minutes later) or on *Refresh*.

Errors: the read path gets no new exception. A failed read of the last charge is the client's to log; the
integration shows *Last charge cost* as unknown and logs nothing more.

## 6. The client bump

`manifest.json` and `pyproject.toml` pin `pynortecgo==0.7.0`; the lock is updated with
`uv lock --upgrade-package pynortecgo`. The checklist in `docs/releasing.md` → *Bumping `pynortecgo`*:

- exception messages and log lines: checked, see *Facts used*;
- `test_client_model_fields_are_pinned`: §10;
- new exception classes: `UnknownChargerStateError`, §4;
- breaking model changes: the three required `Charger` fields, §10.

## 7. User docs and the manual test guide

`docs/user/nortec_go.md`:

- *Supported functionality* → *Charger*, two rows after *Charging power*:

  > | Cost this charge | Sensor | What the open charge costs so far, incl. VAT, fees and the grid tariff, in the charger's currency. Unknown when no charge is open. It can lag *Energy this charge* by a reading, and its last value can be below the billed total; while a charge is stopping it can already show the billed total |
  > | Last charge cost | Sensor | The billed total of the most recent completed charge on the charger. Its long-term statistics add up the charges completed after the sensor's first value. Unknown if the charge isn't among the charger's newest, or if it couldn't be read |

- *Data updates*: the sentence on *Energy this charge* and *Charging power* also names *Cost this charge*,
  and one sentence is added:

  > *Last charge cost* follows at the first read after a charge ends, or the one after it (up to 60 minutes
  > later); press *Refresh* to read it sooner.

- *Known limitations*, one line:

  > *Last charge cost* misses a charge when two charges end between two reads, or when a charge that ended
  > while Home Assistant was off is no longer the most recent one. Its statistics then lack that charge.
  > They also lack the charge the sensor first showed: usually one from before you added the sensor, but
  > the first one after it if the sensor was unknown until then.

- *Diagnostics*: the sentence on what the file keeps also names the last completed charge:

  > It keeps your charger's and car's names and IDs, and the last charge's ID, cost and time, …

`docs/manual-testing.md` → *Entities*, under *Charger*: two lines, *Cost this charge* and *Last charge
cost*, in the form of the lines there. (That section's intro already says the owner checks the values and
an agent sees none; nothing is added for it.)

`docs/releasing.md` → *Bumping `pynortecgo`*: the checklist item on `test_client_model_fields_are_pinned`
says "a changed `Charger`, `CompletedCharge` or `Vehicle` field".

## 8. Changelog

Under *Unreleased*:

> ### Added
>
> - *Cost this charge*: what the open charge costs so far.
> - *Last charge cost*: the billed total of the most recent completed charge. Its long-term statistics add
>   up what the charges completed from then on cost.
>
> ### Changed
>
> - `pynortecgo` 0.7.0. Each charger read makes one more request.
> - A start refused because the charger reports an unknown state says so, instead of showing a general
>   failure.

## 9. Decision log

```markdown
### D42: Charge costs are the client's exact values
- **Date:** 2026-10-01 · **Status:** active
- **Decision:** *Cost this charge* shows the open charge's cost as `pynortecgo` reports it, with no state
  class; *Last charge cost* shows the last completed charge's billed total as `total`, with `last_reset` at
  the charge's completion time. No cost is computed from energy and price, and the unit is the charger's
  currency, then D34's order.
- **Why:** The owner chose exact values over estimates (#75). A per-charge value without `last_reset` gives a
  wrong statistics sum, and the live value ends below the bill, so only the billed totals are summed.
- **Source:** [session cost spec](superpowers/specs/2026-10-01-session-cost-design.md), Decisions and §3
```

## 10. Tests

`pynortecgo` is mocked in every test, and fixtures are built from its model objects (hard rule 7).

`tests/conftest.py`:

- `make_charger` gets the keyword arguments `charge_cost: float | None = None`,
  `currency: str | None = "DKK"` and `last_charge: CompletedCharge | None = None`, and passes them on. The
  charge ID stays as it is: `FAKE_CHARGE_ID = "fake-charge-id"` (a new constant for today's literal) when a
  charge is open, `None` otherwise. `tests/test_diagnostics.py` imports it and drops its own copy.
- `make_completed_charge(*, charge_id: str = "fake-last-charge-id", cost: float = 42.5, kwh: float = 18.4,
  completed_at: datetime = FAKE_COMPLETED_AT) -> CompletedCharge`, with `FAKE_COMPLETED_AT =
  datetime(2026, 9, 25, 6, 15, tzinfo=UTC)`. Its default ID differs from `FAKE_CHARGE_ID`, so an open-charge
  test with a last charge doesn't trigger the swap by accident; the equal-ID case passes
  `charge_id=FAKE_CHARGE_ID`.
- `make_charger` is the only place that builds a `Charger`, so the other tests keep passing unchanged.

`tests/test_costs.py`:

- `charge_cost`: `None` with no open charge, even when `charge_cost` is set; the live value with an open
  charge and no last charge; the live value when the last charge has another ID; the last charge's cost
  when the IDs are equal; `None` for an open charge without a cost reading and no matching last charge.
- `last_charge_cost` and `last_charge_completed_at`: the values, and `None` without a last charge.

`tests/test_sensor.py`:

- both sensors exist on the charger device, with their unique IDs, device class `monetary`, display
  precision 2, no entity category; *Cost this charge* has no state class and no `last_reset` attribute;
  *Last charge cost* has `total` and `last_reset` equal to the completion time;
- the values in each row of §3's table;
- the unit: the charger's currency; the forecast's when the charger names none; Home Assistant's when
  neither does;
- both are unavailable after a failed charger read;
- across reads: a completed charge, then unknown (no last charge), then the same charge again keeps the
  same `last_reset`; a new completed charge changes the value and `last_reset`.

`tests/test_charge_control.py`: a start where `start_charge` raises `UnknownChargerStateError` raises
`ServiceValidationError` with the key `charger_state_unknown`, sets no block, leaves no pending start and
calls `start_charge` once.

`tests/test_diagnostics.py`: `CHARGER_FIELDS` gets `charge_cost`, `currency` and `last_charge`; a new
`COMPLETED_CHARGE_FIELDS` (`id`, `cost`, `kwh`, `completed_at`) is pinned in
`test_client_model_fields_are_pinned`; the expected outputs show the new fields, unredacted, including a
last charge.

`tests/test_manifest.py` needs no change: it checks that the two pins match.
