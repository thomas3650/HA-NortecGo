"""Tests for the integration manifest."""

import json
from pathlib import Path
import tomllib

from custom_components.nortec_go.const import DOMAIN

ROOT = Path(__file__).parent.parent
MANIFEST = ROOT / "custom_components" / DOMAIN / "manifest.json"
PYPROJECT = ROOT / "pyproject.toml"


def _pins(requirements: list[str]) -> list[str]:
    return [req for req in requirements if req.startswith("pynortecgo")]


def test_pynortecgo_pins_match() -> None:
    """The manifest and the dev group pin the same exact pynortecgo version."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    pyproject = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    manifest_pins = _pins(manifest["requirements"])
    dev_pins = _pins(pyproject["dependency-groups"]["dev"])
    assert len(manifest_pins) == 1
    assert manifest_pins[0].startswith("pynortecgo==")
    assert manifest_pins == dev_pins


def test_config_flow_enabled() -> None:
    """The integration is set up from the UI."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["config_flow"] is True
