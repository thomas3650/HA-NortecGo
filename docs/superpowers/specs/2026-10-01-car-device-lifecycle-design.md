# The car device is decided at setup — design

Date: 2026-10-01 · Branch: `feat/car-device-lifecycle` · Issues: #41, #42

## Goal

- **What:** whether the entry has a *Car* device is decided by the setup read alone, and by nothing while
  the integration runs (D44).
  - At setup a failed car read no longer guesses "there is a car": setup is retried until the service
    answers. An account without a car then never gets a *Car* device (#41).
  - While running, a car that goes from the account makes the car entities unavailable and raises a repair
    issue whose fix reloads the integration, which removes the device.
  - A change of car updates the same device, and no longer keeps the old car's brand and model (#42, third
    bullet).
- **Why:** today a network error on the very first car read leaves a no-car account with a *Car* device
  whose entities are unavailable until a reload (#41). And a car removed while running keeps showing its
  last data as if it were fresh (#42).
- **Not in this work:**
  - A car that appears or disappears by itself while running. The owner ruled it out (issue #42,
    2026-10-01): entities never come or go at random times. A car added to the account shows up at the next
    setup (a reload or a restart), as today. So the "appears by itself" and "goes away by itself" parts of
    #42 are deliberately not done, and `dynamic-devices` stays `todo`.
  - Car reads for an account without a car. It makes none after setup, as today.
  - `async_remove_config_entry_device` (a delete button on the device page). The repair's fix covers it.
  - Charge start and stop. `charge_control.py` doesn't use the coordinator's car state and isn't touched.
  - `sensor.py`, `binary_sensor.py`, `entity.py` and `__init__.py`: no code change. The car entities are
    still added by the platforms when `has_car` is true at setup, and `__init__.py` still removes an old car
    device when it is false.
- **Done when:** the cases in §1 and §2 hold in tests with `pynortecgo` mocked, the repair issue and its fix
  work (§3), the docs in §6 are updated, D44 is in `decisions.md`, and the gates pass.

## Decisions

Answered by the owner through the PO (issue #42, 2026-10-01). The owner's answer replaced the three option
sets the team lead had asked about.

| Topic | Decision |
|---|---|
| When car entities are added or removed | Only at setup (first setup, a reload, a restart), never while running (D44) |
| Setup, the service answers "no car" | No *Car* device; one from an earlier setup is removed. As today |
| Setup, the car read fails | Setup fails as it does for the charger read: a retry for a passing error (§1). Fixes #41 |
| Running, account without a car | No car reads. As today |
| Running, a "no car" answer | The car entities go unavailable and a repair issue is raised; nothing is removed (§2, §3) |
| Running, a different car | The same device takes the new car's name, brand and model (§2) |
| `dynamic-devices` | Stays `todo`, with a comment that points to D44 |
| `stale-devices` | `done` (§6): the device is removed at setup, and the repair's fix reloads |
| Release level | Releasing: the title is `feat: …`, with a CHANGELOG entry and the bump step |

"No car" in this spec is the service's own answer to a read that worked: `VehicleNotFoundError` (the account
has no car) or `MultipleVehiclesError` (it has more than one). Both mean "not exactly one car", and the
integration treats them alike everywhere.

Facts used, from the installed Home Assistant source:

- `DataUpdateCoordinator.async_config_entry_first_refresh()` turns an `UpdateFailed` from the read into
  `ConfigEntryNotReady`, and lets `ConfigEntryAuthFailed` and `ConfigEntryError` through.
- After `ConfigEntryNotReady`, Home Assistant sets the entry up again by itself: after about 5 s, then 10 s,
  20 s and so on, doubling up to 10 minutes between tries (`config_entries.py`, `SETUP_RETRY_MAX_WAIT`).
  Each try runs `async_setup_entry` from the top, with a new client and coordinator.
- `DeviceRegistry.async_get_or_create` takes `None` for `manufacturer` and `model`, which is a value of its
  own next to `UNDEFINED` ("leave as it is").
- An issue created with `is_persistent=False` is gone after a Home Assistant restart. A fix flow that ends
  with `async_create_entry` deletes its issue.

## 1. The setup read

The setup read is the coordinator's first read: the one made by `async_config_entry_first_refresh()`, while
the coordinator has no data yet. It reads the charger and then the car, as today. New is what a failed car
read does.

| The car read at setup | Today | New |
|---|---|---|
| One car | `has_car` true; device and entities | Unchanged |
| "No car" | `has_car` false; no device, an old one is removed; one info line | Unchanged |
| `AuthError` | Reauth (`ConfigEntryAuthFailed`, `auth_failed`) | Unchanged |
| `RateLimitError` | `has_car` true, car entities unavailable | Setup is retried (`UpdateFailed`, `rate_limited`) |
| `NortecGoConnectionError` | as above | Setup is retried (`UpdateFailed`, `cannot_connect`) |
| `ApiError` | as above | Setup is retried (`UpdateFailed`, `api_error`) |
| `UnexpectedResponseError` | as above | Setup fails (`ConfigEntryError`, `unexpected_response`) |
| any other `NortecGoError` | as above | Setup is retried (`UpdateFailed`, `car_read_failed`) |

- These are the charger read's rows (#37), with the same translation keys, so the entry shows the same
  texts. Two differences: there is no `charger_not_found` row, and the last row has a text of its own
  (§4), because `read_failed` says "Reading the charger failed".
- The errors are chained (`from`) to the client's error, and the client's text goes only to the debug log,
  as for the charger read.
- So after a setup that worked, `has_car` true means the car has been read: `data.vehicle` is set. The
  state "a car is expected but hasn't been read" no longer exists, and neither does the `_car_checked` flag.
- `has_car` is set by the setup read and doesn't change until the next setup.
- **#41:** on an account without a car, a first car read that fails is retried, and the retry gets the "no
  car" answer. The entry never loads with a *Car* device.

**What it costs.** The car read now counts at setup as the charger read does.

- A passing failure of the car read at startup (a network blip between the two reads, a rate limit, a
  server error) delays the whole entry, not only the car: the charger's entities, the prices and the
  *Charge* switch are unavailable until a retry works. Home Assistant retries by itself, first after about
  5 seconds. Today the entry loads and only the car entities wait.
- Each retry reads the charger again, so it is one extra charger request per retry.
- `UnexpectedResponseError` from the car read fails setup without a retry, as it does from the charger read.
  If the service changes the car's data so that the client can't read it, the whole integration stays down
  until an update, where today only the car entities would be unavailable. This follows the owner's rule
  not to guess; the alternative (load with a car device whose entities are unavailable for this one error)
  would keep a second path alive for a case that hasn't been seen.
- An account without a car pays nothing new: one car read per setup, as today.

## 2. While running

An account without a car (`has_car` false) makes no car reads. An account with a car is read as today: with
a charger read, at most about every 5 minutes, and on every *Refresh* (D29).

| The car read while running | Today | New |
|---|---|---|
| One car | The car's data; the device's name, brand and model are updated | As today, and a brand or model the car lacks is cleared on the device |
| "No car" | The last data is kept as if fresh; one warning | The car is *gone*: its entities go unavailable, a repair issue is raised (§3), one warning |
| `AuthError` | Reauth | Unchanged |
| any other `NortecGoError` | The last data is kept; one warning | Unchanged |

**Gone.** The coordinator gets one new state, *the car is gone*, from a "no car" answer until the next good
car read. While it holds:

- `data.vehicle` is `None`, which is what makes the car entities unavailable (`NortecGoCarEntity.available`
  is unchanged). The last car data is dropped: it belongs to a car that isn't there.
- The device and its entities stay in the registries, with the owner's renames, areas and settings.
- `has_car` stays true, and the car is still read at its usual pace. Any other car error in between changes
  nothing: the car stays gone.
- A good car read ends it: the entities are available again with the car's data, the repair issue is
  deleted, and the existing info line "Reading the car works again" is logged. This covers a car that comes
  back and a second car that is removed again.
- A reload or a restart ends it too: setup decides again (§1), and removes the device if the answer is
  still "no car".

`car_read_failing` keeps its meaning (from the first failed car read to the next good one, whatever the
error), and a new read-only property `car_gone` tells the gone state. Diagnostics add `car_gone` next to
`has_car` and `car_read_failing`.

**Logging.** A "no car" answer logs one warning that says the account no longer has exactly one car and
that the car's entities are unavailable. It is logged once per gone state, also when a warning for another
car error was logged just before. The other lines are as today.

**A different car.** The device is keyed on the charger, not on the car, so a new car on the account is the
same device, and the entities' unique IDs don't change. On every good car read the device takes the car's
name, brand and model:

- The name as today: the car's name, or the translated *Car* when it has none. A name the owner gave the
  device in Home Assistant still wins.
- The brand and model are written as they are, also when the car has none. Today a missing one is skipped,
  so a new car without a brand keeps the old car's.
- No vehicle ID is stored or compared: writing the three values on every good read is enough, and the
  registry only saves when one differs.
- Entities, history and the owner's settings carry on. Entity IDs keep the old car's name until the owner
  renames them; Home Assistant never renames entity IDs by itself.

The update still does nothing when the device doesn't exist yet (the setup read runs before the entities
create it).

## 3. The repair issue

Raised when the car goes (§2), so the owner sees why the car entities are unavailable and can remove them.

- **Issue:** ID `car_gone_<entry ID>`, translation key `car_gone`, severity warning, fixable, not
  persistent, with the entry's title as `{name}` and the entry ID in its data. The ID's format is a
  constant in `const.py`, next to `START_BLOCKED_ISSUE_ID`.
- **Deleted** by a good car read (§2), and when the entry unloads (a reload, a disable, a removal), through
  `entry.async_on_unload`. So it never outlives the coordinator that raised it, and a setup starts without
  one. Not persistent, so a restart drops it as well; setup then decides.
- **Fix flow:** one confirm step, in `repairs.py`. Submit schedules a reload of the entry
  (`hass.config_entries.async_schedule_reload`) and ends the flow. The reload's setup read then decides: the
  device is removed when the answer is still "no car", and stays when the car is back.
  - If the entry no longer exists, the flow aborts with the reason `entry_not_found`.
  - `async_create_fix_flow` picks the flow by the issue ID: `car_gone_…` gets this flow, everything else
    the start-block flow, as today.
- The fix is the owner's own action, so it doesn't break the rule that nothing is removed at a random time.

## 4. Texts

`strings.json` and `translations/en.json` (the same content) get:

| Key | Text |
|---|---|
| `exceptions.car_read_failed.message` | Reading the car failed. Home Assistant will try again. |
| `issues.car_gone.title` | The car of {name} is no longer on the Nortec Go account |
| `issues.car_gone.fix_flow.step.confirm.title` | Remove the car of {name} |
| `issues.car_gone.fix_flow.step.confirm.description` | The Nortec Go account no longer has exactly one car, so the car's entities are unavailable.\n\nIf the car comes back on the account, they work again by themselves and this notice goes away. To remove the car device and its entities now, select **Submit**: the integration reloads. |
| `issues.car_gone.fix_flow.abort.entry_not_found` | The Nortec Go entry no longer exists. |

## 5. Code

| File | Change |
|---|---|
| `coordinator.py` | The car read: the setup rows of §1, the gone state and its issue of §2 and §3, the brand and model of §2, the `car_gone` property; `_car_checked` goes. The charger read's error mapping in `_async_update_data` may be shaped so the car's setup read reuses it. Nothing else in the file changes: not the price reads, the intervals, or `async_read_now` |
| `const.py` | `CAR_GONE_ISSUE_ID` |
| `repairs.py` | The reload flow and the choice by issue ID (§3) |
| `diagnostics.py` | `car_gone` |
| `strings.json`, `translations/en.json` | §4 |
| `quality_scale.yaml` | §6 |

The read-only entities spec (§2.2 and §4.2 there) describes the behaviour this replaces. It is a snapshot
and isn't edited; D44 records the change.

## 6. Docs and the quality scale

- **`docs/user/nortec_go.md`:**
  - *Prerequisites*: a car added to the account appears after a reload (as now), and so does one removed.
  - *Car*: drop the paragraph about a car that hasn't been read yet (the *Car* placeholder name, the
    `car_` entity IDs): that state is gone. Keep "Values the car doesn't report show as unknown". Add: if
    the car goes from the account, the car's entities are unavailable and a repair notice offers to remove
    them; after a change of car the device takes the new car's name, brand and model, and the entity IDs
    keep the old name until you rename them.
  - *Known limitations*: replace "A car removed from the account … disappears after you reload" with the
    rule: the car device is added and removed only when the integration starts (a reload or a restart).
  - *Troubleshooting*: a short entry for the repair notice, by its title.
