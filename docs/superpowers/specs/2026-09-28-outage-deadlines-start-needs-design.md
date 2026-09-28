# Start and stop deadlines without reads, and what a start needs — design

Date: 2026-09-28 · Branch: `fix/outage-reads-and-start-needs` · Issues: #34, #35

## Goal

- **What:**
  - #34: the pending start (10 min, D26) and the pending stop (2 min, D29) end on time even while the
    charger can't be read, or isn't read at all (the entry's "disable polling" option), so the 30 s reads
    and the switch's pending states end on time too.
  - #35: the user docs say what `start_charge()` needs (exactly one car and exactly one saved card), and the
    *Charge* switch's presence without a car is decided.
- **Why:** today both deadlines are checked only on a successful read. During an outage *Charge status*
  stays *Starting* or *Stopping*, the charger is read every 30 s for the whole outage, and the switch can
  stay off for longer than the 2 minutes the docs promise; with polling disabled nothing ends them. The
  docs say a car is optional, but every start without exactly one car and one card is refused.
- **Not in this work:** a stop asked during a pending start that the charger refuses while the charge is
  still `STARTING` (#32, moved to `v3` by the owner on 2026-09-28; findings in its comments).
- **Done when:** built TDD with `pynortecgo` mocked in every test; the gates pass; `scripts/smoke` passes;
  quality scale, user docs, changelog and decision log updated.

## Decisions

Answered by the owner in the brainstorm (2026-09-28), unless marked *controller*.

| Topic | Decision |
|---|---|
| Bundle | #34 and #35 in one PR; #32 moved to `v3` |
| How the deadlines end during an outage | Timers (`async_call_later`) for both deadlines, instead of a check on the failed read: they also cover no reads at all |
| The charger's own `STARTING` / `STOPPING` during an outage | 30 s only while the last good read is under 2 minutes old; older, 5 min (a charge is open). On a failed charger read the interval is worked out again before `UpdateFailed` (review finding; D29's "no cap" assumed working reads) |
| Owner of a deadline | *Controller.* The timer is the only one that ends a pending state because its time is up; a read ends it early only on evidence, as today |
| Pending start overdue at restart | *Controller.* Evidence first, as today: the start timer gets at least a 2-minute grace at load, so the setup's first read decides; only if it brings no evidence does the timer block (review finding) |
| *Charge* switch without exactly one car | Always added. A start is refused with the reason (a translated `ServiceValidationError`, no card hold). The saved card can't be checked beforehand, so hiding the switch for the car alone would only half solve it |
| Changelog | *Controller.* Nothing is released since `v0.0.1`, so no *Fixed* entry: the existing *Unreleased* line on the 30 s reads is made true. #35 changes only docs: no entry |
| Process | Full path (spec, plan, `full-reviewer`); the owner's default unless ruled otherwise under D25 |

Facts used, public-safe:

- `pynortecgo` 0.2.0: `start_charge()` checks, before any payment request, that there is exactly one car
  and exactly one saved card (`VehicleNotFoundError`, `MultipleVehiclesError`, `PaymentSourceNotFoundError`,
  `MultiplePaymentSourcesError`); the integration already turns each into a translated
  `ServiceValidationError`. There is no public call that counts saved cards.
- `has_car` becomes false only when the first car read raises `VehicleNotFoundError` or
  `MultipleVehiclesError`; the switch platform doesn't look at it.
- Home Assistant's `DataUpdateCoordinator` (checked in the installed source, 2026-09-28): setting
  `update_interval` doesn't move a read already scheduled; after a failed read the next one is scheduled
  with the current `update_interval`, or `retry_after` when the error carried one.

## 1. Files

| File | Change |
|---|---|
| `custom_components/nortec_go/charge_control.py` | The start and stop timers (§2); module docstring names D31 |
| `custom_components/nortec_go/const.py` | `START_LOAD_GRACE` and `FAST_READ_MAX_AGE` (both 2 min; §2.5, §3) |
| `custom_components/nortec_go/coordinator.py` | `interval_for` takes the last good read's age; the interval on a failed read (§3) |
| `custom_components/nortec_go/quality_scale.yaml` | `appropriate-polling` comment (§4) |
| `docs/user/nortec_go.md` | §5 |
| `CHANGELOG.md` | §6 |
| `docs/decisions.md` | D31, D32 (§7) |
| `tests/test_charge_control.py`, `tests/test_coordinator.py`, `tests/test_switch.py` | §8 |

No change to `switch.py`.

## 2. The deadlines in `ChargeControl` (#34)

### 2.1 Ownership

- The timers are the only code that ends a pending start or a pending stop because its time is up. The
  10-minute check in `on_charger_read` goes, and so do the `_expire_stop_pending()` calls in
  `on_charger_read`, `async_start` and `async_stop`, so a read and a timer can never both log or block.
- A read still ends either state early on evidence, unchanged: the pending stop when the charge is no
  longer on; the pending start when a charge happened, the cable is unplugged, or the stop asked is sent.
- Where the timestamps change today (the plan must cover each):
  - `_pending_since`: set in `async_load` and `async_start`; cleared in `_async_send_stop` and
    `on_charger_read` (the stop asked is sent, a charge happened or the cable is unplugged, the timeout).
  - `_stop_pending_since`: set in `_async_send_stop` (or set to `None` there on `NoActiveChargeError`) and
    in `on_charger_read` (the background stop); cleared in `on_charger_read` and `_clear_stop_pending`
    (which also calls `_on_change`; the read path doesn't).
- One visible change at runtime: the timer can end a pending start up to one 30 s read before a read would
  have brought evidence. A later read then clears the block for a charge seen or an unplug (D26), but not
  for `BUSY_NON_RELEASED`, which today ended the pending start with no block. Accepted with the timer
  ruling; `test_timeout_on_unplugged_read_ends_without_block` changes meaning accordingly.

### 2.2 The start timer

- **Armed** whenever `_pending_since` is set (a successful start, or `async_load`), for
  `START_CONFIRM_TIMEOUT` from `_pending_since`.
- **Cancelled** wherever `_pending_since` is cleared, through one helper, and in `async_shutdown`. Arming
  again cancels the old timer first.
- **When it fires**, the control, under its lock, and only if not closed and `_pending_since` is still the
  one it was armed for: clears `_pending_since` and `_stop_asked`, logs today's warning ("No charge seen
  within … of the start; blocking starts"), sets the block with the `start_blocked` repair issue, saves and
  tells the coordinator (`_changed`).

### 2.3 The stop timer

- **Armed** whenever `_stop_pending_since` is set (a successful stop, and the background stop's pending
  stop from `on_charger_read`), for `STOP_CONFIRM_TIMEOUT`.
- **Cancelled** wherever `_stop_pending_since` is cleared, through one helper, and in `async_shutdown`.
  Arming again cancels the old timer first: the background stop arms it in `on_charger_read`, then
  `_async_send_stop` sets `_stop_pending_since` again.
- **When it fires**, under the lock, only if not closed and `_stop_pending_since` is still the one it was
  armed for: clears it, logs today's warning ("No stop seen within …; showing the charger's state again")
  and tells the coordinator (`_on_change`). The pending stop isn't stored, so nothing is saved.

### 2.4 Locking

A timer's callback changes nothing itself: it starts a background task on the entry
(`async_create_background_task`, which unload cancels) that takes the control's lock and then checks as
in §2.2–2.3. So a timer that comes due while a start or stop is in flight waits for it. Example: the
start timer comes due while `_async_send_stop` awaits `stop_charge()`; that call clears `_pending_since`,
so when the task gets the lock the start is no longer pending and nothing is blocked.

### 2.5 Restart

`async_load` arms the start timer from the stored `start_pending_since` for the time left, capped at
`START_CONFIRM_TIMEOUT` (a stored time in the future after a clock change) and at least `START_LOAD_GRACE`
(2 min, new in `const.py`). The setup's first read runs right after `async_load`, so a start that is
overdue at restart is still decided by evidence first, as today: a charge seen, `BUSY_NON_RELEASED` or the
cable unplugged end it with no block. Only if that read brings no evidence does the timer block at the end
of the grace. If the setup's first read fails, the setup fails (`ConfigEntryNotReady` and the like), §2.6
cancels the timer, and the retried setup loads the store and arms a new grace; so while the charger can't
be read at startup the stored pending start stays as it is (no entities exist meanwhile), and is decided
once a setup's first read succeeds. The pending stop isn't stored (D29), so there is nothing to re-arm.

### 2.6 Cleanup

- `async_shutdown` cancels both timers (a normal unload).
- A setup that fails after `async_load` (the first read raising `ConfigEntryNotReady`,
  `ConfigEntryAuthFailed` or `ConfigEntryError`, or the setup's price read raising
  `ConfigEntryAuthFailed`) never calls `async_unload_entry`, but Home Assistant runs the entry's on-unload
  callbacks. So the control registers, once in its constructor, one `entry.async_on_unload` callback that
  cancels whichever timers are current. Otherwise the failed setup's timer could block, raise the repair
  issue and save over the retried setup's store.
- The timers are created as `HassJob(..., cancel_on_shutdown=True)`, so Home Assistant's stop cancels
  them too.

### 2.7 Unchanged

What clears the block, the stored shape, the stale-read check, D26's 10 minutes and D29's 2 minutes and
what happens when they pass (apart from §2.1's one runtime change).

## 3. The coordinator and the interval (#34)

- **`interval_for(charger, control, age)`**, where `age` is the time since the last good read, still goes
  through `charge_status`, so its edge cases stay as today (a block wins; an unknown state never gives
  30 s; a pending start with a charge already open follows the charger):
  - 30 s when `charge_status` is starting or stopping and either our start or stop is pending
    (`control.start_pending` or `control.stop_pending`; the timers bound these) or
    `age < FAST_READ_MAX_AGE` (2 min);
  - 5 min when that status holds with an older read (a charge is open), or while `CHARGING`;
  - 60 min otherwise.
  After a successful read `age` is zero, so nothing changes while reads work.
- **On a failed charger read** (any `NortecGoError` from `get_charger()`, including those raised as
  `ConfigEntryAuthFailed` or `ConfigEntryError`; one assignment ahead of the existing `except` chain, for
  example a `try/except NortecGoError` wrapper around it), `_async_update_data` sets
  `update_interval = interval_for(data.charger, control, now - data.read_at)` before raising, when there
  is data. Home Assistant schedules the next read after the failure with that interval, so the charger's
  own `STARTING` / `STOPPING` gives 30 s reads for about 2 minutes of an outage, then 5 min. A
  `RateLimitError`'s `retry_after` still wins for that one read. The error mapping is unchanged.
- A timer that ends a pending state calls `on_change`, that is `_async_control_changed`: it puts the new
  control state in `data`, works out `update_interval` again from the last good charger data and its age
  and updates the entities. So during an outage the switch shows the last good read's
  state again and the interval is that read's: 5 min when it showed a charge, 60 min otherwise.
  *Charge status* is unavailable while reads fail (it keeps
  `CoordinatorEntity`'s availability); only the switch shows the change.
- A new interval doesn't move a read already scheduled: after a timer fires, at most one more read comes at
  30 s; when it fails, the next is scheduled with the new interval. `retry_after` still wins.
- With polling disabled the timers still fire; the interval isn't used.
- Before the first read (`data` is `None`), `_async_control_changed` returns early, as today.

## 4. Quality scale

`appropriate-polling` stays `done`; its comment becomes: "30 s only while a charge is starting or
stopping, bounded while reads fail (10 min after a start, 2 min after a stop or the last good read);
5 min while charging, 60 min otherwise (D29, D31)."

## 5. User docs

In `docs/user/nortec_go.md`:

- **Unsupported devices:** "An account with more than one charger. With no car or more than one there are
  no car entities, and starting a charge needs exactly one car and one saved card (see *Prerequisites*)."
- **Prerequisites:** "You need a Nortec Go account with exactly one charger. To start charges from Home
  Assistant, the account also needs exactly one car and exactly one saved card; without them everything
  else works (the sensors, the prices and *Refresh*), and a start is refused with the reason. A car added
  later appears after you reload the integration."
- **Starting a charge:**
  - add: "A start is refused, with no card hold, without exactly one car and one saved card (see
    *Prerequisites*)."
  - after the 10-minute paragraph, add: "This also applies while the charger can't be read. The block
    clears the same way."
  - the 2-minute paragraph: "After you turn *Charge* off, it shows off for up to 2 minutes, even while
    the charger can't be read, and *Charge status* shows *Stopping* while Home Assistant waits for the
    charger to show the stop. Turning *Charge* on in that time is refused."
- **Data updates:** after the list, add: "While the charger can't be read, the 30-second reads stop after
  about 2 minutes, or about 10 minutes after you turn *Charge* on."
- **Known limitations:** add "Starting a charge needs exactly one car and one saved card (see
  *Prerequisites*)."

## 6. Changelog

Under *Unreleased* → *Added*, the 30 s line becomes: "The charger is read every 30 seconds while a charge
is starting or stopping, for about 2 minutes (10 after a start) while it can't be read, and right away
after turning *Charge* on or off."

## 7. Decision log

```markdown
### D31: The start and stop deadlines hold without reads
- **Date:** 2026-09-28 · **Status:** active
- **Decision:** The 10-minute pending start (D26) and the 2-minute pending stop (D29) end by timers that
  fire whether or not the charger is read; a read ends them early only on evidence. The charger's own
  starting or stopping state gives 30 s reads only while the last good read is under 2 minutes old
  (5 min after that), and a failed read works the interval out again.
- **Why:** Checked only on successful reads, they lasted a whole outage, with reads every 30 s, and never
  ended with polling disabled; D29's "no cap" on the charger's own states assumed working reads.
- **Source:** [outage deadlines and start needs spec](superpowers/specs/2026-09-28-outage-deadlines-start-needs-design.md), §2–3

### D32: The Charge switch is always added
- **Date:** 2026-09-28 · **Status:** active
- **Decision:** The *Charge* switch is added whatever cars the account has. A start without exactly one car
  and one saved card is refused with the reason, before any card hold.
- **Why:** The saved card can't be checked beforehand, so hiding the switch for the car alone would only
  half solve it, and the refusal explains itself.
- **Source:** [outage deadlines and start needs spec](superpowers/specs/2026-09-28-outage-deadlines-start-needs-design.md), Decisions
```

D26 keeps its status: D31 changes how its deadline is kept, not what it is. D29's status becomes
`active; the 30 s reads while the charger can't be read superseded by D31`.

## 8. Tests

TDD, `pynortecgo` mocked, the timers fired with `freezer` and `async_fire_time_changed`, then
`hass.async_block_till_done(wait_background_tasks=True)` (the timer's work runs as a background task).
The test plugin fails a test that leaves a timer scheduled unless its job has `cancel_on_shutdown`
(§2.6); the `control` fixture also calls `async_shutdown` at teardown.

- `tests/test_charge_control.py`:
  - a pending start with no read ends at 10 minutes with the block and the repair issue, and not a second
    earlier;
  - a pending stop with no read ends at 2 minutes, and not a second earlier;
  - a read that sees a charge ends the pending start and its timer doesn't block later; a read that sees
    the charge off ends the pending stop and its timer does nothing later;
  - a new start after a pending start ended arms a fresh timer; the old one does nothing;
  - after unload neither timer changes anything;
  - `async_load` with a stored pending start that has time left arms the timer for the rest; one that is
    overdue gets the 2-minute grace, and a first read with evidence ends it with no block, while one with
    none (or no read) blocks at the end of the grace; a stored time in the future is capped at 10 minutes;
  - a failed setup's timers are cancelled by the entry's on-unload callback;
  - the background stop's re-armed stop timer leaves one timer scheduled, not two;
  - a start timer that comes due while `stop_charge()` is in flight waits for the lock and blocks nothing;
  - the existing tests that reach a timeout with `freezer.tick` and a read are changed to fire the timer.
- `tests/test_coordinator.py`: with the charger read failing, a pending stop after a read that showed
  `CHARGING` ends at 2 minutes, the switch shows on again and `update_interval` becomes
  `INTERVAL_CHARGING`; a pending start after an idle, connected read ends at 10 minutes with the block and
  `INTERVAL_IDLE`; a failed read 2 minutes or more after a good read that showed `STOPPING` (no pending
  stop of ours) sets `INTERVAL_CHARGING`, and one under 2 minutes keeps `INTERVAL_CHANGING`; a failed
  `RateLimitError` read still uses `retry_after`; `interval_for` is covered for each branch.
- `tests/test_switch.py`: the switch is added when the account has no car.

## 9. Verification

The gates in `CLAUDE.md` → Commands, including the coverage gate; `scripts/smoke` on the branch before the
PR is marked ready. No real start or stop (hard rule 2).
