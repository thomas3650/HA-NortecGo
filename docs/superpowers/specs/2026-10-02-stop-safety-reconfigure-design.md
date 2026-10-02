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
  - Tying a stop to one charge by the charge's ID (Decisions, *Which charge*).
  - An options flow, and any setting for the limits in §1.
- **Closes:** #85, #32, #26 and #44, each with its own `Closes #n` line in the PR description.
- **Done when:** the cases in §1 to §5 hold in tests with `pynortecgo` mocked, the docs in §8 are updated,
  D50 is in `decisions.md`, `reconfiguration-flow` is `done`, and the gates pass.

## Decisions

Answered by the owner on 2026-10-02, in the brainstorm and in the questions the spec review raised.

| Topic | Decision |
|---|---|
| A stop that can't be done at once | It is stored and tried again; when that fails too, a repair issue tells the owner |
| When a try has failed | Judged by the result: the call failed, or the charger accepted it and the charge is still on 2 minutes later |
| How many tries | At most 10 `stop_charge()` calls for one stop asked; the count is stored with the stop |
| Between calls | At least 2 minutes from one `stop_charge()` call's answer to the next call, whatever the outcome, also across a restart and from one stop asked to the next |
| How long | At most 30 minutes from when the stop was asked, also across a restart |
| Whichever limit comes first | The control gives up: an error in the log, the repair issue, and the switch shows the charger's state again |
| A charge that is stopping | No stop is sent to it, and seeing it ends the stored stop |
| The log | A warning for every failed try, with its number; an error when the control gives up |
| Which turn-offs | Every one, not only those asked during a pending start. A turn-off whose call fails raises no error, except a rejected session |
| Which charge | The stop is not tied to one charge; its age is the guard (below) |
| The notice after giving up | It stays until the charge is seen off, *Charge* is turned on, or the owner dismisses it; a new turn-off doesn't remove it |
| A store that can't be read | A stop held in it is lost; the notice about the store says so |
| #26, corrupt store file | Fix: starts are blocked to be safe |
| #26, block reason | Fix: stored with the block |
| #26, stop lost across a reload | Fixed by the stored stop |
| #26, unexpected pre-check exception | Fix: translated to "start failed", no block |
| #44 | Done here, as the issue describes it |
| Release level | Releasing: the title is `feat: …`, with a CHANGELOG entry and the bump step |

**Which charge.** A read's open charge has an ID, and a start returns its charge's ID, so the control
could store which charge a stop was asked for and send it only to that one. It doesn't. A stored stop is
sent to whatever charge is open and stoppable, and the 30 minutes bound how old it can be. Stopping a
charge other than the one meant takes a stop that isn't done, a first charge that ends, and a second one
that starts outside Home Assistant, all inside those 30 minutes. Tying the stop to an ID would add stored
state and rules for the cases where no ID is known (a pending start from before a restart, no good read
yet) to close that.

Facts used, from the installed Home Assistant source and `pynortecgo` 0.8.0's public models:

- A read's open charge says whether it can be stopped (`can_stop`).
- `Store.async_load` renames a file with a JSON decode error, raises Home Assistant's own
  `storage_corruption` repair issue, and returns `None`, the same as for a missing file. `Store.path` is
  the file's path.
- A `Store` has a minor version. A stored minor version other than the code's goes through
  `_async_migrate_func`, and what that returns is saved straight back under the code's own version. Code
  without a migrate function that meets a newer minor version of the same major version loads the data
  unchanged, and saves it back the same way.
- An entry's background tasks are cancelled when its setup fails and when it unloads. At an unload the
  control's `async_shutdown` runs first, so a try in flight finishes.
- `ConfirmRepairFlow` is Home Assistant's fix flow with one confirm step and no side effect. Finishing a
  fix flow deletes the issue.
- A config flow's `reconfigure` step is offered on the integration's page. `_get_reconfigure_entry()` gives
  the entry, and `async_update_reload_and_abort` aborts with `reconfigure_successful` from that step.

## 1. The stored stop

All of this is in `charge_control.py`, except the read interval (*What the owner sees*).

### State

- **`stop_asked_since`**, a time, replaces the `stop_asked` flag. It is stored, and it no longer depends
  on the pending start: ending the pending start leaves it alone.
