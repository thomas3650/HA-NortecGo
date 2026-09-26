# Read-only entities for EV Smart Charging — design

Date: 2026-09-26 · Branch: `feat/read-only-entities` · Issue: #8

## Goal

- **What:** the second feature. The integration polls the charger, the car and the price forecast, and
  shows them as sensors and binary sensors on a charger device and a car device.
- **Why:** [EV Smart Charging](https://github.com/jonasbkarlsson/ev_smart_charging) can then plan charging
  from Nortec Go's own entities, with no template sensors. It gets a price sensor in its generic format,
  the car's SOC and target SOC, and a "connected" entity that is on only when *our* car is at *our*
  charger, so a guest car can charge normally.
- **Not in this work:** the charge switch (#9), diagnostics (#11), the currency from the API (#20, needs
  NortecGo#47), the manual test guide (#10), an options flow, a refresh button.
- **Done when:** EV Smart Charging accepts the price sensor, the SOC entities and the connected entity in
  the owner's manual test. Built TDD, with `pynortecgo` mocked in every test.

## Decisions

| Topic | Decision |
|---|---|
| Client | `pynortecgo==0.2.0` (already pinned, D21). Only `get_charger()`, `get_vehicle()` and `get_price_forecast()` are called |
| Polling | One `DataUpdateCoordinator` for the charger and the car, whose interval follows the charger's state: 60 / 15 / 5 min (§3.1) |
| Prices | Read on their own schedule: at setup, then 00:05, 05:05, 10:05, 15:05, 20:05 local time (§3.2) |
| Configuration | No options flow and no polling setting. HA doesn't allow integrations to offer scan intervals ([discussion #306](https://github.com/orgs/home-assistant/discussions/306)); a user who wants more reads calls `homeassistant.update_entity` from an automation |
| Refresh button | None. `homeassistant.update_entity` is HA's standard way; on any of our entities it refreshes the coordinator (charger and car). It doesn't re-read prices, which only change on their schedule |
| Price storage | Known slots are saved per entry with `helpers.storage.Store`, so a restart keeps today's earlier slots, which the API can't return |
| Padding | EV Smart Charging's lists are padded to the full day: a missing past slot is `0`, a missing current or future slot is `10` (§3.3) |
| Predictions | Shown. Slots after the published day are predictions (no flag says which); each read replaces them, so `prices_tomorrow` turns into published prices after the 15:05 read |
| Currency | Unit `<hass.config.currency>/kWh`, assuming the forecast is in HA's currency (observed: DKK for DK2). The API's currency comes in v2 (#20) |
| Time | The client's UTC times, written in HA's time zone (`dt_util.as_local`); "today" and "tomorrow" follow HA's time zone |
| Car | A separate car device, not linked under the charger. SOC keeps its last value however old; a diagnostic *Last seen* sensor shows its age |
| Connected | *Connected to charger* is on when the charger's cable is connected **and** the car reports it's plugged in |

Facts about the price data, from the `NortecGo` session (2026-09-26), public-safe:

- The price is the spot price including 25% VAT, per kWh, without fees or grid tariff (the API's own
  wording; not cross-checked against Nord Pool).
- Prices are hourly for now: the four 15-minute slots of an hour share one price. The client returns
  evenly spaced slots or raises `UnexpectedResponseError`; it never returns gaps.
- The forecast starts at the current hour and runs about 7 days ahead. Earlier hours of today are never
  returned. Tomorrow's published prices come out around 13:00 CET.
- Times are UTC. DST days should be 23 or 25 hours with even UTC spacing (not observed yet; next change
  25 Oct 2026).
- The only rate limit seen is on login.

## 1. Files

| File | Change |
|---|---|
| `custom_components/nortec_go/const.py` | Intervals, price read times, padding values (`PAST_SLOT_PRICE = 0.0`, `MISSING_SLOT_PRICE = 10.0`), storage key format and version |
| `custom_components/nortec_go/prices.py` | New. Pure functions on price slots (merge, prune, build a day) and the `Store` wrapper. No coordinator or entity code |
| `custom_components/nortec_go/coordinator.py` | New. `NortecGoData`, `NortecGoCoordinator`: charger and car reads, the interval, the price job, the timers |
| `custom_components/nortec_go/entity.py` | New. `NortecGoEntity` base (charger or car device, `has_entity_name`, unique ID) |
| `custom_components/nortec_go/sensor.py` | New. Current price, Battery, Charge limit, Last seen |
| `custom_components/nortec_go/binary_sensor.py` | New. Cable connected, Charging, Plugged in, Connected to charger |
| `custom_components/nortec_go/entry.py` | `NortecGoConfigEntry = ConfigEntry[NortecGoCoordinator]`, with the coordinator imported under `TYPE_CHECKING` (the lazy `type` alias allows it), so `entry.py` → `coordinator.py` → `entry.py` isn't a runtime cycle |
| `custom_components/nortec_go/__init__.py` | Setup builds the coordinator (§4.1); `PLATFORMS = [BINARY_SENSOR, SENSOR]`; `async_remove_entry` deletes the stored prices |
| `custom_components/nortec_go/strings.json`, `translations/en.json` | `entity` names for every entity (§2) |
| `custom_components/nortec_go/quality_scale.yaml` | §6 |
| `tests/…` | §5 |
| `docs/user/nortec_go.md`, `CHANGELOG.md` | §7 |
| `docs/decisions.md`, `docs/way-of-working.md` | §8 |

## 2. Devices and entities

### 2.1 Devices

| Device | Identifier | Name | Other info |
|---|---|---|---|
| Charger | `(DOMAIN, "<charger id>")` | `Charger.name`, or the entry title when empty | manufacturer "Nortec" |
| Car | `(DOMAIN, "<charger id>_car")` | `Vehicle.name`, or "Car" when empty or not read yet | manufacturer `Vehicle.brand`, model `Vehicle.model` (when not `None`) |

- The car device has no `via_device` link: HA 2026.9 deprecates `DeviceInfo.via_device`, and the car's data
  comes from the cloud, not through the charger.
- The car device is keyed on the charger, not on the car's ID: a different car on the account updates the
  same device and entities instead of leaving a stale one.
- When a car read returns a name, brand or model that differs from the device's, the coordinator updates
  the device in the device registry (with the same fallback for an empty name). This also replaces the
  "Car" placeholder after setup without car data (§4.2).

### 2.2 Entities

All entities use `has_entity_name = True`, a `translation_key`, and the unique ID `<charger id>_<key>`.

| Device | Key | Platform | Device class / unit | Value |
|---|---|---|---|---|
| Charger | `current_price` | sensor | none; `<currency>/kWh`; state class `measurement` | The current slot's price (§3.4). Attributes `prices_today`, `prices_tomorrow` |
| Charger | `cable_connected` | binary sensor | `plug` | `Charger.is_connected` |
| Charger | `charging` | binary sensor | `battery_charging` | `Charger.charge_state == ChargeState.CHARGING` |
| Car | `battery` | sensor | `battery`, `%`, `measurement` | `Vehicle.battery_level` |
| Car | `charge_limit` | sensor | none, `%`, `measurement` | `Vehicle.charge_limit` (EV Smart Charging's target SOC) |
| Car | `last_seen` | sensor | `timestamp`, entity category `diagnostic` | `Vehicle.last_seen` |
| Car | `plugged_in` | binary sensor | `plug` | `Vehicle.plugged_in` |
| Car | `connected_to_charger` | binary sensor | `plug` | see below |

- **`None` values** show as *unknown* (the car doesn't report that field), not unavailable.
- **Connected to charger:** off when the cable isn't connected; otherwise on when `Vehicle.plugged_in` is
  true, off when it's false, and unknown when it's `None`.
- **Current price:** `prices_today` and `prices_tomorrow` are in `_unrecorded_attributes`, so the recorder
  doesn't store about 200 prices every 15 minutes. The state is recorded (history and statistics work).
- **No car:** if the first car read raises `VehicleNotFoundError` or `MultipleVehiclesError`, there is no car
  device and no car entities, and one info line is logged. A car added later appears after a reload.
- **Car not read yet:** after a setup whose car read failed for another reason (§4.2), the car device and
  entities exist, and the car entities are unavailable until the first good car read.
- **`PARALLEL_UPDATES = 0`** on both platforms (read-only, coordinator-driven).

## 3. Data

### 3.1 Charger and car polling

`NortecGoData` is a frozen dataclass: `charger: Charger`, `vehicle: Vehicle | None`. `vehicle` is `None`
until the first good car read. Whether the account has a car at all is a separate coordinator attribute,
`has_car`, set by the first refresh (§4.2) and fixed until a reload; the two differ after a setup whose car
read failed. The coordinator uses `always_update=False`, so an unchanged read doesn't write states again.

Each coordinator update reads the charger, then the car (if `has_car`). After a successful charger read, the
coordinator sets `update_interval`:

| Charger | Interval |
|---|---|
| `is_connected` false | 60 min |
| `is_connected` true and `charge_state` is `STARTING`, `CHARGING` or `STOPPING` | 5 min |
| `is_connected` true otherwise (no charge open, `PAUSED`, unknown) | 15 min |

The first interval (before any read) is 15 min; the first refresh sets the real one. After a failed read the
interval stays as it was.

### 3.2 Price reads

- `get_price_forecast()` with no zone argument (the client uses the charger's zone).
- Read once during setup (§4.1), then by `async_track_time_change(hour=(0, 5, 10, 15, 20), minute=5,
  second=0)` in HA's time zone.
- Each read runs as `entry.async_create_background_task`, so unloading the entry cancels a read in flight.
- After a successful read: merge, prune, save (§3.3), then `coordinator.async_update_listeners()`.
- The price job is independent of the coordinator's update: it doesn't set `last_update_success` and doesn't
  change the interval.

### 3.3 Known slots

- The known slots are a `dict[datetime, float]`: slot start (UTC) to price.
- **Merge:** every slot of a new forecast overwrites the slot with the same start.
- **Prune:** slots that start before local midnight today are dropped.
- **Save:** after each successful read, the pruned slots are saved with `Store` (version 1, key
  `nortec_go.<entry_id>.prices`) as a list of `{start: ISO 8601 UTC, price: float}`. Only prices, no IDs.
- **Load:** at setup, before the first price read; slots before local midnight today are dropped.
  - A missing file gives no known slots.
  - Corrupt JSON is HA's `Store`'s job: it moves the file aside, raises its own repair issue and returns
    `None`, which gives no known slots.
  - Valid JSON of the wrong shape (a missing key, a bad ISO time, a non-number price) is caught in
    `prices.py` (`KeyError`, `TypeError`, `ValueError`): a warning is logged and there are no known slots.
  - Only version 1 exists, so there is no migration.
- **Remove:** `async_remove_entry` removes the file.

### 3.4 EV Smart Charging's lists

Pure functions in `prices.py`, given the known slots, `now` and HA's time zone:

- **A day's slots** are every 15-minute step in UTC from that day's local midnight to the next local midnight:
  96 slots, 92 or 100 on DST days.
- **`prices_today`:** for every slot of today: the known price; if missing, `PAST_SLOT_PRICE` (0) when the
  slot ended at or before `now`, else `MISSING_SLOT_PRICE` (10). Always a full day.
- **`prices_tomorrow`:** if at least one slot of tomorrow is known, every slot of tomorrow, with
  `MISSING_SLOT_PRICE` for a missing one; otherwise `[]`.
- **Entries** are `{"time": <local datetime>, "price": <float>}`, sorted by time. Today's last entry is
  always earlier than tomorrow's first.
- **State:** the known price of the slot that contains `now`, or unknown when that slot isn't known. The
  padding values never appear in the state or its history. (EV Smart Charging takes the current price from
  `prices_today`, not from the state, so an unknown state doesn't stop it; an *unavailable* one would.)
- **Ticks:** `async_track_time_change(minute=(0, 15, 30, 45), second=0)` calls
  `coordinator.async_update_listeners()`, so the state follows the current slot and the lists roll over at
  midnight without an API call.

## 4. Setup, errors and availability

### 4.1 `async_setup_entry`

1. Build the client as today and call `set_charger(int(entry.unique_id))` (D21).
2. Build the coordinator (`config_entry=entry`) and load the stored prices.
3. `await coordinator.async_config_entry_first_refresh()`: errors as in §4.2.
4. Read the prices once (§4.3), awaited here rather than as a background task. A failure other than
   `AuthError` doesn't stop setup.
5. Start the price and tick timers, cancelled with `entry.async_on_unload`.
6. `entry.runtime_data = coordinator`; forward the platforms.

### 4.2 Charger and car read

| Error | First refresh (setup) | Later updates |
|---|---|---|
| `AuthError` (charger or car) | `ConfigEntryAuthFailed`: reauth, setup stops | `ConfigEntryAuthFailed`: the coordinator starts reauth and stops polling. Never retried (hard rule 6) |
| `NortecGoConnectionError`, `RateLimitError`, `ApiError` from the charger | `UpdateFailed`, so `ConfigEntryNotReady`: HA retries setup | `UpdateFailed`: charger and car entities unavailable, logged once, back at the next good read. A `RateLimitError` with `retry_after` passes it on as `UpdateFailed(retry_after=…)` |
| `ChargerNotFoundError`, `UnexpectedResponseError` from the charger | `ConfigEntryError`: setup stops with the reason | `ConfigEntryError`: HA logs it and the entities go unavailable (HA only stops the entry during setup) |
| `VehicleNotFoundError`, `MultipleVehiclesError` from the car | `has_car = False`: no car device (§2.2) | Last car data kept, logged once at warning |
| Any other car error | `has_car = True`, `vehicle = None`: setup continues, the car device is "Car" and its entities are unavailable (§2.2); logged once at warning | Last car data kept, logged once at warning; back at the next good read |

- A failed charger read skips the car read.
- A car error never fails an update: the charger and price entities don't depend on the car.
- Messages pass on `str(err)` only; `pynortecgo` 0.2.0's texts hold no credentials, tokens or IDs (#16).
- HA's coordinator logs the first failure and the recovery once each (`log-when-unavailable`).

### 4.3 Price read

- `AuthError`: during setup `ConfigEntryAuthFailed`; later `entry.async_start_reauth(hass)`.
- Any other error: a warning is logged, the known slots are kept, and the next read is the next scheduled
  time. Setup continues; with nothing stored, `prices_today` is padding only until a read works.

### 4.4 Availability

- Charger entities: available when the coordinator's last update succeeded.
- Car entities: available when the last update succeeded and there is car data (`vehicle` is not `None`).
- Current price: **always available**, independent of the charger read and of whether any slot is known.
  HA writes attributes only for an available entity, and EV Smart Charging rejects an unavailable price
  sensor, so the padded lists (§3.4) must always be there. With no known slots the state is unknown and
  `prices_today` is padding only.

### 4.5 Unload and removal

Unload cancels both timers and any price read in flight, and unloads the platforms. Removing the entry also
removes the stored prices.

## 5. Tests

TDD; `pynortecgo` always mocked; fixtures built from `pynortecgo` model objects (`Charger`, `Vehicle`,
`PriceForecast`, `PriceSlot`) with fake values (hard rule 7). Time is controlled with `freezer` and
`async_fire_time_changed`.

- **`test_prices.py`:** merge overwrites, prune drops yesterday, a full 96-slot day, 0 before now and 10
  from now on, `[]` for an unknown tomorrow and 10 for a gap in a known one, 92 and 100 slots on DST days,
  local times with time zone, today before tomorrow, the state is unknown for a missing slot, store
  round-trip, and a stored file of the wrong shape giving no slots.
- **`test_coordinator.py`:** the interval for each charger state; each row of §4.2 at setup and later;
  `retry_after` passed on; the car read skipped after a charger failure; car data kept on a car error; the
  device registry updated on a car rename and after a setup without car data; price reads at setup and at
  the five times; a failed price read keeps the slots; `AuthError` in a price read starts reauth (and fails
  setup during setup); stored prices loaded at setup; a tick updates the state with no API call.
- **`test_sensor.py`, `test_binary_sensor.py`:** states, units, device classes, entity categories,
  translated names, the two devices and their fallback names, *Connected to charger* in all its cases, no
  car entities without a car, car entities unavailable until the first car read, the lists not recorded,
  Current price available with its lists during a charger failure and with no known slots.
- **`test_init.py`:** existing tests adapted to the coordinator; unload cancels the timers and a price read
  in flight; removal removes the stored prices.
- **Gates:** `CLAUDE.md` → Commands, coverage ≥ 95%.

## 6. Quality scale

Set to `done` when the code meets them: `appropriate-polling`, `common-modules`, `entity-unique-id`,
`has-entity-name`, `entity-unavailable`, `log-when-unavailable`, `parallel-updates`, `devices`,
`entity-device-class`, `entity-category`, `entity-translations`, `docs-data-update`,
`docs-supported-functions`, `docs-supported-devices`, `docs-use-cases` (the EV Smart Charging section),
`docs-examples` (the `update_entity` automation). `entity-event-setup` becomes `exempt` (no event
subscriptions in entities; the timers belong to the coordinator).

## 7. User docs and changelog

- `docs/user/nortec_go.md`:
  - *Prerequisites*: the car is optional. Without a car on the account there is no car device; a car added
    later appears after reloading the integration.
  - *Supported devices*: a Nortec Go charger on a Nortec Go account, and the car linked to that account.
    *Unsupported devices*: more than one charger or car per account.
  - *Supported functionality*: the two devices and their entities (§2).
  - *Use cases*, a new section: using it with EV Smart Charging, which entity goes in which setting
    (price: Current price; SOC: Battery; target SOC: Charge limit; connected: Connected to charger), and why
    a guest car isn't smart charged.
  - *Data updates*: the 60 / 15 / 5 min schedule, the price times, and that `homeassistant.update_entity`
    reads the charger and car now but not the prices.
  - *Automation examples*: an automation that calls `homeassistant.update_entity` on arriving home.
  - *Known limitations*: the price is spot price incl. VAT only (no fees or tariff); the currency is assumed
    to be HA's; tomorrow shows predictions until about 15:05; car data can lag by hours, so *Connected to
    charger* can turn on late; days follow HA's time zone. The "No entities yet" line goes.
- `CHANGELOG.md`, *Unreleased → Added*: the sensors and binary sensors for EV Smart Charging.

## 8. Decisions log and process

- **D22:** polling follows the charger's state (60 / 15 / 5 min), prices are read at fixed times, and there
  is no options flow or refresh button; `homeassistant.update_entity` is the way to read now. *Why:* reads
  match how fast things change (the car mostly stands unplugged), and HA doesn't allow integrations to offer
  polling settings. Source: this spec, *Decisions*.
- **D23:** the price sensor pads EV Smart Charging's lists (0 before now, 10 for a missing current or future
  slot, `[]` for an unknown tomorrow), keeps predicted prices, and saves known slots with `Store`. *Why:* the
  API has no earlier hours of today and EV Smart Charging rejects a short day; past prices never affect a
  plan, a high price keeps it away from unknown slots, and a forecast beats no prices. Source: this spec,
  §3.3–3.4.
- **D24:** issues get one of the labels `v1` (needed for version 1), `v2` (can wait for version 2) or
  `enhancement` (an improvement with no version decided); chores may have none. When in doubt, ask the
  owner. Added to `way-of-working.md` §6 *Backlog*. Source: owner request on 2026-09-26.

## 9. Verification

- The gates pass locally and in CI.
- Manual test by the owner with `scripts/develop` (live data only there; files stay in `config/` and
  `local/`): the entities appear on two devices; EV Smart Charging accepts Current price, Battery, Charge
  limit and Connected to charger. Nothing in this feature starts or stops a charge.
