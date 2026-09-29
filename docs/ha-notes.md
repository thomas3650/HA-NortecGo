# Home Assistant and HACS notes

Learned facts about building and testing this integration on Home Assistant and HACS, newest last within
each section. Small facts that fit no doc stay in [`notes.md`](notes.md).

## Loading and manifest

- Setting up a config entry always imports the integration's `config_flow` platform, even with
  `"config_flow": false`. An integration with no config flow yet uses `async_setup` with
  `CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)` instead of an empty entry.
- `pytest-homeassistant-custom-component` ships its own `custom_components` package. HA only finds ours if a
  test imports `custom_components.nortec_go` first.
- hassfest requires the `manifest.json` keys in the order `domain`, `name`, then alphabetical.

## Config flows

- `strings.json` in a custom integration holds literal text only. `[%key:…%]` references are resolved by
  core's build, not at runtime, so a custom integration would show the raw key.
- HA adds a `name` placeholder (the entry title) to reauth forms by itself, unless the flow passes its own.
  Reconfigure forms don't get it.
- `async_set_unique_id` leaves reauth flows out of its `already_in_progress` check. A user flow for a charger
  whose reauth is open therefore aborts `already_configured`; `already_in_progress` only comes from two
  overlapping user flows.

## Tooling

- The ruff config copied from HA core bans `voluptuous` (use `probatio`) and `from __future__ import
  annotations`. HA 2026.9.3's flow API (`async_show_form`, `add_suggested_values_to_schema`) is still typed
  for voluptuous schemas, so `probatio` fails mypy strict there; `config_flow.py` imports
  `voluptuous as vol  # noqa: TID251`.
- Python 3.14 allows `except A, B:` without parentheses (PEP 758), and `ruff format` removes them.
- The pre-commit `ruff format` hook also formats Python blocks inside `.md` files. The first commit of a
  plan can fail because the hook changed the file; add it again and commit.

- `hass --debug` turns on asyncio debug mode, not debug logging, and HA logs only warnings and up unless
  the config sets a `logger`. `hass --verbose` logs INFO and DEBUG; `--log-file <path>` writes the log
  elsewhere than `config/`.
- On macOS, `hass` started in the background of a non-interactive shell (`hass … &`) crashed during startup
  in the Bluetooth integration (CoreBluetooth via PyObjC). Run it in the foreground with a timer instead
  (`scripts/smoke`). Started with Claude Code's Bash `run_in_background` (`scripts/develop`), it keeps
  running, Bluetooth included; stop it with `pkill -f "hass -c config"`.

## Testing

- To mock a client class, patch it with `autospec=True` and set its `return_value` to an
  `AsyncMock(spec=Client)` instance. Calling an `AsyncMock(spec=cls)` itself returns a coroutine, not a
  client.
- A `DataUpdateCoordinator` schedules its next poll only while it has listeners. To test polling before any
  entities exist, add one with `coordinator.async_add_listener(lambda: None)`.
- The test `hass` starts in the `US/Pacific` time zone. A test that depends on local time calls
  `await hass.config.async_set_time_zone(...)` first.
- `Store.async_delay_save(..., 0)` writes on a timer, which `hass.async_block_till_done()` doesn't wait for.
  Call `async_fire_time_changed(hass)` before reading `hass_storage`.
- `hass.async_create_task` and `ConfigEntry.async_create_background_task` start the task eagerly: it runs
  up to its first real wait before the caller's next line. With an `AsyncMock` that never waits, a
  "background" task has finished by then. To test the state while it is in flight, make the mock wait on an
  `asyncio.Event`.
- The test plugin fails a test that leaves an `async_call_later` timer scheduled, unless its `HassJob` has
  `cancel_on_shutdown=True`. Work that a timer starts as a background task needs
  `hass.async_block_till_done(wait_background_tasks=True)`; the default doesn't wait for background tasks.
