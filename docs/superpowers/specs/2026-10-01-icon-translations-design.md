# Icon translations — design

Date: 2026-10-01 · Branch: `feat/icon-translations` · Issue: #43

## Goal

- **What:** the Nortec Go entities that Home Assistant gives only a generic icon get a fitting icon of
  their own, and *Charge status* gets one per state. The icons are set through icon translations: a new
  `custom_components/nortec_go/icons.json`.
- **Why:** the dashboard is easier to read (#43), and it completes the `icon-translations` quality-scale
  rule.
- **Not in this work:**
  - any change to a `.py` file of the integration. The icons hang on the translation keys that `entity.py`
    already sets, so no entity's behaviour, state or attributes change. `switch.py` stays as it is;
  - icons for entities whose device class already gives a fitting icon (§1);
  - icons for actions (the integration has none) or for anything outside the entities;
  - a new decision: the rule in §1 is this spec's choice, not an entry in `decisions.md`.
- **Done when:** built TDD; the gates pass; `quality_scale.yaml`, the manual test guide and the changelog
  are updated.

## Decisions

The PO stood in for the owner in the brainstorm (2026-10-01, PO flow) and approved this design.

| Topic | Decision |
|---|---|
| Which entities get an icon | Only those Home Assistant gives no fitting icon (§1) |
| *Last read* and *Last seen* | No icon of their own. The issue lists *Last read* "where the device class gives none"; the timestamp device class gives a clock, so it is left out |
| The cost sensors, *Total energy*, the car entities | Added since the issue was written. Only *Charge limit* has no device class and gets an icon; the others keep their device-class icon |
| The *Charge* switch | A charger icon when off, a charging icon when on. The switch is also on while a charge is starting or paused; the charging icon shows then too, and *Charge status* carries the detail |
| The car-gone repair (the owner's comment on #43) | No icon: a repair issue shows no icon of its own (the `issues` section of `icons.json` is for the sections of a fix flow's forms, and this fix flow has none) |
| *Charge status* | A default icon, also shown while the status is unknown, and one icon for each of the eight states |
| User docs | `docs/user/nortec_go.md` is unchanged: it describes no icons |
| Decision log | No entry |
| PR title | `feat`, releasing: a minor version |

Facts used, read in the installed Home Assistant 2026.9.4:

- An integration's `icons.json` has an `entity` section: per platform, per translation key, a `default`
  icon and optionally a `state` map from a state to an icon. A state without an entry shows `default`.
- Home Assistant's own default icons, from its `sensor`, `binary_sensor`, `switch` and `button`
  components: a sensor without a device class and an `enum` sensor show `mdi:eye`; a switch shows a toggle;
  a button shows `mdi:button-pointer`. The `battery`, `energy`, `power`, `monetary` and `timestamp` sensor
  classes and the `plug` and `battery_charging` binary sensor classes each have an icon of their own.
- An entry for an entity's translation key takes the place of its device-class icon, also *Battery*'s
  level-dependent one. This is the frontend's lookup order, which the installed Python package
  doesn't hold, so it isn't verified here; §3's test 6 keeps such entries out either way.
- An icon is a Material Design Icons name, `mdi:<name>`. `hassfest` checks `icons.json` in CI only; it
  can't run locally.

## 1. The rule

An entity gets an icon in `icons.json` exactly when it has no device class, or the `enum` device class:
Home Assistant then shows only its platform's generic icon. Every other entity keeps the icon of its device
class.

So five entities get icons:

| Entity | Platform, key | Why |
|---|---|---|
| Charge | `switch`, `charge` | No device class |
| Refresh | `button`, `refresh` | No device class |
| Current price | `sensor`, `current_price` | No device class |
| Charge status | `sensor`, `charge_status` | `enum` |
| Charge limit (car) | `sensor`, `charge_limit` | No device class |

And these keep their device-class icon: *Last read* and *Last seen* (timestamp), *Battery* (battery),
*Energy this charge* and *Total energy* (energy), *Charging power* (power), *Cost this charge* and *Last
charge cost* (monetary), and the binary sensors *Cable connected*, *Plugged in*, *Connected to charger*
(plug) and *Charging* (battery charging).

## 2. The icons

Every entry has a `default`.

| Entity | State | Icon |
|---|---|---|
| Charge | default (off) | `mdi:ev-station` |
| Charge | `on` | `mdi:battery-charging` |
| Refresh | default | `mdi:refresh` |
| Current price | default | `mdi:cash-clock` |
| Charge limit | default | `mdi:battery-charging-80` |
| Charge status | default (also unknown) | `mdi:ev-station` |
| Charge status | `start_blocked` | `mdi:alert-circle` |
| Charge status | `starting` | `mdi:play-circle-outline` |
| Charge status | `charging` | `mdi:battery-charging` |
| Charge status | `paused` | `mdi:pause-circle-outline` |
| Charge status | `stopping` | `mdi:stop-circle-outline` |
| Charge status | `not_released` (*Waiting for replug*) | `mdi:connection` |
| Charge status | `unplugged` | `mdi:power-plug-off` |
| Charge status | `idle` | `mdi:power-plug` |

The *Charge status* `state` map has exactly the keys of `CHARGE_STATUS_OPTIONS`. No `state` icon repeats
its entry's `default`: the *Charge* switch has only `on`. All the names are in Material Design Icons
7.4.47, the set the Home Assistant 2026.9.4 frontend ships.

`icons.json` has only the `entity` section. `translations/en.json` is not involved: icons aren't
translations of text, and Home Assistant reads `icons.json` from the integration's folder.

## 3. Tests

A new `tests/test_icons.py`, with `pynortecgo` mocked as everywhere:

1. Every platform and key under `entity` in `icons.json` exists under `entity` in `strings.json`.
2. Every entry has a `default`.
3. Every icon is a well-formed name: `mdi:`, then groups of lowercase letters and digits joined by
   hyphens (`^mdi:[a-z0-9]+(-[a-z0-9]+)*$`).
4. The *Charge status* `state` keys equal `CHARGE_STATUS_OPTIONS`; the *Charge* switch's `state` keys are
   within `on` and `off`. No `state` icon equals its entry's `default` (`hassfest` is expected to refuse
   that, and it runs in CI only).
