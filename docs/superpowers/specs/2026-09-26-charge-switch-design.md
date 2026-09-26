# Charge switch — design

Date: 2026-09-26 · Branch: `feat/charge-switch` · Issue: #9

## Goal

- **What:** the third feature. A *Charge* switch on the charger device starts and stops a charge, guarded
  against repeated starts; a *Charge status* sensor shows the charge's phase and the guard; a repair issue
  explains a blocked start and lets the owner clear it.
- **Why:** [EV Smart Charging](https://github.com/jonasbkarlsson/ev_smart_charging) (EVSC) can then charge the
  car in the cheapest slots through Nortec Go's own entities.
- **Not in this work:** energy and average power sensors (#24, needs NortecGo#55), diagnostics (#11), the
  manual test guide (#10).
- **Done when:** built TDD with `pynortecgo` mocked in every test; the gates pass; the owner has run one live
  start and one stop (only with the owner's explicit OK, hard rule 2); quality scale and user docs updated.

## Decisions

Answered by the owner in the brainstorm (2026-09-26), unless marked *controller*: the owner delegated the
rest and reviews them in the PR.

| Topic | Decision |
|---|---|
| Switch state | On while a charge is open and not ending: `charge_state` is `STARTING`, `CHARGING` or `PAUSED`; also while our own start is pending, unless a stop was asked for (§3.2). Off otherwise, including `STOPPING` |
| Guard | After a start that may have left a card hold, starts are blocked until the cable has been unplugged, or the owner confirms in the repair issue. Reload and restart don't clear it (it is stored) |
| Clearing | A read that sees the cable unplugged, a charger that goes from `BUSY_NON_RELEASED` to `AVAILABLE` (both reads after the block was set), a read that sees a charge open, or the repair issue's fix flow |
| Status sensor | An enum sensor, *Charge status*, including `start_blocked` |
| EVSC's repeated "on" | A no-op while a charge is open or our start is pending (§3.1). EVSC calls `turn_on` without checking the switch |
| Pending start | *Controller.* After a successful `start_charge()` the start is pending until a read sees that a charge happened. If no read within 10 minutes sees it, the start counts as failed with a hold, and starts are blocked |
| Stop during a pending start | *Controller.* The pending start and its guard stay; the switch shows off; the first read that sees the charge open stops it once. The request ends with the pending start |
| Availability | *Controller.* The switch stays available after a failed read, so EVSC's `turn_off` still reaches `stop_charge()` (HA skips unavailable entities in service calls without an error) |
| Power sensor | Out of scope: the API has no live power field. #24 works it out from delivered energy |

Facts about the charger, from the `NortecGo` session (2026-09-26), public-safe. "Observed" means seen in
real traffic:

- `start_charge()` raises its pre-check errors (`ChargeAlreadyActiveError`, `CableNotConnectedError`,
  `ChargerNotReleasedError`, card and car errors) before any payment request: no hold.
- After a finished charge with the cable left in, the charger stays `BUSY_NON_RELEASED` (observed for
  10.5 h) and turns `AVAILABLE` only when the cable is unplugged. It stays `AVAILABLE` after the replug.
  So `BUSY_NON_RELEASED` followed by `AVAILABLE` means an unplug happened, even if no read saw it.
- So after a stop, a new start needs an unplug and replug first: `start_charge()` raises
  `ChargerNotReleasedError` until then.
- After a failed start with no charge, nothing in `Charger` shows a replug. A quick unplug and replug
  (observed: about 1 minute) between two reads can't be seen.
- A hold that led to no charge was never observed; it is assumed to expire by itself within about 7 days.
  No way to cancel a hold is known.
- `Charger.is_connected` is live (about 20 s); the car's data lags minutes to hours, so the guard never uses
  the car.
- `BUSY` is brief, right after a start. `BUSY_CHARGING` covers a charge that is starting, charging or
  stopping.
- Enums can be `UNKNOWN`; the integration treats an unknown charger state as "don't start".

What EVSC does (its README and `coordinator.py`, checked 2026-09-26):

- *Charger control entity*: a switch or input boolean; EVSC calls `turn_on` / `turn_off` on it at slot
  changes, without checking its state first.
- *Charging state entity* (optional): must be `on` while charging. When charging should be on and it isn't,
  EVSC calls `turn_on` again at minutes 5, 10, 20, 25, 35, 40, 50 and 55. It never repeats `turn_off`.
- *Continuous charging preferred* (a switch, on by default) plans one continuous session, which suits a
  charger that needs a replug between charges.

## 1. Files

| File | Change |
|---|---|
| `custom_components/nortec_go/charge_control.py` | New. `ChargeControl`: the start and stop calls, reauth on their `AuthError`, the pending start, the block, its `Store` and the repair issue (§3). No entity code |
| `custom_components/nortec_go/coordinator.py` | Owns a `ChargeControl`; passes each charger read to it (§3.4); 5-minute interval while a start is pending |
| `custom_components/nortec_go/switch.py` | New. The *Charge* switch (§2.1) |
| `custom_components/nortec_go/sensor.py` | The *Charge status* sensor (§2.2) |
| `custom_components/nortec_go/repairs.py` | New. The fix flow for the start block (§3.5) |
| `custom_components/nortec_go/__init__.py` | `Platform.SWITCH`; load the control's stored state at setup; `async_remove_entry` also removes its store and its repair issue |
| `custom_components/nortec_go/const.py` | `START_CONFIRM_TIMEOUT`, the control's store key and version, the repair issue ID format |
| `custom_components/nortec_go/strings.json`, `translations/en.json` | Entity names, the status options, `exceptions`, the repair issue and its fix flow |
| `custom_components/nortec_go/manifest.json` | `repairs` in `dependencies` only if hassfest requires it for the fix flow |
| `custom_components/nortec_go/quality_scale.yaml` | §6 |
| `tests/…` | §5 |
| `docs/user/nortec_go.md`, `CHANGELOG.md` | §7 |
| `docs/decisions.md` | §8 |

## 2. Entities

### 2.1 Charge switch

- Charger device, key `charge` (named *Charge*, apart from the *Charging* binary sensor), no device class,
  `PARALLEL_UPDATES = 1`.
- **`is_on`:** `ChargeControl.is_charge_on(charger)`: true when a start is pending and no stop was asked for,
  or when no stop was asked for and `charge_state` is `STARTING`, `CHARGING` or `PAUSED`. False while a stop
  is asked for during a pending start.
- **`turn_on`** → `ChargeControl.async_start()`, **`turn_off`** → `ChargeControl.async_stop()` (§3).
- **Available** whenever the coordinator has data (always after setup), even after a failed read: it shows
  the last read's state, and `turn_off` still calls `stop_charge()`. The other entities keep the usual
  availability.

### 2.2 Charge status sensor

Charger device, key `charge_status`, device class `enum`, translated options. The first matching row wins:

| Value | When |
|---|---|
| `start_blocked` | the block is set |
| `starting` | a start is pending and the read shows no charge yet |
| `None` (HA's *unknown*) | `Charger.state` or `charge_state` is `UNKNOWN` |
| `starting`, `charging`, `paused`, `stopping` | `charge_state` |
| `not_released` | `Charger.state` is `BUSY_NON_RELEASED` |
| `unplugged` | not `is_connected` |
| `idle` | otherwise |

- The options are `start_blocked`, `starting`, `charging`, `paused`, `stopping`, `not_released`, `unplugged`,
  `idle`. `charge_state` `COMPLETED` (not seen on the charger) shows as `idle`.

## 3. Charge control

`ChargeControl` lives in `charge_control.py`, one per entry, owned by the coordinator. It holds the pending
start (its time and a "stop asked" flag), the block (its time) and the state seen by the last read after the
block was set, and an `asyncio.Lock`: starts, stops and the background stop (§3.4) all run under it.

- **"A charge is open"** in a read: `charge_state is not None`, or `Charger.state` is `BUSY` or
  `BUSY_CHARGING` (the same test `pynortecgo` uses for `ChargeAlreadyActiveError`).
- **"A charge happened"**: a charge is open, or `Charger.state` is `BUSY_NON_RELEASED` (a charge opened and
  closed between reads).
- **Every change** to the pending start, the stop asked flag or the block saves the store and calls
  `coordinator.async_update_listeners()`, because the coordinator (`always_update=False`) doesn't notify
  entities for an unchanged read.
- **Saves** use `Store.async_delay_save` (sync, flushed at HA's final write), so a change made while being
  cancelled still lands.
- **Reauth:** on an `AuthError` from its own calls, `ChargeControl` calls `entry.async_start_reauth(hass)`.
- **Raised errors** are translated (`translation_domain=DOMAIN`) and raised `from None`, so no chained
  exception (for example a `ChargeStartError`'s cause) reaches a caller's log. The control logs the error
  class and `str(err)` itself (`pynortecgo`'s texts hold no private data).

### 3.1 Start

Under the lock, in order:

1. **Nothing to do:** if a start is pending, clear its stop asked flag and return. If the last read shows a
   charge open, return. No API call.
2. **Blocked:** raise `ServiceValidationError`, `start_blocked`.
3. **Unknown charger:** if the last read's `Charger.state` is `UNKNOWN`, raise `ServiceValidationError`,
   `charger_state_unknown`.
4. **`await client.start_charge()`**, once. Never retried, by us or by HA.
5. **Success:** set the pending start (now, stop not asked) and ask the coordinator for a read
   (`async_request_refresh`).

A second `turn_on` from HA waits behind the first (the platform semaphore and the lock), then finds the
pending start in step 1.

| Error | Result | Block |
|---|---|---|
| `CableNotConnectedError` | `ServiceValidationError` `cable_not_connected` | no |
| `ChargerNotReleasedError` | `ServiceValidationError` `charger_not_released` (unplug and replug) | no |
| `ChargeAlreadyActiveError` | none: the charge is on; ask for a read | no |
| `PaymentSourceNotFoundError`, `MultiplePaymentSourcesError` | `ServiceValidationError` `no_payment_source` / `multiple_payment_sources` | no |
| `VehicleNotFoundError`, `MultipleVehiclesError` | `ServiceValidationError` `no_vehicle` / `multiple_vehicles` | no |
| `ChargeStartError`, `hold_may_be_placed` true | `HomeAssistantError` `start_failed_hold`; ask for a read | **yes** |
| `ChargeStartError`, `hold_may_be_placed` false | `HomeAssistantError` `start_failed` | no |
| `AuthError` (pre-check) | start reauth; `HomeAssistantError` `auth_failed` | no |
| `RateLimitError`, `NortecGoConnectionError`, `ApiError`, `UnexpectedResponseError`, other `NortecGoError` (pre-check) | `HomeAssistantError` `start_failed` | no |
| `asyncio.CancelledError` | set the block, then re-raise | **yes** |

- `ChargeStartError` wraps every failure after the first payment request, including an `AuthError`, so an
  `AuthError` outside it comes from the pre-check. With `step` `START` the charge may have started: the read
  it asks for sees it, and a charge seen open clears the block (§3.4).
- A cancelled start may have left a hold or a charge, so it is treated like a failure with a hold.

### 3.2 Pending start

- Set on success, with the time; stored, so a restart keeps it.
- While pending: `turn_on` is a no-op (and clears stop asked), the status is `starting` until the read shows
  the charge, and the coordinator reads every 5 minutes. The switch is on unless a stop is asked.
- **Ends, without a block,** when a read sees that a charge happened, or sees the cable unplugged.
- **Times out** when a read at least `START_CONFIRM_TIMEOUT` (10 min) after the start sees neither: the start
  counts as failed with a hold. The pending start ends, the block is set, and a warning is logged. This
  happens whether or not a stop was asked.

### 3.3 Stop

Under the lock:

1. **Pending start and the last read shows no charge open:** set stop asked and ask for a read. No API call.
   (The charge isn't visible yet, so `stop_charge()` would only answer `NoActiveChargeError`.)
2. **Charge already stopping:** if the last read's `charge_state` is `STOPPING`, return.
3. **`await client.stop_charge()`**, once; then end any pending start and ask for a read.

| Error | Result |
|---|---|
| `NoActiveChargeError` | none: nothing to stop; ask for a read |
| `ChargeNotStoppableError` | `HomeAssistantError` `charge_not_stoppable` |
| `AuthError` | start reauth; `HomeAssistantError` `auth_failed` |
| other `NortecGoError` | `HomeAssistantError` `stop_failed`; ask for a read (the stop may have happened) |

### 3.4 Each charger read

The coordinator calls `ChargeControl.async_on_charger_read(charger)` after every successful charger read,
before it sets the interval. In order:

1. **Pending start with stop asked, and a charge open:** end the pending start and start a background task
   (`entry.async_create_background_task`) that takes the lock and calls `stop_charge()` once, with §3.3's
   error handling, logged instead of raised.
2. **Pending start:** ends or times out as in §3.2. A timeout sets the block.
3. **Block:** cleared if the cable isn't connected, a charge is open, or the remembered state is
   `BUSY_NON_RELEASED` and this read's is `AVAILABLE`. The remembered state is only from reads after the
   block was set: setting the block forgets it, and it isn't stored, so a transition across a restart isn't
   seen (safe: the block stays).
4. **Remember** `Charger.state` while a block is set.

Step 2 before step 3 means a timeout on a read that sees the cable unplugged ends the pending start
without a block (§3.2), and a block set by a timeout is only cleared by a later read.

The interval (D22) is 5 minutes while a start is pending, otherwise unchanged.

### 3.5 Block, store and repair issue

- **Store:** `helpers.storage.Store`, version 1, key `nortec_go.<entry_id>.charge_control`:
  `{"blocked_since": ISO 8601 UTC | null, "start_pending_since": ISO 8601 UTC | null, "stop_asked": bool}`.
  No IDs. Loaded at setup before the first refresh. A missing file gives the empty state. A file of the
  wrong shape logs a warning and sets the block (fail safe: a stored block may have been lost).
- **Setting the block** logs a warning and creates the repair issue.
- **Repair issue:** `ir.async_create_issue`, ID `start_blocked_<entry_id>`, `is_fixable=True`,
  `is_persistent=False`, severity `error`, `data={"entry_id": …}`, translated, with `entry.title` (the
  charger's name or *Nortec Go*) as the only placeholder. The text: a start failed after a card hold may have
  been placed; starts are blocked so no new hold is placed; a hold that led to no charge is expected to
  expire by itself; check the charger in the Nortec Go app, then unplug and replug the cable, or confirm
  here.
- **At setup** a stored block recreates the issue.
- **Fix flow** (`repairs.py`, `async_create_fix_flow` reads `entry_id` from `data`): one confirm step. On
  confirm, if the entry is loaded, clear the block; otherwise abort with `not_loaded`. HA deletes the issue
  when the flow finishes.
- **Clearing the block** by any path deletes the issue and logs an info line.
- **Removal:** `async_remove_entry` removes the store and deletes the issue.

## 4. Errors and availability

- Every exception the switch raises is translated (`strings.json` → `exceptions`).
- The coordinator's read error handling is unchanged
  ([read-only entities spec](2026-09-26-read-only-entities-design.md) §4.2).
- The switch stays available after a failed read (§2.1); the status sensor is unavailable then, like the
  other charger entities.

## 5. Tests

TDD; `pynortecgo` always mocked; fixtures built from `pynortecgo` model objects (hard rule 7). `make_charger`
gains a `state` argument. No test reaches the real API.

- **`test_charge_control.py`:**
  - every row of §3.1 and §3.3: the error raised, block or not, reauth, a read asked for, raised `from None`;
  - `start_charge` called exactly once in every path, never retried; a second `turn_on` after a success is
    a no-op;
  - pending start: no-op `turn_on`; ends on a charge open, on `BUSY_NON_RELEASED`, on the cable unplugged;
    times out into the block, also on a read that returns the same `Charger` as before (the entities still
    update);
  - stop during a pending start: no API call, the switch off, the stop when the charge appears, `turn_on`
    after `turn_off` clears stop asked, and the request ends with the timeout;
  - stop while `STOPPING` is a no-op;
  - each clearing path of §3.4, and a `BUSY_NON_RELEASED` read from before the block does **not** clear it;
  - a cancelled start sets the block;
  - store round-trip, a restart keeps the block and the pending start, a wrong-shape file sets the block;
  - the repair issue created, recreated at setup, deleted on clear.
- **`test_switch.py`:** state for each charge state, on while pending, off while stop asked,
  `turn_on`/`turn_off` through the HA service, translated error messages, available after a failed update
  with `turn_off` still calling `stop_charge()`.
- **`test_sensor.py`:** every row of §2.2.
- **`test_repairs.py`:** the fix flow clears the block and the issue is gone; aborts when the entry isn't
  loaded.
- **`test_coordinator.py`, `test_init.py`:** the interval while pending; the control's read hook; removal
  removes the store and the issue.
- **Gates:** `CLAUDE.md` → Commands, coverage ≥ 95%.

## 6. Quality scale

- `action-exceptions`: `done` (the switch raises `ServiceValidationError` / `HomeAssistantError`).
- `repair-issues`: `done`.
- `exception-translations`: stays `todo`, with a comment: the switch's exceptions are translated; the
  coordinator's `UpdateFailed` and `ConfigEntryError` texts aren't yet.

## 7. User docs and changelog

- `docs/user/nortec_go.md`:
  - *Supported functionality → Charger*: *Charge* (switch) and *Charge status* (sensor, its values).
  - *Use cases → EV Smart Charging*: *Charger control entity*: *Charge*; *Charging state entity*:
    *Charging*, or leave it empty. Not the *Charge* switch: it stays on while paused and right after a
    start, so EVSC's retry wouldn't fire when it should. Keep *Continuous charging preferred* on: after a
    stop the charger needs an unplug and replug before it can start again.
  - *Starting a charge*, a new section: each start can place a card hold; starts are never retried; a start
    that may have left a hold blocks further starts, and how to clear it (unplug the cable, or the repair
    issue); a pending start shows as on for up to 10 minutes; after a stop, unplug and replug before the
    next start.
  - *Data updates*: every 5 minutes while a start is pending.
  - *Troubleshooting*: "Starts are blocked" points to *Starting a charge*.
  - *Known limitations*: an unplug and replug between two reads (up to 15 minutes apart while connected)
    can't be seen, so use the repair issue; a hold that led to no charge is expected to expire within about
    7 days and can't be cancelled from Home Assistant; after a stop the charger needs a replug before the
    next start, so EVSC plans with more than one session need one too; EVSC logs our start errors as its own
    failed action; no live power reading.
- `CHANGELOG.md`, *Unreleased → Added*: the *Charge* switch, the *Charge status* sensor and the start guard.

## 8. Decisions log

- **D26: Start guard.** A start that may have left a card hold (a `ChargeStartError` with
  `hold_may_be_placed`, a cancelled start, or a start whose charge isn't seen within 10 minutes) blocks
  further starts until the cable is seen unplugged, a charge is seen open, or the owner confirms in the
  repair issue. The block is stored, so reload and restart don't clear it. While a start is pending the
  charger is read every 5 minutes (extending D22). *Why:* EVSC repeats "on" up to 8 times an hour, and each
  start can place a new hold; a human looks before the next one. Source: this spec, *Decisions* and §3.

## 9. Verification

- The gates pass locally and in CI.
- The owner's manual test with `scripts/develop`, **only with the owner's explicit OK**: one start and one
  stop with the switch; the status follows; EVSC accepts *Charge* as its charger control entity.