- A `Store` version bump needs a `Store` subclass that overrides `_async_migrate_func`; without it, loading
  an older version raises `NotImplementedError`. The migrated data is saved straight back. `hass_storage`
  loads through HA's real `Store` load, so the migration runs in tests too.
- Setup reads the coordinator's data before it forwards the platforms, so a test that only looks after
  setup can't tell a value set once in the entity's `__init__` from a property. To show a value is live,
  change it in a read after setup.

## Coordinators and actions

- `DataUpdateCoordinator.async_set_updated_data` sets `last_update_success` to true, cancels a requested
  refresh and restarts the timer. To push state that didn't come from a read, replace `coordinator.data`
  and call `async_update_listeners()`.
- HA skips unavailable entities in an entity action (`switch.turn_off`) without an error, so an entity whose
  action must always reach the device stays available after a failed read.
- Unloading an entry doesn't cancel an entity action that is still running. Code that saves state from such
  a call has to finish before the reloaded entry loads it (for example, take the same lock in unload).
- `async_request_refresh()` is debounced with a 10 s cooldown: a second request within it runs only when the
  cooldown ends. `async_refresh()` skips the cooldown and takes the debouncer's lock, so it never overlaps
  another read. After a failed read the next one is scheduled with the current `update_interval`. Setting
  `update_interval` doesn't move a read that is already scheduled.
- A setup that fails for any reason (for example `ConfigEntryNotReady`, `ConfigEntryAuthFailed`,
  `ConfigEntryError`, an unexpected exception or a `False` return) never calls `async_unload_entry`, but Home
  Assistant still runs the entry's on-unload callbacks. Timers or tasks set up before the first refresh are
  cleaned up with `entry.async_on_unload`.
- A coordinator schedules its next read at whole loop seconds plus a random 0.05–0.5 s, so a read can come
  up to about 1 s before one full interval has passed. A time threshold compared with the interval needs a
  margin, and a test that fires the timer ticks a second more than the interval.

## Devices and entities

- HA 2026.9 deprecates `device_registry.async_get_device` (it logs a warning from integration code and
  raises `RuntimeError` in tests); use `async_get_device_by_identifier(identifier, entry_id)`. It also
  deprecates `DeviceInfo.via_device` in favour of `via_device_id`, a registered device's ID.
- `DeviceRegistry.async_get(device_id)` returns `DeviceEntry | ChildDeviceEntry | None`; pass
  `include_child_devices=False` to get a `DeviceEntry` for mypy.
- `async_get_or_create` with a `translation_key` sets the translated name, also on an existing device, so it
  can rename a device back to its placeholder.
- HA writes an entity's attributes only while it's available. An entity whose attributes must always be
  there (such as a price list) overrides `available`.
- HA never removes the devices of a loaded entry, and a user can't delete one in the UI unless the
  integration implements `async_remove_config_entry_device`. A device that no longer exists (such as a car
  removed from the account) is removed by the integration with `DeviceRegistry.async_remove_device`, which
  also removes its entities.
- On the day the clocks go back, two local datetimes with the same time zone compare by wall-clock time and
  ignore `fold`, so the repeated hour sorts wrongly. Compare and sort in UTC.
- When the unit of a sensor with `state_class` `measurement` changes while it has long-term statistics, HA
  stops compiling its statistics and raises its own repair, where the user picks what to do with the old
  statistics. Nothing in the integration has to handle it.
- For a sensor with `state_class` `total_increasing`, the recorder's statistics skip non-numeric states
  (unknown, unavailable) and start a new cycle only when the value drops below 90% of the previous one; a
  drop to 90% or more is logged as a dip, not a reset. So a per-charge counter may go unknown between
  charges, but a new cycle whose first value is at least 90% of the last one is missed.

## HACS

- HACS's `license` check reads the license GitHub detects on the default branch, so `LICENSE` must be on
  `main` before a PR's `hacs` check can pass.
- Brand images: see `custom_components/nortec_go/brand/README.md`.
