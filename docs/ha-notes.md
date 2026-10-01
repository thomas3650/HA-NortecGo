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
- **Enable debug logging** on an integration's page covers the integration's package logger and the
  manifest's `loggers` list, not the packages in `requirements`. A library the integration logs through
  goes in `loggers`.

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
- hassfest's quality-scale check (`validate_iqs_file` in core's `script/hassfest/quality_scale.py`) returns
  at once for an integration that isn't in core, so only `tests/test_quality_scale.py` checks
  `quality_scale.yaml` here. It mirrors hassfest's comment rule: a rule written as a mapping needs a
  `comment`.
- The current quality-scale rule texts are Markdown files in the public
  [developers.home-assistant](https://github.com/home-assistant/developers.home-assistant) repo, under
  `docs/core/integration-quality-scale/rules/`. Most say "There are no exceptions to this rule", yet core
  marks a rule `exempt`, with a comment, when what it governs doesn't exist (`action-setup` for an
  integration without service actions).

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
  `asyncio.Event`. To check that the task started, use `await hass.async_block_till_done()` and then
  `assert started.is_set()`, not `await started.wait()`: without the code under test, that wait hangs (no
  pytest timeout is configured).
- The test plugin fails a test that leaves an `async_call_later` timer scheduled, unless its `HassJob` has
  `cancel_on_shutdown=True`. Work that a timer starts as a background task needs
  `hass.async_block_till_done(wait_background_tasks=True)`; the default doesn't wait for background tasks.
- HA doesn't unload config entries when it stops (it only calls `entry.async_shutdown`), so an entry's
  `async_call_later` timers need `cancel_on_shutdown=True` even when an `async_on_unload` callback cancels
  them. The `hass` fixture unloads loaded entries at teardown, so the lingering-timer check doesn't catch a
  missing flag on an entry's timer: check it in review.
- A `Store` version bump needs a `Store` subclass that overrides `_async_migrate_func`; without it, loading
  an older version raises `NotImplementedError`. The migrated data is saved straight back. `hass_storage`
  loads through HA's real `Store` load, so the migration runs in tests too.
- Setup reads the coordinator's data before it forwards the platforms, so a test that only looks after
  setup can't tell a value set once in the entity's `__init__` from a property. To show a value is live,
  change it in a read after setup.
- `str()` of a `HomeAssistantError` raised with a `translation_key` (and no message) is the English text
  from the translations without its final period: HA strips it. A test that compares it with
  `strings.json` drops the period. The texts come from the translations HA has loaded, so set up the
  integration before building such an exception in a test.
- `hass_client` signs its requests with an access token made at fixture setup, valid for 30 minutes with
  10 s leeway. A test that moves the clock back before that, or more than 30 minutes forward, gets a 401. Make
  a fresh token after the last clock move: create a refresh token for `hass_admin_user` with `CLIENT_ID`
  (from `pytest_homeassistant_custom_component.common`), make an access token from it with
  `hass.auth.async_create_access_token`, and pass that to `hass_client`.

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
- At the first refresh, an `UpdateFailed` re-raises as `ConfigEntryNotReady` with the cause's translation
  domain, key and placeholders; `ConfigEntryError` and `ConfigEntryAuthFailed` pass through as they are. A
  setup that fails or retries with any of the three stores the translation as the entry's
  `error_reason_translation_*`, which the frontend shows translated. So a translated `UpdateFailed` or
  `ConfigEntryError` also translates the setup error.
- Outside setup, `async_refresh()` stores a read's error in `last_exception` instead of raising it,
  including `ConfigEntryAuthFailed` and `ConfigEntryError`. A caller that must report a failed read looks at
  the coordinator afterwards.
- `DataUpdateCoordinator.last_exception` isn't cleared by a successful read. Show it as the current error
  only while `last_update_success` is false.

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
- For a sensor with `state_class` `total`, the recorder's statistics depend on `last_reset`. Without it, a
  drop counts as a negative change, so a value that restarts per cycle gives a sum that is just the current
  value. With it, a changed `last_reset` starts a new cycle and the new value is added in full, and the same
  `last_reset` adds only the change in value. The first value ever recorded sets the zero point and isn't
  added. So a per-cycle value needs `last_reset`, or no state class.
- `device_class` `monetary` allows only the state class `total`, or none.
- A sensor's display precision doesn't change its state string: the state is the native value as it is.

## Diagnostics

- HA's download wraps the integration's data with its own system info (the time zone among it), the
  manifest, setup times and the integration's repair issues. A non-persistent repair issue shows only its ID,
  domain, creation time and flags; a persistent one also shows its placeholders and data.
- The download is served for an entry in any state, so a diagnostics platform handles an entry that isn't
  loaded, which has no `runtime_data`.
- `async_redact_data` leaves `None` and empty strings as they are, and redacts every other value of a listed
  key, in nested dicts too.

## HACS

- HACS's `license` check reads the license GitHub detects on the default branch, so `LICENSE` must be on
  `main` before a PR's `hacs` check can pass.
- Brand images: see `custom_components/nortec_go/brand/README.md`.
