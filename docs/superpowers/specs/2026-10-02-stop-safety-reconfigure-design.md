# A stop that holds, start guard hardening, and reconfigure — design

Date: 2026-10-02 · Branch: `feat/stop-safety-reconfigure` · Issues: #85, #32, #26, #44

## Goal

- **What:** four issues in one PR.
  - Turning *Charge* off means "off until the charge is seen off". The stop is stored until then, sent again
    when it fails, and ends in a repair issue when it can't be done (D50). This closes #85, #32 and the
    reload point of #26.
  - The start guard fails safe in the three other cases #26 lists: a corrupt store file, a block whose
    reason is lost at a restart, and an unexpected exception from a start's pre-check.
  - A reconfigure step changes the account's sign-in without removing the integration (#44).
- **Why:**
  - Today a stop asked for during a pending start lives only as long as that pending start. Everything that
    ends the pending start drops the stop, sent or not: the start deadline (#85, case 2), a read that sees
    the charge open followed by a failed setup (#85, case 1) or a reload (#26), and a charger that refuses
    the stop (#32). The car then keeps charging, and with EV Smart Charging nobody is there to see it.
  - The four issues are done together because three of them share this one cause and one file, and one
    spec, one review and one release cost less than four. #44 touches other files and rides along.
- **Not in this work:**
  - The start. It is still sent once and never retried (hard rule 6), and the start guard's rules (D26)
    don't change, apart from the three hardening points in §2.
  - The start deadline. #85 suggested holding it until the first read has reached the charge control. With
    the stop stored on its own, the deadline no longer loses the stop, so it stays as it is (§1, *The start
    deadline*).
  - The setup order (D44). The stop survives a failed setup because it is stored until it is done.
  - An options flow, and any setting for the limits in §1.
- **Closes:** #85, #32, #26 and #44, each with its own `Closes #n` line in the PR description.
- **Done when:** the cases in §1 to §5 hold in tests with `pynortecgo` mocked, the docs in §8 are updated,
  D50 is in `decisions.md`, `reconfiguration-flow` is `done`, and the gates pass.

## Decisions

Answered by the owner in the brainstorm on 2026-10-02.

| Topic | Decision |
|---|---|
| A stop that can't be done at once | It is stored and tried again; when that fails too, a repair issue tells the owner |
| When a try has failed | Judged by the result: the call failed, or the charger accepted it and the charge is still on 2 minutes later |
| How many tries | At most 10 `stop_charge()` calls for one stop asked |
| How long | At most 30 minutes from when the stop was asked, also across a restart |
| Whichever limit comes first | The control gives up: an error in the log, the repair issue, and the switch shows the charger's state again |
| A charge that is stopping | No stop is sent to it, and seeing it ends the stored stop |
| The log | A warning for every failed try, with its number; an error when the control gives up |
| Which turn-offs | Every one, not only those asked during a pending start |
| #26, corrupt store file | Fix: starts are blocked to be safe |
| #26, block reason | Fix: stored with the block |
| #26, stop lost across a reload | Fixed by the stored stop |
| #26, unexpected pre-check exception | Fix: translated to "start failed", no block |
| #44 | Done here, as the issue describes it |
| Release level | Releasing: the title is `feat: …`, with a CHANGELOG entry and the bump step |

Facts used, from the installed Home Assistant source and `pynortecgo` 0.8.0's public models:

- A read's open charge says whether it can be stopped (`can_stop`). It has no start time, so the control
  can't tell the charge its own start made from a later one. The stop's age is the only guard against
  stopping the wrong charge.
- `Store.async_load` renames a file with a JSON decode error, raises Home Assistant's own
  `storage_corruption` repair issue, and returns `None`, the same as for a missing file. `Store.path` is
  the file's path.
- A `Store` has a minor version. A stored minor version other than the code's goes through
  `_async_migrate_func`, and the migrated data is saved straight back. Code without a migrate function
  that meets a newer minor version of the same major version loads the data unchanged.
- An entry's background tasks are cancelled when its setup fails and when it unloads.
- `ConfirmRepairFlow` is Home Assistant's fix flow with one confirm step and no side effect. Finishing a
  fix flow deletes the issue.
- A config flow's `reconfigure` step is offered on the integration's page. `_get_reconfigure_entry()` gives
  the entry, and `async_update_reload_and_abort` aborts with `reconfigure_successful` from that step.

## 1. The stored stop

All of this is in `charge_control.py`, except the read interval (*What the owner sees*).

### State

- `stop_asked_since`, a time, replaces the `stop_asked` flag. It is stored, and it no longer depends on the
  pending start: ending the pending start leaves it alone.
- The number of tries is kept in memory only. A restart or reload starts it at zero; the 30 minutes, which
  are stored, bound that.
- `ChargeControlState.stop_asked` stays a flag for the entities and the coordinator: true while a stop is
  stored.
- The pending stop (D29: the 2 minutes after an accepted stop) is unchanged and still not stored. It now
  exists only while a stop is stored.

In this section:
- **open** is the existing `charge_is_open`;
- **stoppable** is an open charge that the read says can be stopped (`can_stop`) and that isn't `STOPPING`;
- a **stale read** is one begun before the latest start attempt (the existing `start_attempts` check).

### Turning *Charge* off

In this order, under the lock:

1. The control is closed (unloading): the translated `unloading` error, as today.
2. The repair issue of §4 is deleted: this is a new ask.
3. A pending stop is under way, or the last read shows the charge `STOPPING`: nothing, as today.
4. A start is pending and the last read shows no charge open: the stop is stored and a read is requested,
   as today.
5. The last read shows a charge that is open and not stoppable: the stop is stored and a read is
   requested. No call is made.
6. Otherwise the stop is stored and `stop_charge()` is called now (a try, see below). As today, this also
   covers a last read that shows no charge, or no read yet: the read may be old.

Storing a stop that is already stored changes nothing: its time and its count of tries stay. So an
automation that repeats the turn-off can't keep a failing stop alive past the limits.

### A try

A try is one `stop_charge()` call, from a turn-off (step 6) or from a read (below). Its outcomes:

| The call | What happens |
|---|---|
| Accepted | The pending stop starts (D29). The stop stays stored. If a read shows the charge `STOPPING` or not open within the 2 minutes, the stop is done. If the 2 minutes pass first, the try has failed |
| `NoActiveChargeError` | The stop is done: there is nothing to stop |
| `ChargeNotStoppableError`, or any other `NortecGoError` | The try has failed. The stop stays stored. A read is requested |
| `AuthError` | The try has failed and the stop stays stored. Reauth starts at once, and a turn-off raises the translated `auth_failed` error, as today |
| Cancelled (a failed setup, an unload) | Not counted. The stop stays stored |

- A failed try logs a warning with its number ("try 3 of 10") and the error's type and text. Credentials
  are never part of it (hard rule 5).
- After the 10th failed try the control gives up (below).
- A turn-off no longer raises `charge_not_stoppable` or `stop_failed`: the stop is tried again instead, and
  the owner hears of it only if it can't be done. The two translations are removed (§6).
- Sending a stop twice is harmless: a charge that is already stopping or closed answers
  `NoActiveChargeError` or refuses, and a stop places no card hold.

### On a read

`on_charger_read` keeps its order: the pending stop first, then the stale-read check, then the pending
start, then the block. The stored stop is handled after the pending start:

- **A start is still pending:** the stop waits. A read that sees a charge happened or the cable unplugged
  ends the pending start as today, and the next two points then apply to the same read.
- **The read shows the charge `STOPPING` or not open:** the stop is done. A stale read doesn't count here:
  it can't know what the latest start led to.
- **The read shows the charge stoppable, and no pending stop is under way:** a try is made, as a background
  task under the lock, as today. A stale read may do this: its evidence is the charge it saw. One try runs
  at a time, and the task checks again under the lock that the stop is still stored and the control is
  open.
- **Otherwise** (open but not stoppable, or a pending stop under way): the stop waits.

A done stop is cleared and saved, its timers are cancelled, and the repair issue of §4 is deleted.

### Turning *Charge* on

- While a pending stop is under way, the turn-on is refused with `stop_pending`, as today.
- Every other turn-on clears a stored stop first and deletes the repair issue of §4, whatever the start
  then does (today it clears the stop only while a start is pending). The owner has asked for a charge.

### The limits

- **10 tries:** counted as above.
- **30 minutes:** a timer set when the stop is stored, which fires whether or not the charger is read, as
  D31 requires of the start and stop deadlines.
  - At load, the timer is set for what is left of the 30 minutes. A stop that is already past them gives
    up at once.
  - There is no grace at load, unlike the start's. A stop from before a long outage can't be trusted to
    belong to the charge that is open now, and the owner is told instead.
- **Giving up:** the stored stop and a pending stop are cleared and saved, an error is logged, and the
  repair issue of §4 is raised. The switch then shows the charger's state again.

### The start deadline

Unchanged: after 10 minutes, or at least 2 minutes after a load (`START_LOAD_GRACE`), a pending start
whose charge wasn't seen ends with a block (D26, D31). It no longer clears the stop.

A deadline that fires at a slow setup, before the first read, can still set a block for a charge that did
open. That block clears on the first read that sees the charge open, as D26 says, and the stop is then
sent.

### What the owner sees

- **The switch** shows off while a stop is stored, as today's `is_charge_on` already does.
- ***Charge status*** is unchanged in code: *Stopping* while a start is pending and no charge is open, and
  while a pending stop is under way. Between tries it shows the charge's own state (*Starting*, *Charging*,
  *Paused*).
- **The reads:** `interval_for` treats a stored stop like the charger's own starting and stopping states:
  30 s while a start or a stop is pending or the last good read is under 2 minutes old
  (`FAST_READ_MAX_AGE`), 5 minutes after that. So a stored stop is tried within 30 s of the charge becoming
  stoppable, and an outage doesn't read every 30 s (D31).

### The cases this closes

| Case | Today | With this |
|---|---|---|
| #85, case 1: the setup fails after the stop is queued | The stop is cleared and saved, then its task is cancelled | The stop is still stored; the next setup's read sends it |
| #85, case 2: the deadline fires before the first read | The stop is cleared and saved | The stop outlives the deadline; the first read sends it or ends it |
| #32: the charger refuses the stop | A warning in the log | Tried again when the charge is stoppable; the repair issue after 10 tries or 30 minutes |
| #26: a reload between the read and the stop | The stop is skipped | `async_shutdown` saves the stop, and the reloaded control sends it |

## 2. Start guard hardening (#26)

- **A corrupt store file.** `async_load` checks, before it loads, whether the store's file exists. A file
  that existed and loaded as nothing was corrupt (or empty), and the control can't know what it held: it
  blocks starts with the existing `start_blocked_store` issue and saves, as it does today for a wrong
  shape. A missing file is still a first setup.
- **The block's reason.** It is stored with the block, as the issue's translation key (`start_blocked` or
  `start_blocked_store`). `async_load` raises the issue again with the stored reason. A stored reason that
  is neither of the two is a wrong shape.
- **An unexpected exception from a start.** Anything `start_charge()` raises that isn't a `NortecGoError`
  (and isn't a cancellation, which keeps its block) is logged with its traceback and raised as the
  translated `start_failed` error, with no block. The client wraps everything after the payment request in
  `ChargeStartError`, so no card hold can be behind it.

## 3. The stored format

The charge control's store keeps version 1 and gets minor version 2, with a migrate function.

| Key | Minor 1 | Minor 2 |
|---|---|---|
| `blocked_since` | A time or null | The same |
| `block_reason` | Not there | The issue key, or null without a block |
| `start_pending_since` | A time or null | The same |
| `stop_asked` | A flag | Gone |
| `stop_asked_since` | Not there | A time or null |

- **Migration from minor 1:**
  - A set `stop_asked` flag becomes `stop_asked_since` with the pending start's time: the flag was only
    ever set during a pending start. That time is earlier than the real one, so the stop only expires
    sooner.
  - A block gets the reason `start_blocked`: the text every stored block had after a restart until now.
  - Data that doesn't have the old shape is passed on unchanged, so `async_load`'s shape check blocks
    starts, as today. The migration itself never fails a setup.
- **A newer minor version** than the code knows is passed on unchanged too.
- **A downgrade** to a release before this one loads the new data unchanged, misses `stop_asked`, and
  blocks starts to be safe, with the "couldn't be read" issue. The owner clears it there. Nothing is done
  to avoid this.

## 4. The repair issue

- **ID and key:** its own issue per entry, `stop_failed_<entry id>`, with the translation key
  `stop_failed`. Severity error, not persistent across a Home Assistant restart (after one, the switch
  shows the charger's state anyway).
- **Raised** when the control gives up (§1, *The limits*).
- **Fix flow:** Home Assistant's `ConfirmRepairFlow`: one confirm step that dismisses the notice and does
  nothing else. `async_create_fix_flow` in `repairs.py` picks it by the issue ID.
- **Deleted without the owner** when a read that isn't stale shows the charge `STOPPING` or not open, when
  *Charge* is turned on or off, and when the entry is removed. Deleting an issue that isn't there does
  nothing, so the control doesn't keep track of whether it is up.

## 5. Reconfigure (#44)

A `reconfigure` step in `config_flow.py`:

- It shows the user step's form (email and password), with the entry's current email filled in, and after
  a failed try the email just typed.
- It signs in once with `_async_sign_in`, never retried, with a client that has the entry's stored device
  ID, as reauth does. An error shows on the form with the user step's error texts.
- A charger other than the entry's aborts with `wrong_account`, as reauth does
  (`_abort_if_unique_id_mismatch`).
- On success the entry gets the new email and tokens and is reloaded (`async_update_reload_and_abort`); the
  flow ends with `reconfigure_successful`.
- The entry's title, device ID and unique ID don't change. The email and password are never logged.

A reload while a stop is stored is covered by §1: the stop is saved at unload and loaded again.

## 6. Texts

In `strings.json` and `translations/en.json`:

- **Added, `config.step.reconfigure`:** a title ("Change the Nortec Go sign-in"), a description saying the
  account must be the one with the same charger, and the user step's field labels and descriptions.
- **Added, `config.abort.reconfigure_successful`:** "The sign-in was changed."
- **Added, `issues.stop_failed`:** a title ("A charge stop on {name} couldn't be confirmed") and a confirm
  step whose description says that *Charge* was turned off, that Home Assistant couldn't stop the charge or
  see it stop and has stopped trying, that the charge may still be running, to check the charger in the
  Nortec Go app, and that turning *Charge* off again makes Home Assistant try again.
- **Removed, `exceptions.charge_not_stoppable` and `exceptions.stop_failed`:** nothing raises them any
  more.

The exact wording is settled in the plan.

## 7. Code

| File | Change |
|---|---|
| `charge_control.py` | §1 to §3, and raising and deleting the issue of §4. `async_remove_charge_control` deletes that issue too |
| `const.py` | The two limits, the store's minor version, the new issue ID; the `START_LOAD_GRACE` comment no longer names #85 |
| `coordinator.py` | `interval_for` (§1, *What the owner sees*); the comment on the setup's car read, which describes the stop being forgotten |
| `repairs.py` | The fix flow for the new issue (§4) |
| `config_flow.py` | The reconfigure step (§5) |
| `strings.json`, `translations/en.json` | §6 |
| `quality_scale.yaml` | §8 |

`switch.py` and `__init__.py` don't change. `diagnostics.py` doesn't either: it gives the control's state
as it is.

`charge_control.py` is 595 lines today and grows with this. The store's shape, its parsing and its
migration move to a module of their own, `charge_control_store.py`, which the control uses through a
small interface: load (with the corrupt-file check) and save of one stored-state object. That keeps the
control to the rules, and lets the format be tested without a control.

## 8. Docs, the quality scale and D50

- **`docs/user/nortec_go.md`:**
  - *Starting a charge*: what turning *Charge* off now does (tried again for up to 10 tries or 30 minutes,
    the switch off meanwhile, then the repair issue), in place of the 2-minute paragraph's end.
  - *Data updates*: the 30-second reads also run while a stop waits.
  - *Troubleshooting*: the new repair issue, and what to do. A corrupt saved start guard blocks starts.
  - A reconfigure section next to *Asked to sign in again*.
  - *Known limitations*: a stop asked more than 30 minutes before Home Assistant comes back is not sent.
- **`CHANGELOG.md`**, under *Unreleased*: *Added* (reconfigure), *Changed* (a turn-off is tried again and
  ends in a repair issue instead of an error), *Fixed* (the lost stops of #85, #32 and #26; the corrupt
  store; the block's text after a restart).
- **`quality_scale.yaml`:** `reconfiguration-flow` becomes `done`, without a comment. The
  `action-exceptions` comment says that a turn-off that fails is tried again and ends in a repair issue
  (D50), and that the other actions raise translated errors.
- **`docs/ha-notes.md`:** what the work teaches about `Store` (the corrupt file, the minor version), if it
  isn't there yet; decided in the learnings step.
- **`docs/decisions.md`:** D50 below, and D29's status becomes `active; the 30 s reads while the charger
  can't be read superseded by D31; what follows the 2 minutes superseded by D50`. D26 and D31 stand as
  they are: the stop asked for during a pending start was never part of their text.

### D50: A stop is stored until the charge is seen off

- **Date:** 2026-10-02 · **Status:** active
- **Decision:** Turning *Charge* off stores the stop until a read shows the charge stopping or not open, or
  *Charge* is turned on. Meanwhile the stop is sent when a read shows the charge stoppable, never to a
  charge that is stopping; a try fails when the call fails or when the charge is still on 2 minutes after
  the charger accepted it. After 10 tries or 30 minutes from the ask, whichever is first, the control gives
  up, logs an error and raises a repair issue. The charger is read every 30 s while a stop is stored,
  within D31's limits. A start is still never retried.
- **Why:** A stop tied to the pending start was lost whenever that ended first (#85, #32, #26), and an
  unattended stop from EV Smart Charging must actually stop the car. A charge has no start time, so the
  stop's age is the only guard against stopping a later charge.
- **Source:** this spec, Decisions and §1.

## 9. Tests

`pynortecgo` is mocked, and fixtures are built from its model objects (hard rule 7). No test starts or
stops a real charge.

- **The stored stop** (`test_charge_control.py`, `test_init.py`):
  - one test per row of *The cases this closes*; for #85 that is a setup whose price read is rejected
    after the stop was queued, and a setup try that is slow, lets the deadline fire, and then fails, each
    followed by a setup that sends the stop;
  - each row of the try table, with the warning and its number;
  - every step of *Turning Charge off*, including a repeated turn-off that keeps the time and the count;
  - every branch of *On a read*, including a stale read that may send but not end;
  - turning *Charge* on with a stop stored, on each path;
  - the 10th failed try, and the 30 minutes with and without reads, at load with time left and at load
    past the limit: the error, the issue, the switch's state;
  - no call is ever made to a charge that is `STOPPING` or not stoppable;
  - no test expects a second `start_charge()` call.
- **The read interval** (`test_coordinator.py`): a stored stop gives 30 s reads, and 5 minutes once the
  last good read is 2 minutes old.
- **Hardening** (`test_charge_control.py`): a corrupt file blocks, a missing file doesn't; the reason
  survives a reload for both keys; an unexpected exception from a start is translated and sets no block.
- **The stored format:** minor 1 data with and without the flag and a block, data of a wrong shape, and
  data of a newer minor version.
- **The repair issue** (`test_repairs.py`): the confirm flow dismisses it; each way it is deleted without
  the owner; it goes with the entry.
- **Reconfigure** (`test_config_flow.py`): success with a new email, each sign-in error and the recovery
  from it, another charger, one login call per submit, and that the device ID is the stored one.
- **Texts and scale:** the existing checks on `strings.json` against `translations/en.json` and on
  `quality_scale.yaml` (`test_quality_scale.py`) are updated.