- **`stop_tries`**, the number of `stop_charge()` calls made for this stop. It is stored with the stop, so
  a restart or a reload doesn't start it again.
- **`stop_tried_at`**, the time of the last `stop_charge()` call: set when the call is made and again when
  it is answered. It is stored, and it belongs to the control, not to one stop: it stays when a stop is
  done, given up or cleared.
- **The wait:** from when a try is queued until 2 minutes after its answer (`STOP_CONFIRM_TIMEOUT`), no
  other try is made, for this stop or a new one. Starting it at the queueing keeps two reads from queueing
  two tries. At load, what is left of the 2 minutes since `stop_tried_at` is waited out, and never more
  than 2 minutes.
- **The pending stop** (D29) is the wait after a try the charger accepted: the switch shows off and
  *Charge status* shows *Stopping*. It is still not stored, and now exists only while a stop is stored.
- `ChargeControlState.stop_asked` stays a flag for the entities and the coordinator: true while a stop is
  stored.

In this section:
- **open** is the existing `charge_is_open`;
- **stoppable** is a read with a charge object that says it can be stopped (`can_stop`) and isn't
  `STOPPING`. An open charger without a charge object, which is seen right after a start, is not
  stoppable. Today's code sends the stop in that state; that is fixed on purpose;
- **off** is a read that shows the charge `STOPPING`, or shows no charge open on a charger whose state is
  known. A charger in an unknown state with no charge object has the stop wait, as it has a start
  refused; with a stoppable charge object it is tried like any other;
- a **stale read** is one begun before the latest start attempt (the existing `start_attempts` check).

### When a try may be made

A try is one `stop_charge()` call. It is made only when all of these hold, checked under the lock right
before the call:

