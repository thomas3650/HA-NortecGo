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
- The pre-commit `ruff-format` hook also formats Python blocks inside `.md` files, such as specs and plans
  (found in #45).
  - A commit of a plan can fail once with "files were modified by this hook"; re-stage and commit again.
  - It dedents class methods (indented `def`s) to module level. How a plan writes those, and fragments, is in
    [`way-of-working.md`](way-of-working.md#1-flow-for-non-trivial-changes) §1 step 5.
  - It formats those blocks but doesn't lint them, so a plan's test code can hold a `ruff check` finding (for
    example D403, a lowercase first word in a docstring) that only shows once the code lands in a `.py` file.
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
- hassfest's `icons.json` check (core's `script/hassfest/icons.py`) runs on a draft PR too. In the `entity`
  section it wants every icon to start with `mdi:`, allows only the keys `default`, `state`, `range` and
  `state_attributes` in an entry, and refuses a state icon equal to its entry's `default`.
  `tests/test_icons.py` checks the same and is stricter by choice: only the `entity` section, and a
  `default` in every entry.

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
- To run the first retry of an entry in `SETUP_RETRY`, fire the time 10 s ahead
  (`async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=10))`) and wait with
  `hass.async_block_till_done(wait_background_tasks=True)`. Home Assistant runs the retry as a background
  task (see the bullet on work that a timer starts), so with the default wait the entry can still be
  in `SETUP_IN_PROGRESS`.
- A helper called in a `@pytest.mark.parametrize` list runs at import: if it raises, the file fails to
  collect and pytest runs nothing. So a stricter helper lands in the same commit as the cases it refuses. A
  removed case takes its `ids=` entry with it; compare `pytest --collect-only -q` before and after, since
  removing the wrong id is no error.
- `pytest.raises(match=...)` is a regex search, so a name that is a prefix of another matches the wrong
  message. Compare the whole `str(excinfo.value)` when the exact text matters.
- `async_get_icons(hass, "entity", integrations=[DOMAIN])` (`homeassistant.helpers.icon`) returns a mapping
  keyed by domain: `result[DOMAIN]` is the `entity` section of `icons.json`. It shows that Home Assistant
  itself loads the file.

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
  cleaned up with `entry.async_on_unload`. Home Assistant also cancels the entry's background tasks
  (`ConfigEntry.async_create_background_task`). So in the first refresh, whatever can still fail setup comes
  before work that saves or queues something; otherwise a failed setup leaves that work half done (in this
  integration: the car is read before the charge control gets the charger read, D44).
- A coordinator schedules its next read at whole loop seconds plus a random 0.05–0.5 s, so a read can come
  up to about 1 s before one full interval has passed. A time threshold compared with the interval needs a
  margin, and a test that fires the timer ticks a second more than the interval.
- At the first refresh, an `UpdateFailed` re-raises as `ConfigEntryNotReady` with the cause's translation
  domain, key and placeholders; `ConfigEntryError` and `ConfigEntryAuthFailed` pass through as they are. A
  setup that fails or retries with any of the three stores the translation as the entry's
  `error_reason_translation_*`, which the frontend shows translated. So a translated `UpdateFailed` or
  `ConfigEntryError` also translates the setup error.
- After `ConfigEntryNotReady`, Home Assistant sets the entry up again by itself: after about 5 s, then at
  doubling gaps up to 10 minutes (`SETUP_RETRY_MAX_WAIT`). While Home Assistant is still starting, the first
  retry waits for the started event instead of a timer. Each try runs `async_setup_entry` from the top.
- The first refresh ignores `UpdateFailed.retry_after`, so a rate limit's own waiting time isn't used at
  setup.
- Outside setup, `async_refresh()` stores a read's error in `last_exception` instead of raising it,
  including `ConfigEntryAuthFailed` and `ConfigEntryError`. A caller that must report a failed read looks at
  the coordinator afterwards.
- `DataUpdateCoordinator.last_exception` isn't cleared by a successful read. Show it as the current error
  only while `last_update_success` is false.
- In `_async_update_data`, don't await between taking a snapshot of state that a callback can change (the
  charge control's state, here) and returning the data. A change made during the await updates the
  coordinator's data, and is then overwritten by the older snapshot when the read returns. Take the snapshot
  after the last await.

## Devices and entities

- HA 2026.9 deprecates `device_registry.async_get_device` (it logs a warning from integration code and
  raises `RuntimeError` in tests); use `async_get_device_by_identifier(identifier, entry_id)`. It also
  deprecates `DeviceInfo.via_device` in favour of `via_device_id`, a registered device's ID.
- `DeviceRegistry.async_get(device_id)` returns `DeviceEntry | ChildDeviceEntry | None`; pass
  `include_child_devices=False` to get a `DeviceEntry` for mypy.
- `async_get_or_create` with a `translation_key` sets the translated name, also on an existing device, so it
  can rename a device back to its placeholder.
- `async_get_or_create` takes `None` for `manufacturer` and `model`, which clears them on an existing
  device; `UNDEFINED` leaves them as they are.
- HA writes an entity's attributes only while it's available. An entity whose attributes must always be
  there (such as a price list) overrides `available`.
- HA never removes the devices of a loaded entry, and a user can't delete one in the UI unless the
  integration implements `async_remove_config_entry_device`. A device that no longer exists (such as a car
  removed from the account) is removed by the integration with `DeviceRegistry.async_remove_device`, which
  also removes its entities.
- On the day the clocks go back, two local datetimes with the same time zone compare by wall-clock time and
  ignore `fold`, so the repeated hour sorts wrongly. Compare and sort in UTC.
- When the unit of a sensor with long-term statistics changes to one HA can't convert to the stored unit
  (another currency, say), whatever its `state_class` (`measurement`, `total` or `total_increasing`), HA
  stops compiling its statistics and raises its own repair, where the user picks what to do with the old
  statistics. Nothing in the integration has to handle it. A change HA can convert (kWh to Wh) keeps the
  statistics, in the stored unit.
- For a sensor with `state_class` `total_increasing`, the recorder's statistics skip non-numeric states
  (unknown, unavailable) and start a new cycle only when the value drops below 90% of the previous one: the
  sum carries on, and the new value is added in full. The test is against the sensor's whole value, so on a
  small total a small drop is a new cycle too. A drop to 90% or more is a dip: its negative change is added
  to the sum, and from an entity's second dip after a start Home Assistant logs a warning, once per run,
  that asks the user to report it to the integration. So a per-charge counter may go unknown between
  charges, but a new cycle whose first value is at least 90% of the last one is missed, and a
  `total_increasing` value should never go down by itself.
- A value that can restart from 0 outside the integration's control (a lost store, an entry removed and
  added again) is `total_increasing`, not plain `total` (see the next item for what `total` does with a
  drop).