5. Home Assistant itself loads the file: `async_get_icons(hass, "entity", integrations=[DOMAIN])` returns
   a mapping whose `DOMAIN` entry equals the file's `entity` section.
6. With the integration set up for an account with a car, every entity of the entry follows §1: it is in
   `icons.json` exactly when it has no device class other than `enum`. This fails when a later entity
   without a device class is added without an icon, and when an entry is added for an entity that needs
   none.

`tests/test_quality_scale.py` checks `icon-translations` as `done`.

No test checks that a name exists in Material Design Icons: the list isn't in the test environment.

## 4. Docs and the release

- **`quality_scale.yaml`:** `icon-translations` becomes `done`, in the mapping form, with a comment that
  states the rule of §1, not a list of entities.
- **`docs/manual-testing.md`:** one line in the *Entities (#8)* checklist: the entities without a device class
  show an icon of their own, not the generic one, and *Charge status* shows an icon for its current state.
  The line names only *Charge status*, and gives no list and no count.
- **`CHANGELOG.md`:** an entry under *Added*.
- **`docs/user/nortec_go.md`:** no change.
- **The release:** the PR title is `feat: …`, so the bump step runs before `branch ready`
  (`docs/releasing.md`).

## 5. The visual check

What the PO looks at in Home Assistant, on the device pages. Nothing here needs a control operated: no
switch is turned, and no button is pressed.

- The charger device: *Charge* shows the charger icon (or the charging icon if a charge happens to be on),
  *Refresh* the refresh icon, *Current price* the cash-and-clock icon.
- *Charge status* shows the icon of the state it is in at that moment, per the table in §2, not the eye.
  Only that one state can be checked; the tests cover the map.
- The car device: *Charge limit* shows the battery icon of §2.
- The other entities still show their device-class icons (a clock, a battery, a lightning bolt, a flash,
  cash, a plug): nothing became blank.
- No icon is blank. A blank icon means a name Home Assistant's icon set doesn't have.
