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
| Car on fast reads | Skipped: the car is read when its last read is at least 5 minutes old, and on every Refresh press |
| Last read | A timestamp sensor: HA's frontend shows it as "x minutes / hours / days ago", in one unit, and the exact time on the entity's page. Not a text sensor: its state would change every minute and fill the recorder |
| Pending stop stored | *Controller.* No: it lasts at most 2 minutes. The stored start guard keeps its shape, so an upgrade can't trip its "unexpected shape" block. After a restart within those 2 minutes the switch may show on until a read sees the stop |
| Device rename | *Controller.* The registry's `name` follows `Charger.name` (empty: the entry title), like the car device; an owner's own rename (`name_by_user`) still wins |
| Pin-bump checklist | *Controller.* In `docs/releasing.md` → *Bumping `pynortecgo`*, with a line in the PR template pointing to it |

Facts used, public-safe:

- From the `NortecGo` session (2026-09-27): no read rate limit is known; the charger was read every 15–20 s
  for several minutes in captures without a 429. No limit was ever probed, so this is observed, not
  guaranteed. The client retries a 429 itself, honouring `Retry-After`, and raises `RateLimitError` when its
  retries run out; the coordinator already turns that into `UpdateFailed(retry_after=…)`. A stop settles in
  about 25 s; a start is seen within about 30–60 s.
- Home Assistant's `DataUpdateCoordinator` (checked in the installed source, 2026-09-27):
  - `async_request_refresh()` goes through a debouncer with a 10 s cooldown: a second request within the
    cooldown runs only when the cooldown ends.
  - `async_refresh()` skips the cooldown and runs under the debouncer's lock, so it never overlaps a
    scheduled or requested read.
  - With `always_update=False` (ours) the listeners are told only when the new data differs from the old.

## 1. Files

| File | Change |
|---|---|
| `custom_components/nortec_go/charge_control.py` | The pending stop (§2); `is_charge_on` and `charge_status` take it into account |
| `custom_components/nortec_go/coordinator.py` | The interval (§3.1), the car skip (§3.2), `async_read_now` (§3.3), `read_at` (§4), the device rename (§5), the catch-all (§6) |
| `custom_components/nortec_go/const.py` | `INTERVAL_CHANGING` (30 s), `STOP_CONFIRM_TIMEOUT` (2 min); `INTERVAL_CONNECTED` goes; `INTERVAL_UNPLUGGED` becomes `INTERVAL_IDLE` |
| `custom_components/nortec_go/button.py` | Refresh reads right away, the car included (§3.3) |
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
`ChargeControlState` gains `stop_pending: bool`.

- **Set:** in `_async_send_stop`, after `stop_charge()` returns without an error, to `dt_util.utcnow()`. So
  both a direct stop and the background stop (after a stop asked during a pending start) set it. Not set on
  `NoActiveChargeError` (there is no charge to wait for) or on any error. Setting it tells the coordinator
  (`_changed`) before the read is asked for.
