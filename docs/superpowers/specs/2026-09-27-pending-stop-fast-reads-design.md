# Pending stop, fast reads and a Last read sensor — design

Date: 2026-09-27 · Branch: `feat/pending-stop-fast-reads` · Issues: #30, #22, #23, #16

## Goal

- **What:**
  - #30: after a stop the switch stays off until the charger catches up (a *pending stop*); the charger is
    read every 30 s while the charge is starting or stopping, and right away after a start, a stop or the
    Refresh button; a *Last read* sensor shows when the charger was last read.
  - #22: the charger device's name follows a rename in the Nortec Go app.
  - #23: any other `pynortecgo` error from the charger read fails the read cleanly.
  - #16: each `pynortecgo` pin bump re-checks the client's exception texts and classes.
- **Why:** in the owner's live test (2026-09-27) a stop had to be pressed twice: right after a successful
  `stop_charge()` the charger still reports `CHARGING`, so the switch went back on about 2 s later. The
  state should follow a start or stop within seconds, and the owner should see how fresh the data is.
- **Not in this work:** energy and average power sensors (#24, needs NortecGo#55, not started), the manual
  test guide (#10), the `pynortecgo` 0.3.0 bump (its breaking forecast change needs its own decision).
- **Done when:** built TDD with `pynortecgo` mocked in every test; the gates pass; `scripts/smoke` passes;
  quality scale, user docs, changelog and decision log updated.

## Decisions

Answered by the owner in the brainstorm (2026-09-27), unless marked *controller*.

| Topic | Decision |
|---|---|
| Turn on during a pending stop | Refused with a translated `ServiceValidationError` ("a stop is under way; try again when it has ended"). No start is sent, so no second card hold |
| Turn off during a pending stop | A no-op (from #30) |
| Pending stop ends | When a read sees the charge no longer on (`charge_state` not `STARTING`, `CHARGING` or `PAUSED`), or after 2 minutes; then the switch trusts the read again (from #30) |
| Polling | 30 s while *Charge status* is `starting` or `stopping` (the charger's own state, or our pending start or stop); 5 min while `charge_state` is `CHARGING`; 60 min otherwise. The 15 min *connected* interval goes |
| Car on fast reads | Skipped: the car is read when its last read try is at least 4.5 minutes old (§3.2), and on every Refresh press |
| Last read | A timestamp sensor: HA's frontend shows it as "x minutes / hours / days ago", in one unit, and the exact time on the entity's page. Not a text sensor: its state would change every minute and fill the recorder |
| No cap on the charger's own `STARTING` / `STOPPING` | *Controller.* The 30 s reads last as long as the charger reports these states. They are brief (a stop settles in about 25 s); a pending start or stop has its own timeout (10 min, 2 min) |
| Pending stop stored | *Controller.* No: it lasts at most 2 minutes. The stored start guard keeps its shape, so an upgrade can't trip its "unexpected shape" block. Accepted: after a restart within those 2 minutes the switch can show on until the charger shows the stop (up to 5 minutes at the charging interval), and a second *off* then sends a second stop |
| Stop with an unclear outcome | *Controller.* A stop that fails with a timeout or connection error may still have happened; no pending stop is set. Accepted: the read right away shows the charger's state |
| Device rename | *Controller.* The registry's `name` follows `Charger.name` (empty: the entry title), like the car device; an owner's own rename (`name_by_user`) still wins |
| Pin-bump checklist | *Controller.* In `docs/releasing.md` → *Bumping `pynortecgo`*, with a line in the PR template pointing to it |

Facts used, public-safe:

- From the `NortecGo` session (2026-09-27): no read rate limit is known. Reads of the charger every 15–20 s
  for several minutes were observed without one; no limit was ever probed, so this is observed, not
  guaranteed. `pynortecgo` retries rate-limited requests itself and raises `RateLimitError` (with
  `retry_after`) when its retries run out; the coordinator already turns that into
  `UpdateFailed(retry_after=…)`. A stop settles in about 25 s; a start is seen within about 30–60 s.
- `pynortecgo`'s `stop_charge()` checks the charger first and raises `NoActiveChargeError` or
  `ChargeNotStoppableError`; after a timeout or connection error the stop may have happened.
- Home Assistant's `DataUpdateCoordinator` (checked in the installed source, 2026-09-27):
  - `async_request_refresh()` goes through a debouncer with a 10 s cooldown: a second request within the
    cooldown runs only when the cooldown ends.
  - `async_refresh()` skips the cooldown and runs under the debouncer's lock, so it never overlaps a
    scheduled or requested read.
  - After a failed read the next read is scheduled with the current `update_interval`.
  - A read is scheduled at whole loop seconds plus a random 0.05–0.5 s, so it can come up to about 1 s
    earlier than exactly one interval after the last one.
  - With `always_update=False` (ours) the listeners are told only when the new data differs from the old.

## 1. Files

| File | Change |
|---|---|
| `custom_components/nortec_go/charge_control.py` | The pending stop (§2); `is_charge_on` and `charge_status` take it into account |
| `custom_components/nortec_go/coordinator.py` | The interval (§3.1), the car skip (§3.2), `async_read_now` (§3.3), `read_at` (§4), the device rename (§5), the catch-all (§6) |
| `custom_components/nortec_go/const.py` | `INTERVAL_CHANGING` (30 s), `CAR_READ_MIN_AGE` (§3.2), `STOP_CONFIRM_TIMEOUT` (2 min); `INTERVAL_CONNECTED` goes; `INTERVAL_UNPLUGGED` becomes `INTERVAL_IDLE`; the polling comment cites D29 |
| `custom_components/nortec_go/button.py` | Refresh reads right away, the car included (§3.3) |
| `custom_components/nortec_go/switch.py` | The `is_on` docstring mentions the pending stop |
| `custom_components/nortec_go/sensor.py` | The *Last read* sensor (§4) |
| `custom_components/nortec_go/strings.json`, `translations/en.json` | The *Last read* name, the `stop_pending` exception |
| `custom_components/nortec_go/quality_scale.yaml` | §8 |
| `docs/releasing.md`, `.github/pull_request_template.md` | §7 |
| `tests/…` | §9 |
| `docs/user/nortec_go.md`, `CHANGELOG.md` | §10 |
| `docs/decisions.md` | §11 |

## 2. Pending stop

`ChargeControl` gains `_stop_pending_since: datetime | None`, apart from `stop_asked` (a stop asked for
during a pending start, [charge switch spec](2026-09-26-charge-switch-design.md) §3.3). The snapshot
`ChargeControlState` gains `stop_pending: bool`. The pending stop is not stored (see *Decisions*): the
stored shape and `async_load` are unchanged, and a change to the pending stop alone tells the coordinator
(`_on_change`) without saving. A change that also touches a stored field goes through `_changed` as today.

### 2.1 When it is set

- **A direct stop:** in `_async_send_stop`, after `stop_charge()` returns without an error, to
  `dt_util.utcnow()`.
- **The background stop** (a stop asked during a pending start, sent once a read sees the charge open): set
  in `on_charger_read` when the background stop is queued, in the same step that ends the pending start
  (§2.3, step 4). So the read that queues it already shows the switch off and *Stopping*, and a `turn_off`
  before the background stop runs is a no-op instead of a second `stop_charge()`. When the background stop
  succeeds, `_async_send_stop` sets the time again.
- **It is cleared,** by `_async_send_stop`, on `NoActiveChargeError` (nothing to wait for) and on every
  error it raises. For a direct stop it was not set, so nothing changes; for the background stop this ends
  the pending stop it queued. `_async_background_stop` when unloading returns without clearing it (the
  control is being discarded).

### 2.2 Start and stop while it is pending

Both run under the lock, after `_raise_if_closed()`. First, a pending stop older than
`STOP_CONFIRM_TIMEOUT` counts as ended and is cleared (so "for 2 minutes" holds even while reads fail).
Then, if a stop is still pending:

- **`async_stop`** returns at once, with no API call.
- **`async_start`** raises `ServiceValidationError(translation_domain=DOMAIN, translation_key="stop_pending")`
  before every other start check; `start_attempts` is not counted.

`_async_background_stop` doesn't make this check: it owns the pending stop it runs for.

### 2.3 Each charger read

`on_charger_read` runs these steps in order:

1. Keep `charger` as the last read. If the control is closed, return.
2. **Pending stop:** if one is set and the read's `charge_state` is not `STARTING`, `CHARGING` or `PAUSED`,
   or `STOP_CONFIRM_TIMEOUT` (2 min) has passed since it was set, clear it; the timeout logs a warning ("No
   stop seen within 2 minutes; showing the charger's state again"). This step comes before the stale-read
   return: the stale-read check (D26) is about start attempts, and a read begun before the stop saw the
   charge on, so it can't end the pending stop early.
3. If the read is stale (begun before the latest start attempt), return.
4. **Pending start** (unchanged, D26), except that the branch that queues the background stop also sets the
   pending stop (§2.1).
5. **Block** (unchanged, D26).
6. Save if a stored field changed.

The coordinator carries the new control state in the read's data, so no separate `_on_change` is needed.

### 2.4 Switch and status

- **`is_charge_on`:** false while a stop is pending (checked first).
- **`charge_status`:** the first matching row wins:

| Value | When |
|---|---|
| `start_blocked` | the block is set (unchanged, first) |
| `stopping` | a stop is pending (new) |
| … | the existing rows, unchanged |

## 3. Reads

### 3.1 Interval

`interval_for(charger, control)` replaces `interval_for(charger)`:

| Interval | When |
|---|---|
| `INTERVAL_CHANGING`, 30 s | `charge_status(charger, control)` is `starting` or `stopping` |
| `INTERVAL_CHARGING`, 5 min | `charge_state` is `CHARGING` |
| `INTERVAL_IDLE`, 60 min | otherwise (idle, paused, unplugged, not released, blocked, unknown) |

Using `charge_status` keeps the interval and the *Charge status* sensor in step. It covers the charger's own
`STARTING` and `STOPPING`, a pending start while no charge is open yet (up to 10 min,
`START_CONFIRM_TIMEOUT`, D26), a stop asked during a pending start, and a pending stop. A pending start
with a `CHARGING` read shows `charging`, so it gets 5 min.

The coordinator sets `update_interval` from it:

- after each successful read;
- in `_async_control_changed`, before the read right away is asked for. So if that read fails, the next
  read still comes at the new interval (HA reuses the current interval after a failed read), not 60 min
  later.

The coordinator starts with `update_interval=INTERVAL_IDLE`; the first read sets the real one.

`PAUSED` moves from 15 min to 60 min: the owner accepts that a charge starting or resuming outside Home
Assistant can take up to 60 minutes to show; the Refresh button reads it now.

### 3.2 Car on fast reads

The coordinator keeps `_car_read_at` (the time of the last car read try, success or not) and
`_read_car_next` (a Refresh asked for the car). A read calls `get_vehicle()` when `has_car` and one of:

- no car read has been tried yet;
- the last try is at least `CAR_READ_MIN_AGE` old: `INTERVAL_CHARGING - INTERVAL_CHANGING`, 4.5 min. The
  margin keeps a read at the 5 min interval from being skipped when it comes slightly early (see *Facts*),
  and covers the difference between the loop's clock and `dt_util.utcnow()`;
- `_read_car_next` is set.

The read that reads the car clears `_read_car_next`, whichever read that is. Otherwise the read keeps the
last car data (`self._vehicle`). The car's error handling is unchanged. So the car is read on every read at
5 or 60 min, and about every 5 minutes during 30 s reads.

### 3.3 Reading right away

`NortecGoCoordinator.async_read_now(*, with_car: bool = False)` sets `_read_car_next` when `with_car`, then
calls `async_refresh()`. It is not debounced (see *Facts*).

- `ChargeControl` gets `async_read_now` (without the car) as its `request_refresh`, so every start, stop,
  stop failure and background stop reads right away.
- The Refresh button calls `async_read_now(with_car=True)`, then `async_read_prices()` as today. Its
  docstring loses "(debounced)".
- `homeassistant.update_entity` still goes through `async_request_refresh()` (debounced), and reads the car
  only by the rule of §3.2.

## 4. Last read sensor

- `NortecGoData` gains `read_at: datetime`, set to `dt_util.utcnow()` in `_async_update_data` after a
  successful charger read. `_async_control_changed` keeps it (it replaces only `control`). A read with the
  same charger data now always differs, so the listeners are told on every read, which the sensor needs.
- Charger device, key `last_read`, device class `timestamp`, `EntityCategory.DIAGNOSTIC`, enabled by
  default; value `coordinator.data.read_at`.
- **Available** whenever the coordinator has data (always after setup), even after a failed read: then it
  shows how old the data is.

## 5. Charger device name (#22)

After each successful charger read the coordinator brings the charger device's `name` up to date, as it does
for the car device: it looks the device up by `(DOMAIN, charger_id)`, returns if there is none yet (the
entities create it), and otherwise updates `name` to `charger.name` or, when that is empty, the entry title.
It writes only when the name differs. An owner's own rename (`name_by_user`) is a separate field and still
wins in the UI.

## 6. Catch-all in the charger read (#23)

`_async_update_data` gets a final `except NortecGoError as err: raise UpdateFailed(str(err)) from err`,
after the specific clauses (they are its subclasses). `pynortecgo`'s messages hold no credentials or IDs
(the existing comment), which §7's checklist re-checks at each pin bump.

## 7. Pin-bump checklist (#16)

`docs/releasing.md` → *Bumping `pynortecgo`*: the opening sentence ("Once the integration depends on…") is
reworded, since it already does. A checklist for the bump PR follows:

- Read the new version's exception messages, including wrapped lower-layer errors, and confirm they hold no
  email, password, token, IDs or request bodies (hard rule 5): the integration passes them into logs and
  `ConfigEntry*` errors.
- Check for new exception classes the charger, car, price, start and stop calls can raise, and give each the
  right handling (the charger read's catch-all, §6, only keeps an unknown one from crashing the read).
- Read the client's changelog for breaking changes to the models the entities use.

`.github/pull_request_template.md` gets one checklist line: "`pynortecgo` bump → the checklist in
`docs/releasing.md` → *Bumping `pynortecgo`* done".

## 8. Quality scale

- `entity-unavailable`: stays `done`; its comment lists the entities that stay available after a failed
  read on purpose: the *Charge* switch, the *Current price* sensor, the *Refresh* button and the *Last read*
  sensor.
- `appropriate-polling`: stays `done`; comment: 30 s only while a charge is starting or stopping, 5 min while
  charging, 60 min otherwise.
- No other rule changes.

## 9. Tests

TDD; `pynortecgo` always mocked; fixtures built from `pynortecgo` model objects (hard rule 7).

- **`test_charge_control.py`:**
  - a successful direct stop sets the pending stop; `NoActiveChargeError` and a failed stop don't;
  - the background stop: the read that queues it shows the switch off and `stopping`; a `turn_off` before it
    runs makes no API call, and `stop_charge()` is called exactly once; its success keeps the pending stop,
    its failure or `NoActiveChargeError` clears it;
  - it ends on a read with `STOPPING`, with `COMPLETED`, with no open charge; not on a read still `CHARGING`
    or `PAUSED`, including a stale read (begun before the latest start attempt) and a read begun before the
    stop that returns after it; it ends on a read after 2 minutes, with a warning;
  - `turn_off` while pending: no API call; `turn_on` while pending: `ServiceValidationError` with
    `stop_pending`, no `start_charge()`, `start_attempts` unchanged;
  - after 2 minutes with no read, `turn_on` goes through the normal start checks and `turn_off` the normal
    stop;
  - `is_charge_on` false and `charge_status` `stopping` while pending, `start_blocked` still first;
  - the pending stop alone doesn't save the store; an old store loads without a block.
- **`test_coordinator.py`:**
  - `interval_for`: pending start with no charge open → 30 s; pending start with a `STARTING` read → 30 s;
    pending start with a `CHARGING` read → 5 min; stop asked during a pending start, no charge open →
    30 s; pending stop with a `CHARGING` read → 30 s; charger `STOPPING` → 30 s; `CHARGING` → 5 min;
    `PAUSED`, idle, unplugged, not released, blocked → 60 min;
  - a start whose read right away fails is read again 30 s later;
  - the car: skipped on a read within 4.5 min of the last try; read on a read 4 min 59 s after it (the
    early 5-minute read); read with `async_read_now(with_car=True)`, and the flag is cleared by whichever read
    reads the car;
  - a stop within 10 s of an earlier read still gets its read right away;
  - `read_at` is set on a successful read, kept on a control change, and the listeners are told on a read
    with unchanged charger data;
  - the device name follows a rename, falls back to the entry title when empty, and nothing happens before
    the device exists;
  - an unknown `NortecGoError` subclass from `get_charger()` fails the read with `UpdateFailed`.
- **`test_sensor.py`:** *Last read* shows `read_at`, is diagnostic, and stays available after a failed read.
- **`test_button.py`:** Refresh reads right away with the car, then the prices.
- **`test_switch.py`:** the switch is off right after a stop while the read still says `CHARGING`; `turn_on`
  then raises the translated message.
- **Gates:** `CLAUDE.md` → Commands, coverage ≥ 95%.

## 10. User docs and changelog

- `docs/user/nortec_go.md`:
  - *Supported functionality → Charger*: the *Charge* row adds "and off right after a stop until the charger
    shows it"; a *Last read* row (diagnostic sensor: when the charger was last read).
  - *Data updates*: the new schedule (30 s while a charge is starting or stopping, 5 min while charging,
    60 min otherwise), the car at most about every 5 minutes, a read right away after a start, a stop or
    Refresh. `homeassistant.update_entity` reads the charger, and the car only if it wasn't read in the last
    few minutes, but not the prices.
  - *Starting a charge*: after a stop the switch shows off and *Charge status* shows *Stopping* for up to 2
    minutes, and a start is refused until then.
  - *Known limitations*: "up to 15 minutes apart while a cable is connected" becomes 60 minutes; a charge
    started or resumed outside Home Assistant can take up to 60 minutes to show.
  - *Automation examples*: the "read once an hour while no cable is connected" rationale still holds; it
    stays.
- `CHANGELOG.md`, *Unreleased → Added* (the switch, the schedule and the Refresh button are unreleased, so
  their lines are amended, not listed as *Changed* or *Fixed*):
  - the *Charge* switch line adds that it shows off right after a stop until the charger follows;
  - new: the *Last read* sensor; the charger is read every 30 s while a charge is starting or stopping;
    the charger's device name follows a rename in the Nortec Go app.

## 11. Decisions log

- **D29: Pending stop and fast reads.** After a successful stop the switch shows off and *Charge status*
  *Stopping* until a read sees the charge no longer on, or for 2 minutes, and a start is refused meanwhile.
  The charger is read every 30 s while *Charge status* is *starting* or *stopping*, 5 min while charging
  and 60 min otherwise (replacing D27's intervals and D26's last sentence), and right away after a start, a
  stop or Refresh. *Why:* the charger reports the old state for about 25 s after a stop, so the switch
  flipped back on and a stop was pressed twice; 30 s reads were observed without a rate limit. Source: this
  spec, *Decisions* and §2–3.
- D26 and D27 stay active; D29 names the parts it replaces (D27's no polling settings, price reads and
  Refresh button stand).

## 12. Verification

- The gates pass locally and in CI; `scripts/smoke` passes.
- The owner's manual test with `scripts/develop`, **only with the owner's explicit OK** (hard rule 2): one
  stop with the switch; it stays off, *Charge status* shows *Stopping*, then the charger's state; *Last read*
  moves every 30 s meanwhile.
