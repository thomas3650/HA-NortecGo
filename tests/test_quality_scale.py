"""Tests for the quality scale file."""

from pathlib import Path

from homeassistant.util.yaml import load_yaml_dict

from custom_components.nortec_go.const import DOMAIN

QUALITY_SCALE = (
    Path(__file__).parent.parent / "custom_components" / DOMAIN / "quality_scale.yaml"
)
STATUSES = {"done", "todo", "exempt"}


def test_quality_scale_statuses() -> None:
    """Every rule has a known status, and every rule written as a mapping says why."""
    rules = load_yaml_dict(QUALITY_SCALE)["rules"]
    assert rules
    for name, value in rules.items():
        if isinstance(value, str):
            assert value in STATUSES, name
            assert value != "exempt", f"{name}: exempt needs a comment"
        else:
            assert value["status"] in STATUSES, name
            assert value.get("comment"), name


def test_dependency_transparency_comment() -> None:
    """The comment isn't cut short by a YAML '#' comment marker."""
    rule = load_yaml_dict(QUALITY_SCALE)["rules"]["dependency-transparency"]
    assert rule["comment"].endswith("(issue #34).")


CHECKED_STATUSES = {
    "action-setup": "exempt",
    "docs-actions": "exempt",
    "docs-conditions": "exempt",
    "docs-triggers": "exempt",
    "action-exceptions": "done",
    "test-coverage": "done",
    "discovery": "exempt",
    "discovery-update-info": "exempt",
    "entity-disabled-by-default": "done",
    "strict-typing": "done",
    "dynamic-devices": "todo",
    "stale-devices": "todo",
    "icon-translations": "todo",
    "reconfiguration-flow": "todo",
}


def _status(value: str | dict[str, str]) -> str:
    """A rule's status, from either form."""
    return value if isinstance(value, str) else value["status"]


def test_checked_statuses() -> None:
    """The statuses checked against the rule texts and the code (issue #36)."""
    rules = load_yaml_dict(QUALITY_SCALE)["rules"]
    for name, status in CHECKED_STATUSES.items():
        assert _status(rules[name]) == status, name
        assert rules[name]["comment"], name


def test_rule_count() -> None:
    """All 54 rules from Bronze to Platinum are listed."""
    assert len(load_yaml_dict(QUALITY_SCALE)["rules"]) == 54
