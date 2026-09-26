"""Tests for the quality scale file."""

from pathlib import Path

from homeassistant.util.yaml import load_yaml_dict

from custom_components.nortec_go.const import DOMAIN

QUALITY_SCALE = (
    Path(__file__).parent.parent / "custom_components" / DOMAIN / "quality_scale.yaml"
)
STATUSES = {"done", "todo", "exempt"}


def test_quality_scale_statuses() -> None:
    """Every rule has a known status, and every exemption says why."""
    rules = load_yaml_dict(QUALITY_SCALE)["rules"]
    assert rules
    for name, value in rules.items():
        if isinstance(value, str):
            assert value in STATUSES, name
            assert value != "exempt", f"{name}: exempt needs a comment"
        else:
            assert value["status"] in STATUSES, name
            if value["status"] == "exempt":
                assert value.get("comment"), name


def test_dependency_transparency_comment() -> None:
    """The comment isn't cut short by a YAML '#' comment marker."""
    rule = load_yaml_dict(QUALITY_SCALE)["rules"]["dependency-transparency"]
    assert rule["comment"].endswith("(issue #34).")


def test_rule_count() -> None:
    """All 54 rules from Bronze to Platinum are listed."""
    assert len(load_yaml_dict(QUALITY_SCALE)["rules"]) == 54