- **Ends,** in `on_charger_read`, when a read sees `charge_state` not in `STARTING`, `CHARGING`, `PAUSED`
  (so `STOPPING`, `COMPLETED`, `UNKNOWN` or no open charge), or when `STOP_CONFIRM_TIMEOUT` (2 min) has passed
  since it was set; the timeout logs a warning ("No stop seen within 2 minutes; showing the charger's state
  again"). The start-attempt stale-read check (D26) is not used for it: a read begun before the stop saw the
  charge on, so it can't end it early.
- **`async_stop`** while a stop is pending: returns at once, no API call.
- **`async_start`** while a stop is pending: raises `ServiceValidationError(translation_key="stop_pending")`,
  checked before every other start check; `start_attempts` is not counted.
- **Not stored** (see *Decisions*); `async_load` and the stored shape are unchanged.
- **`is_charge_on`:** false while a stop is pending (before the existing rules).
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
`STARTING` and `STOPPING`, a pending start (up to 10 min, `START_CONFIRM_TIMEOUT`, D26), a stop asked during
a pending start, and a pending stop. The coordinator sets `update_interval` from it after each read. A start
or stop needs nothing more: it reads right away (§3.3), and that read sets the interval.

`PAUSED` moves from 15 min to 60 min: the owner accepts that a charge starting or resuming outside Home
Assistant can take up to 60 minutes to show; the Refresh button reads it now.

### 3.2 Car on fast reads

The coordinator keeps `_car_read_at` (the time of the last car read attempt, success or not). A read calls
`get_vehicle()` only when:

- `has_car`, and
- no car read has been tried yet, or the last try is at least `INTERVAL_CHARGING` (5 min) old, or the read
  was asked for with the car (§3.3).

Otherwise it keeps the last car data (`self._vehicle`). The car's error handling is unchanged.

### 3.3 Reading right away

`NortecGoCoordinator.async_read_now(*, with_car: bool = False)` calls `async_refresh()`, asking the next
read for the car when `with_car`. It is not debounced (see *Facts*).

- `ChargeControl` gets `async_read_now` (without the car) as its `request_refresh`, so every start, stop, stop
  failure and background stop reads right away.
- The Refresh button calls `async_read_now(with_car=True)`, then `async_read_prices()` as today.

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

`docs/releasing.md` → *Bumping `pynortecgo`* gets a checklist for the bump PR:

- Read the new version's exception messages, including wrapped lower-layer errors, and confirm they hold no
  email, password, token, IDs or request bodies (hard rule 5): the integration passes them into logs and
  `ConfigEntry*` errors.
- Check for new exception classes the charger, car, price, start and stop calls can raise, and give each the
  right handling (the charger read's catch-all, §6, only keeps an unknown one from crashing the read).
- Read the client's changelog for breaking changes to the models the entities use.

`.github/pull_request_template.md` gets one checklist line: "`pynortecgo` bump → the checklist in
`docs/releasing.md` → *Bumping `pynortecgo`* done".

## 8. Quality scale

- `entity-unavailable`: stays `done`; its comment adds the *Last read* sensor (and the Refresh button) to
  the entities that stay available after a failed read on purpose.
- `appropriate-polling`: stays `done`; the 30 s interval applies only while a charge is starting or
  stopping.
- No other rule changes.

## 9. Tests

TDD; `pynortecgo` always mocked; fixtures built from `pynortecgo` model objects (hard rule 7).

- **`test_charge_control.py`:**
  - a successful stop sets the pending stop; `NoActiveChargeError` and a failed stop don't; the background
    stop sets it;
  - it ends on a read with `STOPPING`, with `COMPLETED`, with no open charge; not on a read still `CHARGING`
    or `PAUSED`; it ends after 2 minutes with a warning;
  - `turn_off` while pending: no API call; `turn_on` while pending: `ServiceValidationError` with
    `stop_pending`, no `start_charge()`, `start_attempts` unchanged;
  - `is_charge_on` false and `charge_status` `stopping` while pending, `start_blocked` still first;
  - the stored shape is unchanged: an old store loads without a block.
- **`test_coordinator.py`:**
  - `interval_for` for each row of §3.1, including a pending start, a stop asked and a pending stop with a
    `CHARGING` read;
  - after a start, the read right away sets `update_interval` to 30 s;
  - the car is skipped on a read within 5 minutes of the last car read try, read after 5 minutes, and read
    with `async_read_now(with_car=True)`;
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
  - *Supported functionality → Charger*: *Last read* (diagnostic).
  - *Data updates*: the new schedule (30 s / 5 min / 60 min), the car at most every 5 minutes, a read right
    away after a start, a stop or Refresh.
  - *Starting a charge* (or the switch's section): after a stop the switch shows off and *Charge status*
    shows *Stopping* for up to 2 minutes, and a start is refused until then.
  - *Known limitations*: a charge started or resumed outside Home Assistant can take up to 60 minutes to
    show (the unplug-and-replug limitation's "up to 15 minutes" becomes 60).
- `CHANGELOG.md`, *Unreleased*:
  - *Added*: the *Last read* sensor.
  - *Changed*: the polling schedule; the charger device name follows a rename in the app.
  - *Fixed*: the switch no longer turns back on right after a stop; an unexpected client error no longer
    logs a traceback.

## 11. Decisions log

- **D29: Pending stop and fast reads while the charge changes.** After a successful stop the switch shows
  off and *Charge status* *Stopping* until a read sees the charge no longer on, or for 2 minutes; a start is
  refused meanwhile. The charger is read every 30 s while *Charge status* is *starting* or *stopping*, 5 min
  while charging and 60 min otherwise, with the car at most every 5 minutes; a start, a stop and the Refresh
  button read right away, not debounced. This replaces D27's schedule and D26's last sentence (5 min while a
  start is pending). *Why:* the charger reports the old state for about 25 s after a stop, so the switch
  flipped back on; the state should follow an action within seconds, and 30 s reads were seen without a rate
  limit. Source: this spec, *Decisions* and §2–3.
- D27's status becomes `superseded by D29`. D26 stays active: D29 names the one sentence it replaces.

## 12. Verification

- The gates pass locally and in CI; `scripts/smoke` passes.
- The owner's manual test with `scripts/develop`, **only with the owner's explicit OK** (hard rule 2): one
  stop with the switch; it stays off, *Charge status* shows *Stopping*, then the charger's state; *Last read*
  moves every 30 s meanwhile.
