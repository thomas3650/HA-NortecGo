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
rest overnight and reviews them in the PR.

| Topic | Decision |
|---|---|
| Switch state | On while a charge is open and not ending: `charge_state` is `STARTING`, `CHARGING` or `PAUSED`; also while our own start is pending (§3.2). Off otherwise, including `STOPPING` |
| Guard | After a start that may have left a card hold, starts are blocked until the cable has been unplugged, or the owner confirms in the repair issue. Reload and restart don't clear it (it is stored) |
| Clearing | A read that sees the cable unplugged, a charger that goes from `BUSY_NON_RELEASED` to `AVAILABLE`, a read that sees a charge open, or the repair issue's fix flow |
| Status sensor | An enum sensor, *Charge status*, including `start_blocked` |
| EVSC's repeated "on" | A no-op while a charge is open or our start is pending (§3.1). EVSC calls `turn_on` without checking the switch |
| Pending start | *Controller.* After a successful `start_charge()` the start is pending until a read sees the charge open. If no read within 10 minutes sees it, the start counts as failed with a hold, and starts are blocked |
| Stop during a pending start | *Controller.* Remembered; the first read that sees the charge open stops it once |
| Power sensor | Out of scope: the API has no live power field. #24 works it out from delivered energy |

Facts about the charger, from the `NortecGo` session (2026-09-26), public-safe. "Observed" means seen in
real traffic:

- `start_charge()` raises its pre-check errors (`ChargeAlreadyActiveError`, `CableNotConnectedError`,
  `ChargerNotReleasedError`, card and car errors) before any payment request: no hold.
- After a finished charge with the cable left in, the charger stays `BUSY_NON_RELEASED` (observed for
  10.5 h) and turns `AVAILABLE` only when the cable is unplugged. It stays `AVAILABLE` after the replug.
  So `BUSY_NON_RELEASED` followed by `AVAILABLE` means an unplug happened, even if no read saw it.
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
  EVSC calls `turn_on` again at minutes 5, 10, 20, 25, 35, 40, 50 and 55.

## 1. Files

| File | Change |
|---|---|
| `custom_components/nortec_go/charge_control.py` | New. `ChargeControl`: the start and stop calls, the pending start, the block, its `Store` and the repair issue (§3). No entity code |
| `custom_components/nortec_go/coordinator.py` | Owns a `ChargeControl`; passes each charger read to it (§3.4); 5-minute interval while a start is pending |
| `custom_components/nortec_go/switch.py` | New. The *Charge* switch (§2.1) |
| `custom_components/nortec_go/sensor.py` | The *Charge status* sensor (§2.2) |
| `custom_components/nortec_go/repairs.py` | New. The fix flow for the start block (§3.5) |
| `custom_components/nortec_go/__init__.py` | `Platform.SWITCH`; load the control's stored state at setup; `async_remove_entry` also removes it |
| `custom_components/nortec_go/const.py` | `START_CONFIRM_TIMEOUT`, the control's store key and version, the repair issue ID format |
| `custom_components/nortec_go/strings.json`, `translations/en.json` | Entity names, the status options, `exceptions`, the repair issue and its fix flow |
| `custom_components/nortec_go/manifest.json` | `repairs` in `dependencies` only if hassfest requires it for the fix flow |
| `custom_components/nortec_go/quality_scale.yaml` | §6 |
| `tests/…` | §5 |
| `docs/user/nortec_go.md`, `CHANGELOG.md` | §7 |
| `docs/decisions.md` | §8 |

## 2. Entities

### 2.1 Charge switch

- Charger device, key `charge` (named *Charge*, apart from the *Charging* binary sensor), no device class
  (`switch`), `PARALLEL_UPDATES = 1`.
- **`is_on`:** `ChargeControl.is_charge_on(charger)`: true when a start is pending and no stop was asked for,
  or `charge_state` is `STARTING`, `CHARGING` or `PAUSED`.
- **`turn_on`** → `ChargeControl.async_start()`, **`turn_off`** → `ChargeControl.async_stop()` (§3). After
  either, the switch writes its state (the pending start shows as on at once).
- Available when the coordinator's last update succeeded, like the other charger entities.

### 2.2 Charge status sensor

Charger device, key `charge_status`, device class `enum`, translated options. The first matching row wins:

