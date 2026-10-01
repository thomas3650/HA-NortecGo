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
    """A state icon differs from its entry's default: a state without an icon shows the default."""
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