- a stop is stored and the control is open (not unloading);
- no start is pending;
- no wait is running from an earlier try (this try's own wait aside);
- fewer than 10 tries have been made.

### Turning *Charge* off

In this order, under the lock:

1. The control is closed (unloading): the translated `unloading` error, as today.
2. A pending stop is under way, or the last read shows the charge `STOPPING`: nothing more, as today.
3. The stop is stored, unless one already is. A stop that is already stored keeps its time and its count,
   so repeating the turn-off doesn't move that stop's limits.
4. A try is made now when one may be made (above) and the last read doesn't show an open charge that
   isn't stoppable. As today, that includes a last read that shows no charge, and no read yet: the read
   may be old. Otherwise a read is requested and the stop waits for it.

So during a pending start no call is made, whatever the last read shows: the read that sees the charge
ends the pending start and then tries.

A turn-off after the control has given up is a new ask: a new stop with its own 10 tries and 30 minutes,
whose first try waits out what is left of the last call's 2 minutes.
It doesn't delete the repair issue of §4, so an automation that keeps turning *Charge* off can't hide
from the owner that the charge doesn't stop.

### A try's outcome

The try is counted, and the count and the time saved, when the call is made; the time is saved again at
the answer. The 2 minutes run from the call's answer, not from its start: a call can take a while, and an accepted stop is judged 2 minutes after
the charger accepted it.

| The call | What happens |
|---|---|
| Accepted | The pending stop starts, and a read is requested, as today. If a read shows the charge off within the 2 minutes, the stop is done. If the 2 minutes pass first, the try has failed |
| `NoActiveChargeError` | The charger had no charge to stop when the client looked. That doesn't end the stop: the client gives this answer for an open charger without a charge object too. The stop stays stored, a read is requested, and that read decides: off ends the stop, anything else has it wait. No warning; the try is counted like any call |
| `ChargeNotStoppableError`, or any other `NortecGoError` | The try has failed. The stop stays stored, and the wait runs its 2 minutes |
| `AuthError` | The try has failed and the stop stays stored. Reauth starts at once. A turn-off raises the translated `auth_failed` error, as today |
| Cancelled (a failed setup, Home Assistant stopping, a cancelled turn-off call) | The stop stays stored and the try stays counted. The 2 minutes run from when the call was made |

A queued try that ends up making no call, because the check under the lock fails, ends its own wait.

So only a read ends a stop as done: never a call's answer.

A turn-off on an idle charger makes a call too, as today, and so starts the 2 minutes. A stop asked for
a charge that opens inside them waits out the rest. That is intended: the rule is one call per 2 minutes,
whatever the call led to.

- A failed try logs a warning with its number ("try 3 of 10") and what failed: the error's type and text,
  or that the charge was still on after the 2 minutes. Credentials are never part of it (hard rule 5).
- When the 10th try has failed, the control gives up (*The limits*).
- A turn-off no longer raises `charge_not_stoppable` or `stop_failed`: the stop is tried again instead, and
  the owner hears of it only if it can't be done. The two translations are removed (§6).
- Sending a stop twice is harmless: a charge that is already stopping or closed answers
  `NoActiveChargeError` or refuses, and a stop places no card hold.

### On a read

`on_charger_read` keeps the read as the last read, as today, and then:

1. **A stale read changes nothing more.** Today the pending stop is checked before this; it moves after,
   so the stop and its pending stop follow one rule. D26's "reads begun before the latest start attempt
   change nothing" holds for the stop too.
2. **The pending start**, as today: a read that sees a charge happened or the cable unplugged ends it. It
   no longer clears the stop.
3. **The stop:**
   - **The read shows the charge off, and no start is pending:** a stored stop is done, and the repair
     issue of §4 is deleted, whether or not a stop is stored.
   - **A start is still pending:** the stop waits.
   - **The read shows the charge stoppable, and a try may be made:** the wait starts and the try is queued
     as a background task, which checks again under the lock (*When a try may be made*).
   - **Otherwise** (open but not stoppable, or a wait running): the stop waits.
4. **The block**, as today.

A done stop is cleared with its count and its pending stop; the 30-minute timer is cancelled and the
state is saved. The wait runs on, so a stop asked right afterwards waits out what is left of it.

The pending stop today ends on any charge state other than starting, charging and paused. It now ends on
the same evidence as the stop: the charge off. For an open charge in an unknown state, or an open charger
without a charge object, it runs its 2 minutes, and the try has then failed.

### Turning *Charge* on

- While a pending stop is under way, the turn-on is refused with `stop_pending`, as today (D29). With
  stops that are accepted but don't take effect, that refuses a turn-on for 2 minutes at a time until the
  control gives up. That is accepted: the charger has just been told to stop.
- Every other turn-on clears a stored stop first and deletes the repair issue of §4, whatever the start
  then does (today it clears the stop only while a start is pending). The owner has asked for a charge.

### The limits

- **10 tries:** counted as above. A failed call gives up when it was the 10th. Otherwise a stop with 10
  tries made gives up when the wait after the 10th has passed and the stop is still stored: an accepted
  10th try, one answered "no active charge", and a stop that is loaded with 10 tries made (at once, if
  nothing is left of its wait).
- **The wait's timer** fires 2 minutes after the answer whether or not the charger is read. It ends the
  wait, and when the stop it was made for is still stored with its pending stop under way, it ends that
  pending stop and marks the accepted try as failed. It replaces today's stop timer.
- **30 minutes:** a timer set when the stop is stored, which fires whether or not the charger is read, as
  D31 requires of the start and stop deadlines.
  - At load, the timer is set for what is left of the 30 minutes, and never for more than 30 minutes (a
    stored time in the future, after a clock change). A stop that is already past them gives up at once.
  - There is no grace at load, unlike the start's. A stop from before a long outage can't be trusted to
    belong to the charge that is open now, and the owner is told instead.
- **Giving up:** the stop is cleared as a done one is, an error is logged, and the repair issue of §4 is
  raised. The switch then shows the charger's state again.
- **The timers' work** runs under the lock and first checks that it still belongs to the same wait or the
  same stop, as today's timers check their `since`. Both timers are cancelled with the others when a setup
  fails and at unload, so an old control can't clear what a new one has loaded.

Each try waits 2 minutes from its answer, and the next comes with a read up to 30 s later, so 10 tries
take 20 to 25 minutes, inside the 30.

### The start deadline

Unchanged: after 10 minutes, or at least 2 minutes after a load (`START_LOAD_GRACE`), a pending start
whose charge wasn't seen ends with a block (D26, D31). It no longer clears the stop.

A deadline that fires at a slow setup, before the first read, can still set a block for a charge that did
open. That block clears on the first read that sees the charge open, as D26 says, and the stop is then
sent.

### What the owner sees

- **The switch** shows off while a stop is stored, as today's `is_charge_on` already does.
- ***Charge status*** is unchanged in code: *Stopping* while a start is pending and no charge is open, and
  while a pending stop is under way. Otherwise it shows the charge's own state (*Starting*, *Charging*,
  *Paused*), also while a stop waits for its next try.