| Option | When |
|---|---|
| `start_blocked` | the block is set |
| `starting` | a start is pending and the read shows no charge yet |
| `unknown` | `Charger.state` or `charge_state` is `UNKNOWN` |
| `starting`, `charging`, `paused`, `stopping` | `charge_state` |
| `not_released` | `Charger.state` is `BUSY_NON_RELEASED` |
| `unplugged` | not `is_connected` |
| `idle` | otherwise |

- `charge_state` `COMPLETED` (not seen on the charger) shows as `idle`.

## 3. Charge control

`ChargeControl` lives in `charge_control.py`, one per entry, owned by the coordinator. It holds the pending
start, the "stop wanted" flag, the block and the last seen `Charger.state`, and an `asyncio.Lock` so a start
and a stop never run at the same time.

"A charge is open" in a read means `charge_state is not None` or `Charger.state` is `BUSY` or
`BUSY_CHARGING` (the same test `pynortecgo` uses for `ChargeAlreadyActiveError`).

### 3.1 Start

In order:

1. **Start already under way:** if the lock is held by a start, return (EVSC's repeated "on"). A stop in
   flight is waited for.
2. **Nothing to do:** if a start is pending, or the last read shows a charge open, return. No API call.
3. **Blocked:** raise `ServiceValidationError`, `start_blocked`.
4. **Unknown charger:** if the last read's `Charger.state` is `UNKNOWN`, raise `ServiceValidationError`,
   `charger_state_unknown`.
5. **`await client.start_charge()`**, once. Never retried, by us or by HA.
6. **Success:** set the pending start (its time), save it, and ask the coordinator for a read
   (`async_request_refresh`).

Errors, all with translated messages (`translation_domain=DOMAIN`):

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
- Logs name the error class and `str(err)` only (`pynortecgo`'s texts hold no private data).

### 3.2 Pending start

- Set on success, with the time; saved in the store so a restart keeps it.
- While pending: the switch is on, the status is `starting` (until the read shows the charge), `turn_on` is
  a no-op, and the coordinator reads every 5 minutes.
- **Ends** when a read sees a charge open (normal), or on `turn_off`'s stop.
- **Times out** when a read at least `START_CONFIRM_TIMEOUT` (10 min) after the start still sees no charge
  open: the start counts as failed with a hold. The block is set, and a warning is logged.

### 3.3 Stop

1. Take the lock (a start in flight finishes first).
2. **Pending start, no charge seen yet:** clear the pending start, set "stop wanted", save, ask for a read,
   return. The first read that sees the charge open calls `stop_charge()` once (§3.4).
3. **`await client.stop_charge()`**, once. Then ask for a read.

| Error | Result |
|---|---|
| `NoActiveChargeError` | none: nothing to stop; ask for a read |
| `ChargeNotStoppableError` | `HomeAssistantError` `charge_not_stoppable` |
| `AuthError` | start reauth; `HomeAssistantError` `auth_failed` |
| other `NortecGoError` | `HomeAssistantError` `stop_failed`; ask for a read (the stop may have happened) |

### 3.4 Each charger read

The coordinator calls `ChargeControl.async_on_charger_read(charger)` after every successful charger read,
before it sets the interval. In order:

1. **Clear the block** if the cable isn't connected, or the last seen state was `BUSY_NON_RELEASED` and this
   one is `AVAILABLE`, or a charge is open.
2. **Pending start:** ends if a charge is open; times out as in §3.2.
3. **Stop wanted:** if a charge is open, clear the flag and call `stop_charge()` once, as a background task
   (`entry.async_create_background_task`) with §3.3's error handling, logged instead of raised. If the cable
   isn't connected, clear the flag.
4. Remember `Charger.state`; save if anything changed.

The interval (D22) is 5 minutes while a start is pending, otherwise unchanged.

### 3.5 Block, store and repair issue

- **Store:** `helpers.storage.Store`, version 1, key `nortec_go.<entry_id>.charge_control`:
  `{"blocked_since": ISO 8601 UTC | null, "start_pending_since": ISO 8601 UTC | null, "stop_wanted": bool}`.
  No IDs. Loaded at setup before the first refresh; a missing file or a wrong shape (logged at warning) gives
  the empty state. Removed by `async_remove_entry`.
- **Setting the block** saves it, logs a warning, and creates the repair issue.
- **Repair issue:** `ir.async_create_issue`, ID `start_blocked_<entry_id>`, `is_fixable=True`,
  `is_persistent=False`, severity `error`, translated, with the charger name as the only placeholder. The
  text: a start failed after a card hold may have been placed; starts are blocked so no new hold is placed;
  a hold that led to no charge is expected to expire by itself; check the charger in the Nortec Go app, then
  unplug and replug the cable, or confirm here.
- **At setup** a stored block recreates the issue.
- **Fix flow** (`repairs.py`, `async_create_fix_flow`): one confirm step. On confirm, if the entry is loaded,
  clear the block; otherwise abort with `not_loaded`.
- **Clearing the block** by any path saves, deletes the issue, logs an info line and updates the entities.

## 4. Errors and availability

- Every exception the switch raises is translated (`strings.json` → `exceptions`).
- The coordinator's read error handling is unchanged
  ([read-only entities spec](2026-09-26-read-only-entities-design.md) §4.2); the switch starts reauth itself
  (`entry.async_start_reauth`) on an `AuthError` from its own calls.
- The status sensor and switch are unavailable when the last update failed, like the other charger entities.

## 5. Tests

TDD; `pynortecgo` always mocked; fixtures built from `pynortecgo` model objects (hard rule 7). `make_charger`
gains a `state` argument. No test reaches the real API.

- **`test_charge_control.py`:** every row of §3.1 and §3.3 (errors, block or not, reauth, read asked for);
  the start in flight ignored; pending start no-op, timeout sets the block, a charge seen ends it; stop during
  a pending start, then the stop when the charge appears; each clearing path of §3.4; store round-trip,
  restart keeps the block and the pending start, a wrong-shape file; the repair issue created, recreated at
  setup and deleted; `start_charge` called exactly once in every path (never retried).
- **`test_switch.py`:** state for each charge state, on while pending, `turn_on`/`turn_off` through the HA
  service, translated error messages, unavailable after a failed update.
- **`test_sensor.py`:** every row of §2.2.
- **`test_repairs.py`:** the fix flow clears the block and deletes the issue; aborts when the entry isn't
  loaded.
- **`test_coordinator.py`, `test_init.py`:** the interval while pending; the control's read hook; removal
  removes the store.
- **Gates:** `CLAUDE.md` → Commands, coverage ≥ 95%.

## 6. Quality scale

- `action-exceptions`: `done` (the switch raises `ServiceValidationError` / `HomeAssistantError`).
- `repair-issues`: `done`.
- `exception-translations`: stays `todo`, with a comment: the switch's exceptions are translated; the
  coordinator's `UpdateFailed` and `ConfigEntryError` texts aren't yet.

## 7. User docs and changelog

- `docs/user/nortec_go.md`:
  - *Supported functionality → Charger*: *Charge* (switch) and *Charge status* (sensor, its values).
  - *Use cases → EV Smart Charging*: *Charger control entity*: *Charge*; *Charging state entity*: *Charging*,
    or leave it empty. Not the *Charge* switch: it stays on while paused and right after a start, so EVSC's
    retry wouldn't fire when it should.
  - *Starting a charge*, a new section: each start can place a card hold; starts are never retried; a start
    that may have left a hold blocks further starts, and how to clear it (unplug the cable, or the repair
    issue); a pending start shows as on for up to 10 minutes.
  - *Known limitations*: a quick unplug and replug between reads can't be seen, so use the repair issue; a
    hold that led to no charge is expected to expire within about 7 days and can't be cancelled from Home
    Assistant; EVSC logs our start errors as its own failed action; no live power reading.
- `CHANGELOG.md`, *Unreleased → Added*: the *Charge* switch, the *Charge status* sensor and the start guard.

## 8. Decisions log

- **D26: Start guard.** A start that may have left a card hold (a `ChargeStartError` with
  `hold_may_be_placed`, a cancelled start, or a start whose charge isn't seen within 10 minutes) blocks
  further starts until the cable is seen unplugged, a charge is seen open, or the owner confirms in the
  repair issue. The block is stored, so reload and restart don't clear it. *Why:* EVSC repeats "on" up to 8
  times an hour, and each start can place a new hold; a human looks before the next one. Source: this spec,
  *Decisions* and §3.

## 9. Verification

- The gates pass locally and in CI.
- The owner's manual test with `scripts/develop`, **only with the owner's explicit OK**: one start and one
  stop with the switch; the status follows; EVSC accepts *Charge* as its charger control entity.
