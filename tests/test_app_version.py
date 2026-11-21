"""Tests for the app version tracker and its repair issue."""

from datetime import timedelta
import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from pynortecgo import (
    ApiError,
    ChargeStartError,
    ChargeStartStep,
    NortecGoConnectionError,
    UnsupportedAppVersionError,
)
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.nortec_go.app_version import (
    AppVersionCall,
    AppVersionTracker,
    is_refused,
)
from custom_components.nortec_go.charge_control import async_remove_charge_control
from custom_components.nortec_go.const import APP_VERSION_ISSUE_ID, DOMAIN

from .conftest import setup_integration

COMPONENT = Path(__file__).parent.parent / "custom_components" / "nortec_go"
BACK = "The Nortec Go service accepts the app version again"


def _issue(hass: HomeAssistant, entry: MockConfigEntry) -> ir.IssueEntry | None:
    return ir.async_get(hass).async_get_issue(
        DOMAIN, APP_VERSION_ISSUE_ID.format(entry_id=entry.entry_id)
    )


def _create_issue(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    ir.async_create_issue(
        hass,
        DOMAIN,
        APP_VERSION_ISSUE_ID.format(entry_id=entry.entry_id),
        is_fixable=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key="app_version",
    )


def _start_error(cause: Exception | None, hold: bool = False) -> ChargeStartError:
    err = ChargeStartError(ChargeStartStep.CONFIRM, hold)
    err.__cause__ = cause
    return err


def test_is_refused() -> None:
    """Only the refused app version counts, directly or as a start's cause."""
    refused = UnsupportedAppVersionError("GET /example")
    assert is_refused(refused)
    assert is_refused(_start_error(refused, True))
    assert is_refused(_start_error(refused, False))
    assert not is_refused(ApiError("GET /example", 500))
    assert not is_refused(_start_error(ApiError("GET /example", 500)))
    assert not is_refused(_start_error(None))


async def test_first_refusal_raises_issue(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """The first refusal creates the repair issue."""
    mock_config_entry.add_to_hass(hass)
    AppVersionTracker(hass, mock_config_entry).refused(AppVersionCall.START)
    issue = _issue(hass, mock_config_entry)
    assert issue is not None
    assert issue.translation_key == "app_version"
    assert issue.is_fixable is False
    assert issue.is_persistent is False
    assert issue.severity is ir.IssueSeverity.ERROR
    assert issue.translation_placeholders == {"name": mock_config_entry.title}


async def test_second_refusal_keeps_one_issue(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """A second refused call adds to the set, not a second issue."""
    mock_config_entry.add_to_hass(hass)
    tracker = AppVersionTracker(hass, mock_config_entry)
    tracker.refused(AppVersionCall.START)
    tracker.refused(AppVersionCall.STOP)
    assert _issue(hass, mock_config_entry) is not None
    assert len(ir.async_get(hass).issues) == 1
    assert tracker.refused_calls == {AppVersionCall.START, AppVersionCall.STOP}


async def test_issue_stays_until_last_call_succeeds(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The issue goes only when every refused call has succeeded."""
    caplog.set_level(logging.INFO)
    mock_config_entry.add_to_hass(hass)
    tracker = AppVersionTracker(hass, mock_config_entry)
    tracker.refused(AppVersionCall.START)
    tracker.refused(AppVersionCall.STOP)
    assert _issue(hass, mock_config_entry) is not None
    tracker.succeeded(AppVersionCall.START)
    assert _issue(hass, mock_config_entry) is not None
    assert BACK not in caplog.text
    tracker.succeeded(AppVersionCall.STOP)
    assert _issue(hass, mock_config_entry) is None
    assert caplog.text.count(BACK) == 1


async def test_success_of_unrefused_call_changes_nothing(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A success with nothing refused makes no issue and no log line."""
    caplog.set_level(logging.INFO)
    mock_config_entry.add_to_hass(hass)
    tracker = AppVersionTracker(hass, mock_config_entry)
    tracker.succeeded(AppVersionCall.CHARGER_READ)
    assert _issue(hass, mock_config_entry) is None
    assert BACK not in caplog.text


async def test_unload_deletes_issue(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: object
) -> None:
    """Unloading deletes the issue, and the closed tracker raises none."""
    await setup_integration(hass, mock_config_entry)
    tracker = mock_config_entry.runtime_data.app_version
    tracker.refused(AppVersionCall.CHARGER_READ)
    assert _issue(hass, mock_config_entry) is not None
    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    assert _issue(hass, mock_config_entry) is None
    tracker.refused(AppVersionCall.START)
    assert _issue(hass, mock_config_entry) is None


async def test_remove_deletes_issue(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Removing the entry's charge control deletes the issue of an unloaded entry."""
    mock_config_entry.add_to_hass(hass)
    _create_issue(hass, mock_config_entry)
    assert _issue(hass, mock_config_entry) is not None
    await async_remove_charge_control(hass, mock_config_entry.entry_id)
    assert _issue(hass, mock_config_entry) is None


async def test_setup_deletes_stale_issue(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: object
) -> None:
    """A successful setup leaves no issue from an earlier run."""
    _create_issue(hass, mock_config_entry)
    assert _issue(hass, mock_config_entry) is not None
    await setup_integration(hass, mock_config_entry)
    assert _issue(hass, mock_config_entry) is None


@pytest.mark.parametrize(
    "error", [NortecGoConnectionError("network down"), ApiError("GET /example", 500)]
)
async def test_other_error_changes_nothing(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    error: Exception,
) -> None:
    """Another error neither clears nor duplicates the issue, and raises none by itself."""
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    tracker = coordinator.app_version

    mock_client.get_charger.side_effect = error
    await coordinator.async_refresh()
    assert _issue(hass, mock_config_entry) is None

    mock_client.get_charger.side_effect = UnsupportedAppVersionError("GET /example")
    await coordinator.async_refresh()
    assert _issue(hass, mock_config_entry) is not None

    mock_client.get_charger.side_effect = error
    await coordinator.async_refresh()
    assert _issue(hass, mock_config_entry) is not None
    assert len(ir.async_get(hass).issues) == 1
    assert tracker.refused_calls == {AppVersionCall.CHARGER_READ}


async def test_failed_setup_keeps_issue_and_next_setup_clears_it(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
) -> None:
    """A setup that fails on a refusal keeps the issue; the setup that works deletes it."""
    mock_client.get_charger.side_effect = UnsupportedAppVersionError("GET /example")
    await setup_integration(hass, mock_config_entry)
    state = mock_config_entry.state  # a local, so mypy doesn't keep the narrowing
    assert state is ConfigEntryState.SETUP_RETRY
    assert _issue(hass, mock_config_entry) is not None

    mock_client.get_charger.side_effect = None
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
    await hass.async_block_till_done(wait_background_tasks=True)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert _issue(hass, mock_config_entry) is None


@pytest.mark.parametrize("name", ["strings.json", "translations/en.json"])
def test_issue_strings_exist(name: str) -> None:
    """The issue has a title and a description in the strings and the English file."""
    issue = json.loads((COMPONENT / name).read_text())["issues"]["app_version"]
    assert issue["title"]
    assert issue["description"]