- **The reads:** `interval_for` treats a stored stop like the charger's own starting and stopping states:
  30 s while a start or a stop is pending or the last good read is under 2 minutes old
  (`FAST_READ_MAX_AGE`), 5 minutes after that. So the first try comes within 30 s of the charge becoming
  stoppable, and an outage doesn't read every 30 s (D31).

### The cases this closes

| Case | Today | With this |
|---|---|---|
| #85, case 1: the setup fails after the stop is queued | The stop is cleared and saved, then its task is cancelled | The stop is still stored; the next setup's read sends it, once what is left of the 2 minutes has passed |
| #85, case 2: the deadline fires before the first read | The stop is cleared and saved | The stop outlives the deadline; the first read sends it or ends it |
| #32: the charger refuses the stop | A warning in the log | Not sent while the read says it can't be stopped; tried again every 2 minutes when a call fails; the repair issue after 10 tries or 30 minutes |
| #26: a reload between the read and the stop | The stop is skipped | `async_shutdown` saves the stop, and the reloaded control sends it |

## 2. Start guard hardening (#26)

- **A corrupt store file.** The load checks, before it loads, whether the store's file exists. A file that
  existed and loaded as nothing was corrupt (or empty), and the control can't know what it held: it
  blocks starts with the existing `start_blocked_store` issue and saves, as it does today for a wrong
  shape. A missing file is still a first setup.
- **A stop in a store that can't be read** (a corrupt file, or a wrong shape) is lost with it: the control
  can't know one was asked. The `start_blocked_store` issue's text gets a sentence saying that a stop
  asked for earlier may not have been sent, next to its advice to check the charger.
- **The block's reason.** It is stored with the block, as the issue's translation key (`start_blocked` or
  `start_blocked_store`). `async_load` raises the issue again with the stored reason.
