"""Tests for the Nortec Go config flow."""

from collections.abc import Mapping
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from homeassistant.config_entries import (
    SOURCE_REAUTH,
    SOURCE_USER,
    ConfigEntryState,
    ConfigFlow,
)
from homeassistant.const import CONF_DEVICE_ID, CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pynortecgo import (
    ApiError,
    AuthError,
    ChargerNotFoundError,
    MultipleChargersError,
    NortecGoConnectionError,
    RateLimitError,
    UnexpectedResponseError,
)
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nortec_go.const import DOMAIN
from custom_components.nortec_go.entry import tokens_from_data, tokens_to_data

from .conftest import (
    FAKE_CHARGER_ID,
    FAKE_CHARGER_NAME,
    FAKE_DEVICE_ID,
    FAKE_EMAIL,
    FAKE_PASSWORD,
    FAKE_TOKENS,
    NEW_TOKENS,
    OTHER_CHARGER_ID,
    make_charger,
)

USER_INPUT = {CONF_EMAIL: FAKE_EMAIL, CONF_PASSWORD: FAKE_PASSWORD}
NEW_EMAIL = "other@example.com"  # fake, like FAKE_EMAIL

# (method that raises, exception, error key)
FLOW_ERRORS = [
    ("login", AuthError("rejected"), "invalid_auth"),
    ("login", NortecGoConnectionError("network down"), "cannot_connect"),
    ("login", ApiError("POST /example", 500), "cannot_connect"),
    ("login", RateLimitError("too many requests"), "rate_limited"),
    ("get_charger", ChargerNotFoundError("no charger"), "no_charger"),
    ("get_charger", MultipleChargersError("two chargers"), "multiple_chargers"),
    ("get_charger", UnexpectedResponseError("GET /example", "bad shape"), "unknown"),
    ("login", RuntimeError("boom"), "unknown"),
]


def _suggested(result: Mapping[str, Any], key: str) -> Any:
    for marker in result["data_schema"].schema:
        if marker == key:
            return (marker.description or {}).get("suggested_value")
    raise AssertionError(key)


async def test_user_flow(
    hass: HomeAssistant, mock_client_class: MagicMock, mock_client: AsyncMock
) -> None:
    """A login creates the entry with tokens and device_id, never the password."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == FAKE_CHARGER_NAME
    assert result["data"] == {
        CONF_EMAIL: FAKE_EMAIL,
        CONF_DEVICE_ID: FAKE_DEVICE_ID,
        **tokens_to_data(FAKE_TOKENS),
    }
    assert CONF_PASSWORD not in result["data"]
    assert result["result"].unique_id == str(FAKE_CHARGER_ID)
    assert result["result"].state is ConfigEntryState.LOADED
    assert mock_client_class.call_args_list[0].kwargs["device_id"] is None
    mock_client.login.assert_awaited_once_with(FAKE_EMAIL, FAKE_PASSWORD)


async def test_user_flow_stores_client_tokens(
    hass: HomeAssistant, mock_client: AsyncMock
) -> None:
    """The stored tokens are client.tokens after get_charger, not login's return value."""
    mock_client.tokens = NEW_TOKENS
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    await hass.async_block_till_done()

    assert tokens_from_data(result["data"]) == NEW_TOKENS


async def test_user_flow_strips_email_not_password(
    hass: HomeAssistant, mock_client: AsyncMock
) -> None:
    """Spaces around the email are dropped; the password is sent as typed."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: f"  {FAKE_EMAIL} ", CONF_PASSWORD: " pass word "},
    )
    await hass.async_block_till_done()

    assert result["data"][CONF_EMAIL] == FAKE_EMAIL
    mock_client.login.assert_awaited_once_with(FAKE_EMAIL, " pass word ")


async def test_user_flow_empty_charger_name(
    hass: HomeAssistant, mock_client: AsyncMock
) -> None:
    """A charger without a name gets the title 'Nortec Go'."""
    mock_client.get_charger.return_value = make_charger(name="")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    await hass.async_block_till_done()

    assert result["title"] == "Nortec Go"


@pytest.mark.parametrize(("method", "error", "key"), FLOW_ERRORS)
async def test_user_flow_errors(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    method: str,
    error: Exception,
    key: str,
) -> None:
    """Each error shows its key, keeps the email, logs in once, and a retry succeeds."""
    getattr(mock_client, method).side_effect = error
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": key}
    assert _suggested(result, CONF_EMAIL) == FAKE_EMAIL
    assert _suggested(result, CONF_PASSWORD) is None
    assert mock_client.login.await_count == 1

    getattr(mock_client, method).side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_client.login.await_count == 2


async def test_user_flow_logs_no_credentials(
    hass: HomeAssistant, mock_client: AsyncMock, caplog: pytest.LogCaptureFixture
) -> None:
    """An unexpected error is logged without the email or password."""
    caplog.set_level(logging.DEBUG, logger="custom_components.nortec_go")
    mock_client.login.side_effect = RuntimeError("boom")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert "Unexpected error" in caplog.text
    assert FAKE_EMAIL not in caplog.text
    assert FAKE_PASSWORD not in caplog.text


async def test_user_flow_already_configured(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """The same charger can't be added twice."""
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_flow_while_reauth_in_progress(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """Adding a charger whose reauth is open aborts as already configured.

    HA leaves reauth flows out of its already_in_progress check, so the entry check decides.
    """
    mock_config_entry.add_to_hass(hass)
    await mock_config_entry.start_reauth_flow(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_flow_parallel_for_same_charger(
    hass: HomeAssistant, mock_client: AsyncMock
) -> None:
    """A second add flow for a charger another add flow has claimed aborts with readable text."""
    first = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    second = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    flow = hass.config_entries.flow._progress[first["flow_id"]]  # noqa: SLF001
    assert isinstance(flow, ConfigFlow)
    await flow.async_set_unique_id(str(FAKE_CHARGER_ID))

    result = await hass.config_entries.flow.async_configure(
        second["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_in_progress"


async def test_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client_class: MagicMock,
    mock_client: AsyncMock,
) -> None:
    """Reauth logs in with the stored email and device_id and stores the new tokens."""
    mock_config_entry.add_to_hass(hass)
    mock_client.tokens = NEW_TOKENS
    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    # HA adds {"name": entry.title} to reauth placeholders itself.
    assert result["description_placeholders"] == {
        "email": FAKE_EMAIL,
        "name": FAKE_CHARGER_NAME,
    }

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: FAKE_PASSWORD}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert tokens_from_data(mock_config_entry.data) == NEW_TOKENS
    assert mock_config_entry.data[CONF_EMAIL] == FAKE_EMAIL
    assert mock_config_entry.data[CONF_DEVICE_ID] == FAKE_DEVICE_ID
    assert CONF_PASSWORD not in mock_config_entry.data
    assert mock_client_class.call_args_list[0].kwargs["device_id"] == FAKE_DEVICE_ID
    mock_client.login.assert_awaited_once_with(FAKE_EMAIL, FAKE_PASSWORD)


async def test_reauth_wrong_account(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """Signing in to an account with another charger aborts and keeps the old data."""
    mock_config_entry.add_to_hass(hass)
    mock_client.get_charger.return_value = make_charger(OTHER_CHARGER_ID)
    result = await mock_config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: FAKE_PASSWORD}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_account"
    assert tokens_from_data(mock_config_entry.data) == FAKE_TOKENS


@pytest.mark.parametrize(("method", "error", "key"), FLOW_ERRORS)
async def test_reauth_errors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    method: str,
    error: Exception,
    key: str,
) -> None:
    """Each reauth error shows its key, logs in once, and a retry succeeds."""
    mock_config_entry.add_to_hass(hass)
    getattr(mock_client, method).side_effect = error
    result = await mock_config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: FAKE_PASSWORD}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": key}
    assert mock_client.login.await_count == 1

    getattr(mock_client, method).side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: FAKE_PASSWORD}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_client.login.await_count == 2