- For a sensor with `state_class` `total`, the recorder's statistics depend on `last_reset`. Without it, a
  drop counts as a negative change, so a value that restarts per cycle gives a sum that is just the current
  value. With it, a changed `last_reset` starts a new cycle and the new value is added in full, and the same
  `last_reset` adds only the change in value. The first value ever recorded sets the zero point and isn't
  added. So a per-cycle value needs `last_reset`, or no state class.
- `device_class` `monetary` allows only the state class `total`, or none.
- A sensor's display precision doesn't change its state string: the state is the native value as it is.
- Icon translations: `icons.json` has an `entity` section, per platform and translation key, with a
  `default` icon and optionally a `state` map; a state without an entry shows `default`. Home Assistant's
  device-class icons are in each entity component's own `icons.json`; without a device class, or with
  `enum`, an entity gets only its platform's generic icon. Which entities get an entry here is the rule
  `tests/test_icons.py` checks against the entity registry.
- The Material Design Icons list isn't in the Python environment (the frontend isn't installed for the
  tests), so no test can tell whether an icon name exists, and a wrong name shows a blank icon. Check a new
  name against the MDI list by hand, and look for blank icons in the visual check.

## Repairs

- A fix flow of the integration's own (a `RepairsFlow` subclass) doesn't get the issue's placeholders; it
  passes `description_placeholders` to `async_show_form` itself. Home Assistant's `ConfirmRepairFlow` does
  take them from the issue.
- A fix flow that ends with `async_create_entry` deletes its issue; one that aborts leaves it.
- An issue created with `is_persistent=False` isn't shown after a restart of Home Assistant, until the
  integration creates it again: the registry keeps only its ID, its creation time and whether it was
  ignored. Deleting an issue that doesn't exist does nothing.
- `hass.config_entries.async_schedule_reload` raises `UnknownEntry` for an entry that no longer exists, so a
  flow that reloads checks the entry first.
- `async_create_fix_flow` gets every fixable issue of the integration; with more than one kind of issue it
  picks the flow by the issue ID.

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
