# Total energy — design

Date: 2026-10-01 · Branch: `feat/total-energy` · Issue: #75

## Goal

- **What:** a *Total energy* sensor on the charger device: the energy the charger has delivered since the
  sensor was added, in kWh. It never goes down while its stored ledger lasts (it restarts at 0 only when
  the integration is removed and added again, or the ledger's file is unreadable), so it can be the
  charger's individual device in the Energy dashboard.
- **Why:** the owner wants the charger's consumption in the Energy dashboard (#75). *Energy this charge*
  restarts with every charge, so the dashboard can miss a charge, and it never sees the energy delivered
  after a charge's last read.
- **How, in one line:** the integration keeps a stored ledger. Each completed charge is counted once, by
  its charge ID, at the final energy `pynortecgo` reports; the open charge is counted at its live energy.
- **Not in this work:**
  - a `pynortecgo` bump: 0.8.0 has every field used here (0.9.0 adds only the charges' start times);
  - a change to *Energy this charge*, to the polling intervals or to the number of requests;
  - anything near starting or stopping a charge;
  - a lifetime figure from before the sensor was added.
- **Done when:** built TDD with `pynortecgo` mocked in every test; the gates pass; the user docs, the
  manual test guide, the HA notes, the changelog and the decision log are updated.

## Decisions

The owner's answers in the brainstorm (2026-10-01), and the controller's choices the owner agreed to there.
The owner let the controller approve this spec and its plan once `full-reviewer` rates them Ready, and
reviews the final PR.

| Topic | Decision |
|---|---|
| Where the total comes from | The integration sums it from the per-charge energy. The client can't expose a lifetime meter (the owner's answer), so this replaces the owner's earlier answer on #75 to wait for one. thomas3650/nortecgo#79 can be closed; the owner closes it |
| Where it starts | At 0. A charge completed before the ledger was created is never counted at its final energy. A charge open at the first read counts in full |
| The total never goes down | The controller's choice after the spec review: an open charge keeps the highest reading seen, and a completed charge counts at the higher of its final energy and that reading (§2). In the brainstorm the owner was told the total could step down slightly; this removes that case, and the PR description says so |
| A charge whose final record never arrives | It keeps its last live reading (the owner's answer). The total never drops because a record is missing |
| Where the state lives | A ledger in Home Assistant's storage, one file per config entry, updated in the coordinator's read path. Not the sensor's restore state: that is saved only every 15 minutes and at a clean stop, and stops while the entity is disabled |
| State class | `total_increasing` (§4) |
| *Energy this charge* | Unchanged. The docs say to use *Total energy* in the Energy dashboard, not both |
| Diagnostics | The ledger is shown, unredacted (D38: only the sign-in secrets) |
| Decision log | D47 (§9) |
| PR title | `feat`, releasing: a minor version |

Facts used, public-safe:

- `pynortecgo` 0.8.0, from its docstrings:
  - `Charger.active_charge` is the open charge, or `None`. `ActiveCharge.id` is the charge ID.
    `ActiveCharge.kwh` is the delivered energy so far; it can lag the latest measurement slightly, and it
    is `None` when the charge has no energy reading.
  - `Charger.last_charge` is the most recent completed charge on the charger, a `CompletedCharge` with
    `id`, `kwh` and `completed_at` (UTC). During a charge it is the previous one. While a charge is
    stopping it can already be the open charge (`active_charge.id == last_charge.id`). It is `None` when
    none is among the charger's newest charges, or when its read failed.
- Home Assistant's Energy docs and FAQ: an energy sensor needs `device_class` `energy`, `state_class`
  `total` or `total_increasing`, and an energy unit. An individual device takes one energy sensor and,
  optionally, a power sensor (`device_class` `power`, `state_class` `measurement`).
- Home Assistant 2026.9.4, the sensor recorder (read in the installed version), for `total_increasing`:
  - non-numeric states (unknown, unavailable) are skipped;
  - a value below 90% of the previous one starts a new cycle: the sum carries on and the new value is added
    in full. The test is against the sensor's whole value, so on a small total a small drop is a new cycle
    too, and the whole total is added again;
  - a smaller drop is a dip: its negative change is added to the sum. From an entity's second dip after a
    start, Home Assistant logs a warning, once per run, that asks the user to report it to the
    integration.
  So a `total_increasing` value should never go down by itself. For `total` without `last_reset`, every
  drop is a negative change, so a restart from 0 would take the whole earlier total off the sum.
- On a first add, the sensor's first state sets the statistics' zero point, so the Energy dashboard counts
  from there. After a restart from 0 the first state starts a new cycle and is added in full.
- One charge is open on a charger at a time, and after a stop the cable must be replugged before the next
  start. So two charges never overlap, and minutes pass between one charge's end and the next one's start.

## 1. Files

| File | Change |
|---|---|
| `custom_components/nortec_go/energy.py` | New: the ledger, the counting rule and the store (§2) |
| `custom_components/nortec_go/const.py` | The store's version and key (§2) |
| `custom_components/nortec_go/coordinator.py` | Loads, advances and saves the ledger; the total in its data (§3) |
| `custom_components/nortec_go/__init__.py` | Loads the ledger at setup; deletes its file with the entry (§3) |
| `custom_components/nortec_go/sensor.py` | The sensor (§4) |
| `custom_components/nortec_go/costs.py` | Its module docstring (below) |
| `custom_components/nortec_go/diagnostics.py` | The ledger (§5) |
| `custom_components/nortec_go/strings.json`, `translations/en.json` | The name (§4) |
| `docs/user/nortec_go.md` | §6 |
| `docs/manual-testing.md`, `docs/ha-notes.md` | §7 |
| `CHANGELOG.md` | §8 |
| `docs/decisions.md` | D47 (§9) |
| `tests/test_energy.py` (new), `tests/test_coordinator.py`, `tests/test_sensor.py`, `tests/test_diagnostics.py`, `tests/test_init.py` | §10 |

`manifest.json`, `pyproject.toml`, `uv.lock`, `charge_control.py` and `quality_scale.yaml` don't change.
`costs.py` changes only in its module docstring, which calls it the one place that reads
`Charger.last_charge`: it becomes the one place that reads the charges' costs. No rule in `quality_scale.yaml` changes status.

## 2. `energy.py`

Shaped like `prices.py`: pure functions over the ledger, and the store class.

### The ledger

Two frozen dataclasses.

`ProvisionalCharge`: a charge counted at its live reading, waiting for its final record.

| Field | Type | Meaning |
|---|---|---|
| `id` | `str` | The charge ID |
| `kwh` | `float` | The highest live reading seen; 0.0 until it has one |
| `seen_at` | `datetime` | When it was last seen open (UTC) |

`EnergyLedger`:

| Field | Type | Meaning |
|---|---|---|
| `since` | `datetime` | When the ledger was created (UTC). A charge completed at or before it is never counted by step 1 |
| `settled_kwh` | `float` | The sum of the charges counted in step 1 (at their final energy, or at their highest reading if that is higher), and of those folded in at their highest reading |
| `settled_id` | `str \| None` | The last completed charge counted; `None` until there is one |
| `settled_at` | `datetime \| None` | That charge's completion time |
| `provisional` | `tuple[ProvisionalCharge, ...]` | In the order they were first seen |

### The functions

- `new_ledger(now: datetime) -> EnergyLedger`: `since=now`, 0.0, no settled charge, no provisional ones.
- `total_kwh(ledger: EnergyLedger) -> float`: `settled_kwh` plus the `kwh` of every provisional charge.
- `advance(ledger: EnergyLedger, charger: Charger, now: datetime) -> EnergyLedger`: the counting rule. It
  returns the ledger it was given, unchanged, when nothing changes.

### The counting rule

`advance` takes `last = charger.last_charge` and `active = charger.active_charge`, and does two steps in
this order.

1. **The completed charge.** `last` counts when it is not `None`, `last.id != settled_id`, and
   `last.completed_at` is later than `settled_at` (than `since` while `settled_at` is `None`). Then:
   - a provisional charge with `last.id` is removed, and `settled_kwh` grows by the higher of `last.kwh`
     and that charge's `kwh`: the final energy replaces the live reading, but the total doesn't go down.
     Without such a provisional charge, `settled_kwh` grows by `last.kwh`;
   - `settled_id` and `settled_at` become `last.id` and `last.completed_at`;
   - every other provisional charge is **folded** when it is not the open charge (`active` is `None` or has
     another ID) and its `seen_at` is before `last.completed_at`: `settled_kwh` grows by its `kwh`, and it
     is removed. Such a charge was open before `last` completed, so it is the older of the two, and the
     client will never list it as the last completed charge again.
2. **The open charge.** When `active` is not `None` and `active.id` is not `settled_id` (as step 1 left
   it), the charge is provisional:
   - if it is already there, its `seen_at` becomes `now`, and its `kwh` becomes `active.kwh` when that is
     not `None` and is higher;
   - otherwise it is added at the end, with `active.kwh` (0.0 for `None`) and `seen_at=now`.

When no charge is open, step 2 does nothing: a charge that just closed stays provisional until step 1
removes or folds it.

How the cases come out:

| Case | Result |
|---|---|
| A normal charge | Live while open; the final energy replaces it at the first read that lists the charge as completed |
| The charge closed and isn't listed yet (up to 60 minutes) | The total stays at the live reading. No drop, nothing counted twice |
| Stopping, and already listed as completed | Step 1 counts the final energy; step 2 skips the charge, on this read and on later ones |
| Two charges end between two reads | The newer one counts at its final energy; the older is folded at its live reading |
| A charge ran entirely while Home Assistant was off, and is still the newest | Counted in full by step 1 |
| A charge was never seen open (it ran while Home Assistant was off, or between two reads), and a later charge has completed too by the next read | Missed (a known limitation, §6). If the later charge is still open at that read, the earlier one is still listed and counts |
| An older charge is listed late: P waits; X opens, is seen and closes; then P is listed | P counts at its final energy. X was seen open after P completed, so it is not folded; its final energy replaces its reading when X is listed |
| A new charge opens while the previous one waits, and the previous one's record arrives during the new charge | The previous charge counts at its final energy; the new one stays provisional and is not folded |
| The charge's energy reading goes down, or its final energy is below the highest reading | The total stays; the highest reading counts |
| The completed charge's read fails for a while (`last_charge` is `None`) | Nothing changes, and when it is back the ID and time checks keep a counted charge from counting again |
| A restart with a charge open | The stored ledger carries it |
| An open charge without an energy reading | Its highest reading stays; 0.0 if it never had one |
| A charge completed before the ledger was created | Not counted by step 1, also when it is first listed later |
| A charge that ended at or before `since` is still shown open at the first read | Step 2 makes it provisional, so it counts at its live reading; step 1 never counts it. A later completed charge folds it |

What the rule assumes and accepts:

- An older completed charge listed after a newer one fails step 1's time check and is ignored.
- `completed_at` is when the charge ended, or when the charger released it; the rule holds with either.
  Home Assistant's clock and those times must agree to within the gap between two charges (minutes, see
  *Facts used*). Otherwise a waiting charge could be folded too early, and counted again when its record
  arrives. No guard is added.
- Only step 1 removes provisional charges, and only when a completed charge counts. So while `last_charge`
  gives nothing to count (its read keeps failing, or no charge is among the charger's newest), each charge
  adds an entry that stays. The list is not capped: a cap could fold a charge whose record still arrives,
  and count it twice. The first completed charge that counts folds all the older entries, and the total is
  the same either way.

The total never goes down, apart from the noise of adding floats: `settled_kwh` only grows, a provisional charge's `kwh` only grows, and a
provisional charge leaves the list only as it is added to `settled_kwh` with at least its `kwh`.

### The store

`EnergyStore`, like `PriceStore`: a `Store[dict[str, Any]]` with `ENERGY_STORE_VERSION = 1` and
`ENERGY_STORE_KEY = "nortec_go.{entry_id}.energy"`, both in `const.py`.

- `async_load() -> EnergyLedger | None`: the stored ledger. `None` when there is no file, and `None` with a
  warning ("Ignoring the stored energy total: it has an unexpected shape") when the file has the wrong
  shape: a missing key, a wrong type, a time that doesn't parse, or a time without a time zone.
- `async_save(ledger: EnergyLedger) -> None`
- `async_remove() -> None`

The file holds the ledger's fields under their own names, times as ISO 8601 strings, and `provisional` as a
list of objects.

## 3. The coordinator and setup

- `NortecGoCoordinator` gets `_energy_store` and the ledger, with a read-only property `energy_ledger`
  for the diagnostics. Until `async_load_energy()` runs, the ledger is `new_ledger(dt_util.utcnow())`, as
  `known_prices` starts empty; nothing reads or saves that one.
- `async_load_energy()`: loads the ledger. When the store gives `None`, it makes a new one with
  `new_ledger(dt_util.utcnow())` and saves it at once. Saved at once, so that `since` survives a restart
  that comes before the first charge: a charge that then runs while Home Assistant is off still counts.
  `async_setup_entry` calls it after `async_load_prices()`, before the first refresh.
- `_async_update_data`, as its last step before it builds `NortecGoData`, so after the car read: `advance`
  with the charger and the read's time (`read_at`). When the result differs from the ledger, the
  coordinator keeps it and saves it, awaited in the read. While a charge is open that is a save per read,
  as `seen_at` moves.
- `NortecGoData` gets `total_energy_kwh: float`, set from `total_kwh` of the ledger after the advance. A
  failed charger read, and a car read that fails the whole read (a rejected sign-in, or a failed car read
  at setup), raise before this, so the ledger doesn't move on a read that fails. The next good read
  catches up: `advance` loses nothing by running later.
- A file of the wrong shape gives a new ledger, so *Total energy* restarts at 0. The recorder sees a new
  cycle, and the earlier statistics stay.
- `async_remove_entry` also removes the energy store's file.

Nothing in the read path gets a new exception, a new request or a new interval.

## 4. The sensor

One new class in `sensor.py`, `NortecGoTotalEnergySensor`, a `NortecGoChargerEntity`; `async_setup_entry`
always adds it.

| Key | Name | Device class | State class | Unit | Display precision |
|---|---|---|---|---|---|
| `total_energy` | Total energy | `energy` | `total_increasing` | kWh | 2 |

- **Unique ID:** `<charger id>_total_energy`, as the base entity makes it.
- **Value:** `coordinator.data.total_energy_kwh`, rounded to 3 decimals, so the state doesn't carry the
  noise of adding floats.
- **Availability:** the base behaviour: unavailable after a failed charger read, like the other charger
  sensors. The recorder skips those states.
- **Category and default:** no entity category, enabled by default.

The module docstring of `sensor.py` and the docstring of `async_remove_entry` list what they cover; both
get the new sensor and the new store.

Why `total_increasing` and not `total`: the value restarts at 0 when the integration is removed and added
again (the entity ID, and so the statistics, are usually the same), or when the store file is unreadable.
`total_increasing` makes that a new cycle and keeps the sum; `total` would take the whole earlier total
off it. `total_increasing` in turn needs a value that never goes down by itself (see *Facts used*), which
§2's rule gives.

## 5. Diagnostics

The download gets a top-level `energy` key, next to `prices`, with the ledger as `asdict` gives it. Nothing
in it is redacted (D38). It only exists for a loaded entry, like `data` and `prices`.

## 6. User docs

`docs/user/nortec_go.md`:

- *Supported functionality* → *Charger*:
  - a new row after *Energy this charge*:

    > | Total energy | Sensor | The energy the charger has delivered since you added the integration, in kWh, kept across restarts. Use it for the Energy dashboard (see *Use cases*) |

  - in the *Energy this charge* row, the sentence on the Energy dashboard becomes:

    > For the Energy dashboard, use *Total energy*.

- *Use cases*, a new section after *Smart charging with EV Smart Charging*:

  > ### The charger in the Energy dashboard
  >
  > In **Settings** > **Dashboards** > **Energy**, add an individual device with *Total energy* as its
  > energy sensor and, if you like, *Charging power* as its power sensor.
  >
  > Don't add *Energy this charge* as well: the charger would be counted twice. If you added it before
  > *Total energy* existed, replace it.

- *Data updates*, after the sentence on *Last charge cost*:

  > *Total energy* follows the same reads. While a charge runs it grows with *Energy this charge*. When the
  > charge ends, it moves up to the charge's final energy at the read that first lists the charge as
  > completed (see *Known limitations* for when that doesn't happen).

- *Known limitations*: the paragraph that starts "The Energy dashboard sees a new charge only when" is
  replaced by:

  > - *Total energy* misses the end of a charge when a newer charge has completed before the charger was
  >   read again (two charges end between two reads, or a newer charge ends while Home Assistant is off).
  >   The older charge then keeps its highest reading, and the energy delivered after that reading isn't
  >   counted.
  > - A charge that the integration never read while it was open (it started and ended between two reads,
  >   which are up to 60 minutes apart, or while Home Assistant was off) is counted only if it is still the
  >   charger's most recent completed charge at the next read.
  > - *Total energy* starts at 0 when you add the integration, and again if you remove the integration and
  >   add it back. The Energy dashboard keeps its history.
  > - *Total energy* never goes down. In the rare case that a charge's final energy is below a reading taken
  >   while it ran, the reading counts.
  > - *Energy this charge* restarts with every charge, so it isn't meant for the Energy dashboard: a charge
  >   that follows a very short one, or that is first read late, can be missed there.

- *Diagnostics*: the sentence on what the file keeps becomes:

  > It keeps your charger's and car's names and IDs, the last charge's ID, cost, energy and time, and the
  > IDs, energy and times behind *Total energy*. …

## 7. The manual test guide and the HA notes

- `docs/manual-testing.md` → *Entities*, under *Charger*: one line, *Total energy*, after *Energy this
  charge*, in the form of the lines there. And in *Pitfalls*, where it covers deleting and re-adding the
  entry: one clause that this also restarts *Total energy* at 0.
- `docs/ha-notes.md`, the paragraph on `total_increasing`, gets the three recorder facts in *Facts used*
  that it doesn't have yet: the 90% test is against the whole value; a dip's negative change is added to
  the sum; the dip warning comes from an entity's second dip after a start, once per run, and asks the user
  to report it to the integration. And the rule that follows: a value that can restart from 0 (a lost
  store) is `total_increasing`, because plain `total` would count the restart as a negative change, and a
  `total_increasing` value must never go down by itself.

## 8. Changelog

Under *Unreleased*:

> ### Added
>
> - *Total energy*: the energy the charger has delivered since you added the integration, kept across
>   restarts. Use it as the charger's individual device in the Energy dashboard, instead of *Energy this
>   charge*.

## 9. Decision log

```markdown
### D47: Total energy is summed in the integration
- **Date:** 2026-10-01 · **Status:** active
- **Decision:** *Total energy* is summed by the integration from the per-charge energy `pynortecgo`
  reports, in a stored ledger that starts at 0: each completed charge once, by its charge ID, at its final
  energy, and the open charge at its live reading. It is `total_increasing` and never goes down: a charge
  whose final record never arrives, or is lower, keeps its highest live reading.
- **Why:** The client can't expose a lifetime meter (the owner, #75), and *Energy this charge* restarts
  with every charge, so the Energy dashboard can miss charges. This replaces the owner's earlier answer on
  #75 to wait for the client.
- **Source:** [total energy spec](superpowers/specs/2026-10-01-total-energy-design.md), Decisions and §2
```

## 10. Tests

`pynortecgo` is mocked in every test, and fixtures are built from its model objects with `make_charger` and
`make_completed_charge` (hard rule 7). `make_charger` gets one keyword argument, `charge_id: str =
FAKE_CHARGE_ID`, used as the open charge's ID, so a test can open a second charge.

`tests/test_energy.py`:

- `new_ledger` and `total_kwh`.
- `advance`, one test per row of §2's case table, each as a sequence of reads with the total checked after
  every read. Also:
  - the same read twice returns the same ledger object the second time when no charge is open;
  - a completed charge with `completed_at` equal to `since` doesn't count;
  - the open charge is never folded, even with a `seen_at` before the completed charge's time;
  - the total after every read of every test, rounded to 3 decimals as the sensor does, is at least the
    rounded total before it.
- `EnergyStore`: a ledger with a settled charge and two provisional ones survives save and load; no file
  gives `None`; each wrong shape (a missing key, a wrong type, a time that doesn't parse, a time without a
  time zone) gives `None`
  and the warning; `async_remove` deletes the file.

`tests/test_coordinator.py`:

- a first setup creates a ledger with `since` at the setup time and saves it before any charge;
- a stored ledger is loaded at setup and its total is in the first data;
- a read that changes nothing doesn't save; a read with an open charge saves;
- a failed charger read leaves the ledger and the file as they were, and so does a later read whose car
  read is rejected (a sign-in failure);
- a file of the wrong shape gives a new ledger and the total 0.0.

`tests/test_sensor.py`:

- the sensor exists on the charger device with its unique ID, device class `energy`, state class
  `total_increasing`, the unit kWh, display precision 2 and no entity category;
- its value across a charge: growing while open, steady when the charge has closed and isn't listed, the
  final energy once it is;
- its value is rounded to 3 decimals;
- it is unavailable after a failed charger read.

`tests/test_diagnostics.py`: the expected outputs for a loaded entry get the `energy` key; an entry that
isn't loaded has none.

`tests/test_init.py`: removing the entry deletes the energy store's file.
