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

## Testing

- To mock a client class, patch it with `autospec=True` and set its `return_value` to an
  `AsyncMock(spec=Client)` instance. Calling an `AsyncMock(spec=cls)` itself returns a coroutine, not a
  client.
- A `DataUpdateCoordinator` schedules its next poll only while it has listeners. To test polling before any
  entities exist, add one with `coordinator.async_add_listener(lambda: None)`.
- The test `hass` starts in the `US/Pacific` time zone. A test that depends on local time calls
  `await hass.config.async_set_time_zone(...)` first.

## Devices and entities

- HA 2026.9 deprecates `device_registry.async_get_device` (it logs a warning from integration code and
  raises `RuntimeError` in tests); use `async_get_device_by_identifier(identifier, entry_id)`. It also
  deprecates `DeviceInfo.via_device` in favour of `via_device_id`, a registered device's ID.
- `device_registry.async_get(id)` returns `DeviceEntry | ChildDeviceEntry | None`; pass
  `include_child_devices=False` to get a `DeviceEntry` for mypy.
- `async_get_or_create` with a `translation_key` sets the translated name, also on an existing device, so it
  can rename a device back to its placeholder.
- HA writes an entity's attributes only while it's available. An entity whose attributes must always be
  there (such as a price list) overrides `available`.

## HACS

- HACS's `license` check reads the license GitHub detects on the default branch, so `LICENSE` must be on
  `main` before a PR's `hacs` check can pass.
- Brand images: see `custom_components/nortec_go/brand/README.md`.
