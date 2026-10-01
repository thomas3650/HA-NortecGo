# Icon translations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. In this repo the flow in `docs/way-of-working.md` §1–2 applies (implementer and task-reviewer agents, waves, worktrees).

**Goal:** The entities that Home Assistant gives only a generic icon get an icon of their own through icon translations, with one icon per *Charge status* state.

**Architecture:** Task 1 adds `custom_components/nortec_go/icons.json` and `tests/test_icons.py`, which checks the file against `strings.json`, against `CHARGE_STATUS_OPTIONS` and against the entities of a set-up entry. Task 2 marks the quality-scale rule done and writes the manual-test line and the changelog entry. No `.py` file of the integration changes: the icons hang on the translation keys `entity.py` already sets.

**Tech Stack:** Python 3.14, Home Assistant 2026.9.4 custom integration, `pynortecgo` (always mocked in tests), pytest with `pytest-homeassistant-custom-component`, uv.

**Spec:** `docs/superpowers/specs/2026-10-01-icon-translations-design.md` (issue #43).

## Global Constraints

- TDD: write the failing test, see it fail, then write the file that makes it pass. Tests always mock `pynortecgo` and use the `tests/conftest.py` fixtures (hard rules 2, 7).
- Icons only. No task changes a `.py` file under `custom_components/nortec_go/`; `switch.py` stays as it is. No entity's behaviour, state, name or attributes change. Nothing near starting or stopping a charge is touched (hard rule 2).
- Nothing private (hard rule 3): no IDs, tokens, emails, captures, raw endpoints or response shapes, in code, tests, docs or commit messages.
- The rule (spec §1): an entity has an entry in `icons.json` exactly when it has no device class, or the `enum` device class. Every other entity keeps its device class's icon and has no entry.
- The icons are exactly those of the spec's §2 table, copied verbatim in Task 1. Every entry has a `default`. No `state` icon equals its entry's `default`. `icons.json` has only the `entity` section.
- No new decision: nothing is added to `docs/decisions.md`. `docs/user/nortec_go.md` and `translations/en.json` don't change.
- Gates before every commit: `uv run pytest -q`, then `uv run ruff check && uv run ruff format --check && uv run mypy` (the gates in `CLAUDE.md` → Commands without `actionlint` and `zizmor`: no task touches a workflow). The coverage gate (`uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95`) passes at the end of each task.
- Subagents write commit messages with the Write tool to a file outside the repo (`/tmp/icon-translations-task-<n>-msg.txt`), and commit with `git commit -F <file>` (no heredocs). End each message with the co-author trailer given in the dispatch.
- Match the surrounding code: one-line docstrings ending in a period, names, comment density. `ruff format` decides the layout; if it rewrites a line of this plan's code, keep ruff's version.
- `CHANGELOG.md`: the entry goes under `## [Unreleased]`. No task sets `version` in `manifest.json` or moves *Unreleased*: the controller runs the bump step at the end (`docs/releasing.md`).

## Review Focus

The conditions the spec implies that no test here can exercise, most likely first. None of them can get a test in this repo (the reason is given), so each names who checks it instead.

1. An icon name that Material Design Icons doesn't have shows a blank icon. The icon list isn't in the test environment (spec §3), so the test checks only the name's form. The task reviewer compares every name in `icons.json` with the spec's §2 table, character by character; the PO's visual check looks for a blank icon (spec §5).
2. `hassfest` refuses an `icons.json` shape the local tests accept. It runs in CI only. The tests mirror the rules known here (a `default` in every entry, only `default` and `state` keys, no state icon equal to the default, only the `entity` section), and the controller reads the `hassfest` check on the draft PR after Task 1 is pushed.
3. *Charge status* is unknown (its value is `None`, for a charger state the integration doesn't know): the `default` icon shows. That is Home Assistant's fallback, in the frontend; the test checks that the entry has a `default`.
4. An account without a car has no *Charge limit* entity, and `icons.json` still has its entry. An entry for an entity that isn't there is unused, which is fine; the registry test runs with a car so that it covers every entity.
5. A later entity without a device class added without an icon: `test_icons_exactly_where_home_assistant_gives_none` fails. This one is tested; it is listed so the reviewer checks that the test reads the entity registry and no hand-kept list of keys.

## Waves

| Wave | Tasks | Notes |
|---|---|---|
| 1 | Task 1 (`icons.json` and its test) | Alone in its wave: it runs in the issue worktree, on the feature branch |
| 2 | Task 2 (quality scale, manual-test line, changelog) | Needs Task 1 on the feature branch: it declares the rule done. Alone in its wave too |

No task has guarded files.

---

### Task 1: `icons.json` and its test

**Model:** sonnet — a data file and a test of it; no auth, no start or stop, and no mapping of client models.
**Wave:** 1

**Files:**
- Create: `custom_components/nortec_go/icons.json`
- Test: `tests/test_icons.py` (new)

**Interfaces:**
- Consumes: `CHARGE_STATUS_OPTIONS` from `custom_components/nortec_go/charge_control.py` (a list of the eight status keys); `setup_integration`, and the fixtures `mock_client` and `mock_config_entry`, from `tests/conftest.py` (the mocked account has a charger and a car); the `entity` section of `custom_components/nortec_go/strings.json`.
- Produces: `custom_components/nortec_go/icons.json`, with an `entity` section keyed by platform and translation key. Task 2 describes it in words only.

- [ ] **Step 1: Write the failing test**

Create `tests/test_icons.py` with exactly this content:

```python
"""Tests for the icon translations (icons.json)."""

from collections.abc import Iterator
import json
from pathlib import Path
import re
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.icon import async_get_icons
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nortec_go.charge_control import CHARGE_STATUS_OPTIONS
from custom_components.nortec_go.const import DOMAIN

from .conftest import setup_integration

INTEGRATION_DIR = Path(__file__).parent.parent / "custom_components" / DOMAIN
ICON_NAME = re.compile(r"mdi:[a-z0-9]+(-[a-z0-9]+)*")
# An entity with one of these device classes gets only its platform's generic icon.
NO_ICON_DEVICE_CLASSES = {None, "enum"}


def _load(name: str) -> dict[str, Any]:
    """A JSON file of the integration."""
    loaded: dict[str, Any] = json.loads(
        (INTEGRATION_DIR / name).read_text(encoding="utf-8")
    )
    return loaded


def _entries(icons: dict[str, Any]) -> Iterator[tuple[str, str, dict[str, Any]]]:
    """Every (platform, translation key, entry) under entity."""
    for platform, keys in icons["entity"].items():
        for key, entry in keys.items():
            yield platform, key, entry


def test_only_the_entity_section() -> None:
    """icons.json holds entity icons only: the integration has no actions."""
    assert set(_load("icons.json")) == {"entity"}


def test_every_icon_key_is_an_entity_key() -> None:
    """Every platform and key with an icon exists in strings.json."""
    entities = _load("strings.json")["entity"]
    entries = list(_entries(_load("icons.json")))
    assert entries
    for platform, key, _ in entries:
        assert key in entities.get(platform, {}), f"{platform}.{key}"


def test_every_entry_has_a_default() -> None:
    """Every entry has a default icon: a state without its own icon shows it."""
    for platform, key, entry in _entries(_load("icons.json")):
        assert "default" in entry, f"{platform}.{key}"
        assert set(entry) <= {"default", "state"}, f"{platform}.{key}"


def test_every_icon_is_a_well_formed_name() -> None:
    """Every icon is mdi: and groups of lowercase letters and digits joined by hyphens."""
    for platform, key, entry in _entries(_load("icons.json")):
        for icon in (entry["default"], *entry.get("state", {}).values()):
            assert isinstance(icon, str), f"{platform}.{key}"
            assert ICON_NAME.fullmatch(icon), f"{platform}.{key}: {icon}"


def test_no_state_icon_repeats_the_default() -> None:
    """A state icon differs from its entry's default; hassfest (CI only) refuses a repeat."""
    for platform, key, entry in _entries(_load("icons.json")):
        for state, icon in entry.get("state", {}).items():
            assert icon != entry["default"], f"{platform}.{key}.{state}"


def test_charge_status_has_an_icon_per_state() -> None:
    """Charge status has an icon for exactly its options."""
    states = _load("icons.json")["entity"]["sensor"]["charge_status"]["state"]
    assert set(states) == set(CHARGE_STATUS_OPTIONS)
    assert len(CHARGE_STATUS_OPTIONS) == len(set(CHARGE_STATUS_OPTIONS))


def test_charge_switch_states() -> None:
    """The Charge switch's state icons are for on or off only."""
    states = _load("icons.json")["entity"]["switch"]["charge"]["state"]
    assert states
    assert set(states) <= {"on", "off"}


async def test_home_assistant_loads_the_icons(hass: HomeAssistant) -> None:
    """Home Assistant reads icons.json and gives its entity section for the domain."""
    icons = await async_get_icons(hass, "entity", integrations=[DOMAIN])
    assert icons[DOMAIN] == _load("icons.json")["entity"]


async def test_icons_exactly_where_home_assistant_gives_none(
    hass: HomeAssistant,
    mock_client: object,
    mock_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """An entity has an icon of its own exactly when it has no device class, or enum."""
    await setup_integration(hass, mock_config_entry)
    icons_file = _load("icons.json")
    icons = icons_file["entity"]
    entries = er.async_entries_for_config_entry(
        entity_registry, mock_config_entry.entry_id
    )
    # The mocked account has a car, so the car's entities are checked too.
    assert {entry.translation_key for entry in entries} >= {"charge", "charge_limit"}
    with_icon = set()
    for entry in entries:
        assert entry.translation_key is not None, entry.entity_id
        has_icon = entry.translation_key in icons.get(entry.domain, {})
        needs_icon = entry.original_device_class in NO_ICON_DEVICE_CLASSES
        assert has_icon == needs_icon, entry.entity_id
        if has_icon:
            with_icon.add((entry.domain, entry.translation_key))
    # And no icon is left over for an entity that isn't there.
    assert with_icon == {(platform, key) for platform, key, _ in _entries(icons_file)}
```

Notes for the implementer:
- `entity_registry` is a fixture of `pytest-homeassistant-custom-component`.
- `mock_client` is requested so that the client class is patched; the test doesn't use the object.
- `original_device_class` is what the entity itself declares; a string such as `"timestamp"`, or `None`.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest -q tests/test_icons.py`
Expected: 9 failed. Eight fail with `FileNotFoundError` for `icons.json`; `test_home_assistant_loads_the_icons` fails with `KeyError: 'nortec_go'`.

- [ ] **Step 3: Write `icons.json`**

Create `custom_components/nortec_go/icons.json` with exactly this content (the spec's §2 table; two-space indent, a final newline):

```json
{
  "entity": {
    "button": {
      "refresh": {
        "default": "mdi:refresh"
      }
    },
    "sensor": {
      "current_price": {
        "default": "mdi:cash-clock"
      },
      "charge_limit": {
        "default": "mdi:battery-charging-80"
      },
      "charge_status": {
        "default": "mdi:ev-station",
        "state": {
          "start_blocked": "mdi:alert-circle",
          "starting": "mdi:play-circle-outline",
          "charging": "mdi:battery-charging",
          "paused": "mdi:pause-circle-outline",
          "stopping": "mdi:stop-circle-outline",
          "not_released": "mdi:connection",
          "unplugged": "mdi:power-plug-off",
          "idle": "mdi:power-plug"
        }
      }
    },
    "switch": {
      "charge": {
        "default": "mdi:ev-station",
        "state": {
          "on": "mdi:battery-charging"
        }
      }
    }
  }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest -q tests/test_icons.py`
Expected: 9 passed.

- [ ] **Step 5: See the registry test catch a break of the rule**

This shows the test has teeth; nothing from this step is committed.

1. In `icons.json`, remove the `charge_limit` entry. Run `uv run pytest -q tests/test_icons.py`. Expected: `test_icons_exactly_where_home_assistant_gives_none` fails, naming `sensor.family_car_charge_limit`.
2. Put the entry back, and add `"last_read": {"default": "mdi:clock"}` under `sensor`. Run again. Expected: the same test fails, naming `sensor.garage_charger_last_read`.
3. Restore the file to exactly Step 3's content: write it again with the Write tool. Run again. Expected: 9 passed.

Say in the report what each run showed.

- [ ] **Step 6: Run the gates**

Run: `uv run pytest -q`
Expected: all pass.

Run: `uv run ruff check && uv run ruff format --check && uv run mypy`
Expected: no findings.

Run: `uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95`
Expected: passes; the coverage is what it was before (no `.py` file of the integration changed).

- [ ] **Step 7: Commit**

Write the message to `/tmp/icon-translations-task-1-msg.txt` with the Write tool:

```text
feat: icons for the entities without a device-class icon (#43)

icons.json gives an icon to the Charge switch, the Refresh button and the
Current price, Charge limit and Charge status sensors, with one per Charge
status state. A test keeps the file in step with the entities.

<the co-author trailer from the dispatch>
```

```bash
git add custom_components/nortec_go/icons.json tests/test_icons.py
git commit -F /tmp/icon-translations-task-1-msg.txt
```

`git status --short` shows nothing afterwards.

---

### Task 2: Quality scale, manual-test line and changelog

**Model:** opus — a docs task (D33).
**Wave:** 2

**Files:**
- Modify: `tests/test_quality_scale.py` (the `icon-translations` row of `CHECKED_STATUSES`)
- Modify: `custom_components/nortec_go/quality_scale.yaml` (the `icon-translations` rule)
- Modify: `docs/manual-testing.md` (the *Entities (#8)* checklist, its *Reads and the device page* group)
- Modify: `CHANGELOG.md` (under `## [Unreleased]`)

**Interfaces:**
- Consumes: Task 1's `custom_components/nortec_go/icons.json` on the feature branch, and the rule of the spec's §1.
- Produces: nothing a later task uses.

- [ ] **Step 1: Make the quality-scale test expect `done`**

In `tests/test_quality_scale.py`, in `CHECKED_STATUSES`, change this row:

```text
    "icon-translations": "todo",
```

to:

```text
    "icon-translations": "done",
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest -q tests/test_quality_scale.py`
Expected: `test_checked_statuses` fails with `AssertionError: icon-translations`; the other tests pass.

- [ ] **Step 3: Mark the rule done**

In `custom_components/nortec_go/quality_scale.yaml`, replace:

```yaml
  icon-translations:
    status: todo
    comment: "No icons.json yet; the Charge switch, the Refresh button and the Current price, Charge status and Charge limit sensors have no icon of their own."
```

with:

```yaml
  icon-translations:
    status: done
    comment: "icons.json gives an icon to every entity that has no device class or the enum device class, with one per state for Charge status; every other entity shows its device class's icon."
```

The rule keeps the mapping form: `test_checked_statuses` needs the comment. The comment states the rule and lists no entities, so it stays true when an entity is added (spec §4).

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest -q tests/test_quality_scale.py`
Expected: all pass (the rule count stays 54).

- [ ] **Step 5: Add the manual-test line**

In `docs/manual-testing.md`, in *Entities (#8)*, the group *Reads and the device page* ends with this item:

```markdown
- [ ] The device page: both devices, their entities, and the diagnostic entities in the diagnostic group.
```

Add this item right after it, as the group's last:

```markdown
- [ ] Icons: an entity without a device class shows an icon of its own, not Home Assistant's generic one
  (an eye, a toggle or a button pointer), and *Charge status* shows an icon for its current state. No icon
  is blank.
```

The line names only *Charge status*, and gives no list and no count (spec §4). Keep lines within the file's wrap width (about 110 characters), as the lines around it.

- [ ] **Step 6: Add the changelog entry**

In `CHANGELOG.md`, `## [Unreleased]` is empty. Make it:

```markdown
## [Unreleased]

### Added

- Icons: the entities that showed Home Assistant's generic icon now have one of their own, and *Charge
  status* shows an icon for each state.
```

Leave one blank line before `## [0.4.0] - 2026-10-01`. Don't change `version` in `manifest.json` and don't move *Unreleased*: the controller runs the bump step.

- [ ] **Step 7: Check that nothing else needs a change**

Run: `grep -rn -i "icon" docs/user/nortec_go.md README.md docs/ha-notes.md docs/notes.md`
Expected: no line about entity icons (the brand icon of D14 is another matter). If a line claims that entities have no icons, stop and report it; don't edit those files.

- [ ] **Step 8: Run the gates**

Run: `uv run pytest -q`
Expected: all pass.

Run: `uv run ruff check && uv run ruff format --check && uv run mypy`
Expected: no findings.

Run: `uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95`
Expected: passes.

- [ ] **Step 9: Commit**

Write the message to `/tmp/icon-translations-task-2-msg.txt` with the Write tool:

```text
docs: icon-translations is done, with a manual-test line and a changelog entry (#43)

<the co-author trailer from the dispatch>
```

```bash
git add tests/test_quality_scale.py custom_components/nortec_go/quality_scale.yaml docs/manual-testing.md CHANGELOG.md
git commit -F /tmp/icon-translations-task-2-msg.txt
```

`git status --short` shows nothing afterwards.

---

## After the tasks (the controller)

- After Task 1 is pushed: read the `hassfest` check on the draft PR (Review Focus 2).
- Learnings (step 8), the branch review (step 9), then the bump step for the `feat` title (`docs/releasing.md`) and `branch ready` to the PO, with `visible: yes` (spec §5).