async def test_reconfigure(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client_class: MagicMock,
    mock_client: AsyncMock,
) -> None:
    """Reconfigure signs in once with the new email and the stored device ID, and stores the new sign-in."""
    mock_config_entry.add_to_hass(hass)
    mock_client.tokens = NEW_TOKENS
    result = await mock_config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert _suggested(result, CONF_EMAIL) == FAKE_EMAIL
    assert _suggested(result, CONF_PASSWORD) is None

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: f"  {NEW_EMAIL} ", CONF_PASSWORD: FAKE_PASSWORD},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data[CONF_EMAIL] == NEW_EMAIL
    assert tokens_from_data(mock_config_entry.data) == NEW_TOKENS
    assert mock_config_entry.data[CONF_DEVICE_ID] == FAKE_DEVICE_ID
    assert CONF_PASSWORD not in mock_config_entry.data
    assert mock_config_entry.title == FAKE_CHARGER_NAME
    assert mock_config_entry.unique_id == str(FAKE_CHARGER_ID)
    assert mock_client_class.call_args_list[0].kwargs["device_id"] == FAKE_DEVICE_ID
    mock_client.login.assert_awaited_once_with(NEW_EMAIL, FAKE_PASSWORD)


async def test_reconfigure_wrong_account(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """Signing in to an account with another charger aborts and keeps the old sign-in."""
    mock_config_entry.add_to_hass(hass)
    mock_client.get_charger.return_value = make_charger(OTHER_CHARGER_ID)
    result = await mock_config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: NEW_EMAIL, CONF_PASSWORD: FAKE_PASSWORD}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_account"
    assert mock_config_entry.data[CONF_EMAIL] == FAKE_EMAIL
    assert tokens_from_data(mock_config_entry.data) == FAKE_TOKENS


@pytest.mark.parametrize(("method", "error", "key"), FLOW_ERRORS)
async def test_reconfigure_errors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    caplog: pytest.LogCaptureFixture,
    method: str,
    error: Exception,
    key: str,
) -> None:
    """Each error shows its key, keeps the typed email, logs in once and logs no credentials; a retry succeeds."""
    mock_config_entry.add_to_hass(hass)
    getattr(mock_client, method).side_effect = error
    result = await mock_config_entry.start_reconfigure_flow(hass)
    user_input = {CONF_EMAIL: NEW_EMAIL, CONF_PASSWORD: FAKE_PASSWORD}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert result["errors"] == {"base": key}
    assert _suggested(result, CONF_EMAIL) == NEW_EMAIL
    assert _suggested(result, CONF_PASSWORD) is None
    assert mock_client.login.await_count == 1
    assert mock_config_entry.data[CONF_EMAIL] == FAKE_EMAIL
    assert NEW_EMAIL not in caplog.text
    assert FAKE_PASSWORD not in caplog.text

    getattr(mock_client, method).side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_client.login.await_count == 2
    assert mock_config_entry.data[CONF_EMAIL] == NEW_EMAIL


async def test_setup_auth_error_opens_reauth(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A token rejected at setup opens the reauth form."""
    mock_client.get_charger.side_effect = AuthError("token rejected")
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == SOURCE_REAUTH
    assert flows[0]["step_id"] == "reauth_confirm"
    mock_client.login.assert_not_awaited()
