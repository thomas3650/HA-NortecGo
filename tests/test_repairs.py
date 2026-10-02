"""Tests for the Nortec Go repair fix flows."""

from datetime import timedelta
from http import HTTPStatus
import json
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pynortecgo import ChargerState, ChargeState, VehicleNotFoundError
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.nortec_go.const import (
    CAR_GONE_ISSUE_ID,
    DOMAIN,
    STOP_FAILED_ISSUE_ID,
)
from custom_components.nortec_go.coordinator import car_device_identifier

from .conftest import FAKE_CHARGER_ID, make_charger, setup_integration


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


async def _car_gone(
    hass: HomeAssistant, entry: MockConfigEntry, mock_client: AsyncMock
) -> str:
    """Set the entry up and let the car go; return the issue's ID."""
    await setup_integration(hass, entry)
    assert await async_setup_component(hass, "repairs", {})
    mock_client.get_vehicle.side_effect = VehicleNotFoundError("no car")
    await entry.runtime_data.async_read_now(with_car=True)
    await hass.async_block_till_done()
    return CAR_GONE_ISSUE_ID.format(entry_id=entry.entry_id)


async def test_car_gone_fix_reloads_and_removes_the_car_device(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Confirming reloads the entry; with the car still gone, its device and entities go."""
    issue_id = await _car_gone(hass, mock_config_entry, mock_client)
    identifier = car_device_identifier(str(FAKE_CHARGER_ID))
    entry_id = mock_config_entry.entry_id
    assert device_registry.async_get_device_by_identifier(identifier, entry_id)
    assert entity_registry.async_get("sensor.family_car_battery") is not None

    client = await hass_client()
    flow = await _start_fix(client, issue_id)
    assert flow["step_id"] == "confirm"
    assert flow["description_placeholders"] == {"name": mock_config_entry.title}
    resp = await client.post(f"/api/repairs/issues/fix/{flow['flow_id']}", json={})
    assert (await resp.json())["type"] == "create_entry"
    await hass.async_block_till_done(wait_background_tasks=True)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert not mock_config_entry.runtime_data.has_car
    assert device_registry.async_get_device_by_identifier(identifier, entry_id) is None
    assert entity_registry.async_get("sensor.family_car_battery") is None
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


async def test_car_gone_fix_keeps_a_car_that_is_back(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Confirming when the car is back: the reload keeps the device and its entities."""
    issue_id = await _car_gone(hass, mock_config_entry, mock_client)
    mock_client.get_vehicle.side_effect = None

    client = await hass_client()
    flow = await _start_fix(client, issue_id)
    resp = await client.post(f"/api/repairs/issues/fix/{flow['flow_id']}", json={})
    assert (await resp.json())["type"] == "create_entry"
    await hass.async_block_till_done(wait_background_tasks=True)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_config_entry.runtime_data.has_car
    assert device_registry.async_get_device_by_identifier(
        car_device_identifier(str(FAKE_CHARGER_ID)), mock_config_entry.entry_id
    )
    battery = hass.states.get("sensor.family_car_battery")
    assert battery is not None
    assert battery.state == "55.0"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


async def test_car_gone_fix_aborts_without_the_entry(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
) -> None:
    """An issue whose entry no longer exists: the flow aborts with entry_not_found."""
    await setup_integration(hass, mock_config_entry)
    assert await async_setup_component(hass, "repairs", {})
    issue_id = CAR_GONE_ISSUE_ID.format(entry_id="missing")
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=True,
        is_persistent=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="car_gone",
        translation_placeholders={"name": "Gone"},
        data={"entry_id": "missing"},
    )

    client = await hass_client()
    flow = await _start_fix(client, issue_id)
    assert flow["type"] == "abort"
    assert flow["reason"] == "entry_not_found"


def _given_up(
    hass_storage: dict[str, Any], entry: MockConfigEntry, *, blocked: bool = False
) -> None:
    """A stored stop past its 30 minutes: the control gives up at load and raises the issue."""
    key = f"nortec_go.{entry.entry_id}.charge_control"
    hass_storage[key] = {
        "version": 1,
        "minor_version": 2,
        "key": key,
        "data": {
            "blocked_since": "2026-09-26T20:00:00+00:00" if blocked else None,
            "block_reason": "start_blocked" if blocked else None,
            "start_pending_since": None,
            "stop_asked_since": (dt_util.utcnow() - timedelta(minutes=31)).isoformat(),
            "stop_tries": 0,
            "stop_tried_at": None,
        },
    }


