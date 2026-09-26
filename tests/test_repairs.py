"""Tests for the Nortec Go repair fix flow."""

from http import HTTPStatus
from typing import Any, cast
from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.nortec_go.const import DOMAIN

from .conftest import make_charger, setup_integration


def _blocked(hass_storage: dict[str, Any], entry: MockConfigEntry) -> None:
    key = f"nortec_go.{entry.entry_id}.charge_control"
    hass_storage[key] = {
        "version": 1,
        "key": key,
        "data": {
            "blocked_since": "2026-09-26T20:00:00+00:00",
            "start_pending_since": None,
            "stop_asked": False,
        },
    }


async def _start_fix(client: Any, issue_id: str) -> dict[str, Any]:
    resp = await client.post(
        "/api/repairs/issues/fix", json={"handler": DOMAIN, "issue_id": issue_id}
    )
    assert resp.status == HTTPStatus.OK
    return cast("dict[str, Any]", await resp.json())


async def test_fix_flow_clears_the_block(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    hass_storage: dict[str, Any],
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
) -> None:
    """Confirming clears the block; the issue is gone."""
    _blocked(hass_storage, mock_config_entry)
    mock_client.get_charger.return_value = make_charger(is_connected=True)
    await setup_integration(hass, mock_config_entry)
    assert await async_setup_component(hass, "repairs", {})
    issue_id = f"start_blocked_{mock_config_entry.entry_id}"
    client = await hass_client()
    flow = await _start_fix(client, issue_id)
    assert flow["step_id"] == "confirm"
    resp = await client.post(f"/api/repairs/issues/fix/{flow['flow_id']}", json={})
    assert (await resp.json())["type"] == "create_entry"
    await hass.async_block_till_done()
    assert not mock_config_entry.runtime_data.data.control.blocked
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


async def test_fix_flow_aborts_when_not_loaded(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    hass_storage: dict[str, Any],
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
) -> None:
    """With the entry unloaded, the flow aborts with not_loaded."""
    _blocked(hass_storage, mock_config_entry)
    mock_client.get_charger.return_value = make_charger(is_connected=True)
    await setup_integration(hass, mock_config_entry)
    assert await async_setup_component(hass, "repairs", {})
    await hass.config_entries.async_unload(mock_config_entry.entry_id)
    client = await hass_client()
    flow = await _start_fix(client, f"start_blocked_{mock_config_entry.entry_id}")
    assert flow["type"] == "abort"
    assert flow["reason"] == "not_loaded"