- **`CHANGELOG.md`**, under *Unreleased*:
  - *Fixed*: an account without a car no longer keeps an unavailable *Car* device after a failed first car
    read (#41); a change of car no longer keeps the old car's brand and model.
  - *Changed*: if the car can't be read when the integration starts, the start is retried; a car removed
    from the account makes its entities unavailable and raises a repair notice.
- **`docs/decisions.md`:** D44 (below).
- **`quality_scale.yaml`** and `tests/test_quality_scale.py`:
  - `dynamic-devices`: `todo`, with the comment "Deliberately not done (D44): car entities are added only
    at setup, so a car added to the account shows up after a reload."
  - `stale-devices`: `done`, with the comment "The car device is removed at setup when the account has no
    single car. A car that goes while running raises a repair issue whose fix reloads the entry, which
    removes it (D44)."
    The rule text asks that a device removed from the account is removed from Home Assistant, and accepts
    two ways: automatically, or by the user's own action (its `async_remove_config_entry_device` example).
    Here the integration knows the car is gone, tells the owner, and removes the device on the owner's
    confirmation; without that, at the next start. That is the rule's second way with a more visible
    control, so the rule is met. If the owner reads the rule as "automatically whenever the integration can
    know", the status is `todo` with the same comment, and nothing else in this spec changes.
- **`docs/manual-testing.md`:** no change. The car checklist's rows still hold, and the repair can't be
  provoked without removing the car from the real account.

D44, as it goes into `decisions.md`:

```markdown
### D44: The car device is decided at setup
- **Date:** 2026-10-01 · **Status:** active
- **Decision:** Car entities are added and removed only at setup (first setup, a reload, a restart), never
  while running. A failed car read at setup fails setup like a failed charger read, so setup is retried
  rather than guessing. While running, a "no car" answer makes the car entities unavailable and raises a
  repair issue whose fix reloads the entry; a different car updates the same device.
- **Why:** The owner wants no entities to appear or disappear at random times, and a guessed car left
  no-car accounts with a dead device (#41).
- **Source:** [car device lifecycle spec](superpowers/specs/2026-10-01-car-device-lifecycle-design.md),
  Decisions; owner answer on issue #42
```

## 7. Tests

All with `pynortecgo` mocked, and cars built with `make_vehicle` (hard rule 7).

- **`test_coordinator.py`:**
  - Setup: each row of §1. For the retried rows: the entry is in `SETUP_RETRY` with the row's translation
    key, no *Car* device exists, and after the retry time a "no car" answer loads the entry without a car
    (#41) and a good answer loads it with one. `UnexpectedResponseError` gives `SETUP_ERROR`. The client's
    text is in the debug log and not in the entry's reason.
  - `test_car_error_at_setup_continues` goes: its case is now a retry.
  - Running: a "no car" answer (both errors) sets `data.vehicle` to `None`, `car_gone` and
    `car_read_failing`, keeps `has_car` and `last_update_success` true, and logs the warning once over
    several reads. Another car error while gone keeps it gone. A good read ends it and logs the recovery.
    Another car error without a "no car" answer keeps the last data, as today
    (`test_later_car_error_keeps_car_data`, split into its two cases).
  - The device: a car with another name, brand and model updates the device; a car without a brand or a
    model clears them; the owner's own device name stays.
- **Entities** (`test_sensor.py`, `test_binary_sensor.py` or `test_init.py`, where the car entities are
  tested today): the five car entities are unavailable while the car is gone and are still registered; they
  have values again after a good read.
- **The issue** (`test_repairs.py`, `test_coordinator.py`): raised on a "no car" answer with the right ID,
  key, severity and placeholders; deleted by a good read and by an unload; not raised at setup. The fix
  flow: confirm reloads the entry, and with a "no car" answer at that setup the *Car* device and its
  entities are gone and the issue with them; with the car back they stay. The flow aborts when the entry is
  gone. The start-block issues still get their own flow.
- **`test_diagnostics.py`:** `car_gone` is in the output.
- **`test_init.py`:** `test_reload_without_car_removes_car_device` stays as it is.
- **`test_quality_scale.py`:** `stale-devices` is `done`.
- The coverage gate stays at 95%.