- **An unexpected exception from a start.** Anything `start_charge()` raises that isn't a `NortecGoError`
  (and isn't a cancellation, which keeps its block) is logged with its traceback and raised as the
  translated `start_failed` error, with no block. The client wraps everything from the first payment
  request on in `ChargeStartError`, so no card hold can be behind it.

## 3. The stored format

The charge control's store keeps version 1 and gets minor version 2, with a migrate function.

| Key | Minor 1 | Minor 2 |
|---|---|---|
| `blocked_since` | A time or null | The same |
| `block_reason` | Not there | The issue key with a block, null without one |
| `start_pending_since` | A time or null | The same |
| `stop_asked` | A flag | Gone |
| `stop_asked_since` | Not there | A time or null |
| `stop_tries` | Not there | A whole number from 0 to 10; 0 without a stop |
| `stop_tried_at` | Not there | A time or null; null until the first stop call |

- **Wrong shapes**, which block starts as today: a missing key, a value of the wrong type, a block with a
  null or unknown reason, a reason without a block, tries above 0 without a stop or without a try's time,
  tries above 10.
- **Migration from minor 1:**
  - A set `stop_asked` flag becomes `stop_asked_since` with the pending start's time: the flag was only
    ever set during a pending start. That time is earlier than the real one, so the stop only expires
    sooner. A flag without a pending start becomes null.
  - `stop_tries` is 0 and `stop_tried_at` is null.
  - A block gets the reason `start_blocked`: the text every stored block had after a restart until now.
  - Data that doesn't have the old shape is passed on unchanged, so the shape check blocks starts, as
    today. The migration itself never fails a setup.
- **A newer minor version** than the code knows is passed on unchanged too.
- **A downgrade** to a release before this one loads the new data unchanged, misses `stop_asked`, and
  blocks starts to be safe, with the "couldn't be read" issue. A stop stored at that moment is lost. The
  owner clears the block there. Nothing is done to avoid this.

## 4. The repair issue

- **ID and key:** its own issue per entry, `stop_failed_<entry id>`, with the translation key
  `stop_failed`. Severity error, and persistent, so it survives a Home Assistant restart while the charge
  may still be running. Nothing about it is stored by the control.
- **Raised** when the control gives up (§1, *The limits*).
- **Fix flow:** Home Assistant's `ConfirmRepairFlow`: one confirm step that dismisses the notice and does
  nothing else. `async_create_fix_flow` in `repairs.py` picks it by the issue ID; today it gives every
  issue that isn't `car_gone` the start block's flow, so confirming this one must not clear a start block.
- **Deleted without the owner** when a read that isn't stale shows the charge off and no start is pending
  (§1, *On a read*), when *Charge* is turned on, and when the entry is removed. A turn-off doesn't delete
  it (§1, *Turning Charge off*). Deleting an issue that isn't there does nothing, so the control doesn't
  keep track of whether it is up.

## 5. Reconfigure (#44)

A `reconfigure` step in `config_flow.py`:

- It shows the user step's form (email and password), with the entry's current email filled in, and after
  a failed try the email just typed. The email is trimmed, as in the user step.
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
- **Changed, `issues.start_blocked_store`:** one more sentence in the description: a stop asked for
  earlier may not have been sent (§2).
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
| `charge_control.py` | §1 and §2, and raising and deleting the issue of §4. `async_remove_charge_control` deletes that issue too |
| `charge_control_store.py` (new) | §3, and the corrupt-file check of §2 |
| `const.py` | The two limits, the store's minor version, the new issue ID; the `START_LOAD_GRACE` comment no longer names #85 |
| `coordinator.py` | `interval_for` (§1, *What the owner sees*); the comment on the setup's car read, which describes the stop being forgotten |
| `repairs.py` | The fix flow for the new issue (§4) |
| `config_flow.py` | The reconfigure step (§5) |
| `strings.json`, `translations/en.json` | §6 |
| `quality_scale.yaml` | §8 |

`switch.py` and `__init__.py` don't change. `diagnostics.py` doesn't either: it gives the control's state
as it is.

**The store module.** `charge_control.py` is 595 lines today and grows with this. The store's shape, its
parsing and its migration move to `charge_control_store.py`, as the prices and the energy ledger have
their stores. The control keeps the rules, and the format can be tested without a control. What the
module gives the control:

- **Load**, with three results the control tells apart: nothing stored (a first setup), unreadable (a
  corrupt file or a wrong shape, which blocks starts), and the stored state. The file check runs in the
  executor, before the load, because the load renames a corrupt file.
- **Two saves,** both used today: the delayed one from callbacks, which isn't awaited, and the awaited
  one at shutdown.
- **Remove,** for `async_remove_charge_control`.

## 8. Docs, the quality scale and D50

- **`docs/user/nortec_go.md`:**
  - *Starting a charge*: what turning *Charge* off now does (tried again for up to 10 tries or 30 minutes,
    the switch off meanwhile, then the repair issue), in place of the 2-minute paragraph's end.
  - *Data updates*: the 30-second reads also run while a stop waits.
  - *Troubleshooting*: the new repair issue, and what to do. A corrupt saved start guard blocks starts.
  - A reconfigure section next to *Asked to sign in again*.
  - *Known limitations*: a stop asked more than 30 minutes before Home Assistant comes back is not sent;
    a stored stop is sent to whatever charge is open; a stop is lost when the saved start guard can't be
    read.
- **`docs/manual-testing.md`:** a reconfigure check, for the owner only, since it takes credentials.
- **`CHANGELOG.md`**, under *Unreleased*: *Added* (reconfigure), *Changed* (a turn-off is tried again and
  ends in a repair issue instead of an error), *Fixed* (the lost stops of #85, #32 and #26; the corrupt
  store; the block's text after a restart).
- **`quality_scale.yaml`:**
  - `reconfiguration-flow` becomes `done`, without a comment; it leaves the list of rules that
    `tests/test_quality_scale.py` requires a comment for.
  - The `action-exceptions` comment says that a turn-off that fails is tried again and ends in a repair
    issue (D50), and that the other actions raise translated errors.
  - The `appropriate-polling` comment says that the 30 s reads also run while a stop is stored, for at
    most 30 minutes per stop asked (D50).
- **`docs/ha-notes.md`:** what the work teaches about `Store` (the corrupt file, the minor version), if it
  isn't there yet; decided in the learnings step.
- **`docs/decisions.md`:** D50 below, and D29's status becomes `active; the 30 s reads while the charger
  can't be read superseded by D31; what ends the pending stop, what follows the 2 minutes, and the reads
  while a stop is stored, superseded by D50`. D26 and D31 stand as they are: the stop asked for during a
  pending start was never part of their text, and a stale read still changes nothing.

### D50: A stop is stored until the charge is seen off

- **Date:** 2026-10-02 · **Status:** active
- **Decision:** Turning *Charge* off stores the stop until a read shows the charge off (stopping, or
  not open on a charger whose state is known), or *Charge* is turned on. Meanwhile the stop is sent, at
  the turn-off or when a read shows the charge stoppable, never to a charge that is stopping and never
  while a start is pending, with at least 2 minutes between two stop calls; a try fails when the call
  fails or when the charge is still on 2 minutes after the charger accepted it. A failed try raises no
  error (a rejected session aside). After 10 tries or 30 minutes from the ask, whichever is first, the
  control gives up, logs an error and raises a repair issue that a new turn-off doesn't remove. The
  charger is read every 30 s while a stop is stored, within D31's limits. A start is still never retried.
- **Why:** A stop tied to the pending start was lost whenever that ended first (#85, #32, #26), and an
  unattended stop from EV Smart Charging must actually stop the car. The stop isn't tied to one charge, so
  its age bounds the chance of stopping a later one.
- **Source:** [stop safety spec](superpowers/specs/2026-10-02-stop-safety-reconfigure-design.md),
  Decisions and §1

## 9. Tests

`pynortecgo` is mocked, and fixtures are built from its model objects (hard rule 7). No test starts or
stops a real charge.

- **The stored stop** (`test_charge_control.py`, `test_init.py`):
  - one test per row of *The cases this closes*; for #85 that is a setup whose price read is rejected
    after the stop was queued, and a setup try that is slow, lets the deadline fire, and then fails, each
    followed by a setup that sends the stop;
  - each row of the outcome table, with the warning and its number; "no active charge" followed by a
    read that shows an open charger keeps the stop, and by a read that shows the charge off ends it;
  - a turn-off right after a give-up, and a turn-on then a turn-off right after a failed call, make no
    call before the 2 minutes have passed;
  - every step of *Turning Charge off*, including a repeated turn-off that keeps the time and the count,
    and a turn-off during a pending start with a last read that shows a charge: no call;
  - every branch of *On a read*, including a stale read, which neither sends nor ends, and an open
    charger without a charge object, which gets no call;
  - two reads in a row, and a turn-off followed by a read, make one call;
  - a call that fails while the reads work makes the next call no sooner than 2 minutes later, and so
    does a reload or a restart right after a call;
  - a call answered after more than 2 minutes: its 2 minutes run from the answer;
  - a queued try that makes no call ends its wait;
  - a give-up followed by a turn-off: a new stop, and the issue stays;
  - a load with 10 tries made, with and without wait left;
  - a charger in an unknown state: the stop waits;
  - turning *Charge* on with a stop stored, on each path;
  - the 10th failed try, by a failed call and by an accepted one; the count across a reload;
  - the 30 minutes with and without reads, at load with time left, at load past the limit, and at load
    with a time in the future: the error, the issue, the switch's state;
  - no call is ever made to a charge that is `STOPPING` or not stoppable;
  - no test expects a second `start_charge()` call.
- **The read interval** (`test_coordinator.py`): a stored stop gives 30 s reads, and 5 minutes once the
  last good read is 2 minutes old.
- **Hardening** (`test_charge_control.py`): a corrupt file blocks, a missing file doesn't; the timers of a
  control whose setup failed change nothing; the reason
  survives a reload for both keys; an unexpected exception from a start is translated and sets no block.
  `hass_storage` replaces the store's load, and no file is on disk in tests, so the file check gets its
  own seam; the plan picks it.
- **The stored format** (`test_charge_control_store.py`, new): minor 1 data with and without the flag and
  a block, each wrong shape of §3, and data of a newer minor version.
- **The repair issue** (`test_repairs.py`): the confirm flow dismisses it and leaves a start block in
  place; each way it is deleted without the owner; it goes with the entry.
- **Reconfigure** (`test_config_flow.py`): success with a new email, each sign-in error and the recovery
  from it, another charger, one login call per submit, and that the device ID is the stored one.
- **Texts and scale:** the existing checks on `strings.json` against `translations/en.json` and on
  `quality_scale.yaml` (`test_quality_scale.py`) are updated.