async def test_stop_failed_fix_dismisses_the_issue(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    hass_storage: dict[str, Any],
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
) -> None:
    """Confirming the stop notice dismisses it and calls nothing."""
    _given_up(hass_storage, mock_config_entry)
    mock_client.get_charger.return_value = make_charger(
        is_connected=True, charge_state=ChargeState.CHARGING
    )
    await setup_integration(hass, mock_config_entry)
    assert await async_setup_component(hass, "repairs", {})
    issue_id = STOP_FAILED_ISSUE_ID.format(entry_id=mock_config_entry.entry_id)
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None
    client = await hass_client()
    flow = await _start_fix(client, issue_id)
    assert flow["step_id"] == "confirm"
    resp = await client.post(f"/api/repairs/issues/fix/{flow['flow_id']}", json={})
    assert (await resp.json())["type"] == "create_entry"
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
    mock_client.stop_charge.assert_not_awaited()
    mock_client.start_charge.assert_not_awaited()


async def test_stop_failed_fix_leaves_a_start_block(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    hass_storage: dict[str, Any],
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
) -> None:
    """Confirming the stop notice while starts are blocked leaves the block and its issue in place."""
    _given_up(hass_storage, mock_config_entry, blocked=True)
    # An unknown charger state: neither "off", which would delete the notice, nor evidence
    # that clears the block.
    mock_client.get_charger.return_value = make_charger(
        is_connected=True, state=ChargerState.UNKNOWN
    )
    await setup_integration(hass, mock_config_entry)
    assert await async_setup_component(hass, "repairs", {})
    issue_id = STOP_FAILED_ISSUE_ID.format(entry_id=mock_config_entry.entry_id)
    client = await hass_client()
    flow = await _start_fix(client, issue_id)
    resp = await client.post(f"/api/repairs/issues/fix/{flow['flow_id']}", json={})
    assert (await resp.json())["type"] == "create_entry"
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
    assert mock_config_entry.runtime_data.data.control.blocked
    assert (
        ir.async_get(hass).async_get_issue(
            DOMAIN, f"start_blocked_{mock_config_entry.entry_id}"
        )
        is not None
    )


def test_stop_failed_texts() -> None:
    """The stop notice's texts, word for word, and the two errors a turn-off no longer raises are gone."""
    strings = json.loads(
        (
            Path(__file__).parent.parent / "custom_components" / DOMAIN / "strings.json"
        ).read_text(encoding="utf-8")
    )
    assert strings["issues"]["stop_failed"] == {
        "title": "A charge stop on {name} couldn't be confirmed",
        "fix_flow": {
            "step": {
                "confirm": {
                    "title": "The charge on {name} may still be running",
                    "description": (
                        "You turned Charge off, but Home Assistant couldn't stop the charge"
                        " or see it stop, and has stopped trying. The charge may still be"
                        " running.\n\nCheck the charger in the Nortec Go app and stop the"
                        " charge there if needed. Turning Charge off again makes Home"
                        " Assistant try again. Select **Submit** to dismiss this notice."
                    ),
                }
            }
        },
    }
    assert "charge_not_stoppable" not in strings["exceptions"]
    assert "stop_failed" not in strings["exceptions"]


def test_car_gone_texts() -> None:
    """The issue's texts, word for word."""
    strings = json.loads(
        (
            Path(__file__).parent.parent / "custom_components" / DOMAIN / "strings.json"
        ).read_text(encoding="utf-8")
    )
    assert strings["issues"]["car_gone"] == {
        "title": "The Nortec Go account of {name} no longer has exactly one car",
        "fix_flow": {
            "step": {
                "confirm": {
                    "title": "Remove the car device of {name}",
                    "description": (
                        "The Nortec Go account no longer has exactly one car, so the car's"
                        " entities are unavailable.\n\nIf the car comes back on the account,"
                        " they work again by themselves and this notice goes away. To remove"
                        " the car device and its entities now, select **Submit**: the"
                        " integration reloads. A restart of Home Assistant removes them too,"
                        " if the account still doesn't have exactly one car."
                    ),
                }
            },
            "abort": {"entry_not_found": "The Nortec Go entry no longer exists."},
        },
    }
