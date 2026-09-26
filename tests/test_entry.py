"""Tests for the config entry helpers."""

import json
from unittest.mock import AsyncMock, MagicMock

from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.nortec_go.const import CONF_EXPIRES_AT, CONF_REFRESH_TOKEN
from custom_components.nortec_go.entry import (
    create_client,
    tokens_from_data,
    tokens_to_data,
)

from .conftest import FAKE_DEVICE_ID, FAKE_TOKENS


def test_tokens_to_data() -> None:
    """Tokens become three JSON-safe strings."""
    data = tokens_to_data(FAKE_TOKENS)
    assert data == {
        CONF_ACCESS_TOKEN: "fake-access-token",
        CONF_REFRESH_TOKEN: "fake-refresh-token",
        CONF_EXPIRES_AT: "2030-01-01T12:00:00+00:00",
    }
    assert json.loads(json.dumps(data)) == data


def test_tokens_round_trip() -> None:
    """Tokens survive the round trip, and expires_at keeps its UTC offset."""
    tokens = tokens_from_data(tokens_to_data(FAKE_TOKENS))
    assert tokens == FAKE_TOKENS
    assert tokens.expires_at.utcoffset() is not None


def test_tokens_from_data_ignores_other_keys() -> None:
    """Other entry data (email, device_id) doesn't disturb the conversion."""
    data = {"email": "x", "device_id": "y", **tokens_to_data(FAKE_TOKENS)}
    assert tokens_from_data(data) == FAKE_TOKENS


async def test_create_client(hass: HomeAssistant, mock_client_class: MagicMock) -> None:
    """The client gets HA's shared session and the given keyword arguments."""
    callback = AsyncMock()
    client = create_client(
        hass,
        tokens=FAKE_TOKENS,
        device_id=FAKE_DEVICE_ID,
        on_tokens_refreshed=callback,
    )
    assert client is mock_client_class.return_value
    mock_client_class.assert_called_once_with(
        async_get_clientsession(hass),
        tokens=FAKE_TOKENS,
        device_id=FAKE_DEVICE_ID,
        on_tokens_refreshed=callback,
    )


async def test_create_client_defaults(
    hass: HomeAssistant, mock_client_class: MagicMock
) -> None:
    """Without arguments the client starts with no tokens and makes its own device_id."""
    create_client(hass)
    mock_client_class.assert_called_once_with(
        async_get_clientsession(hass),
        tokens=None,
        device_id=None,
        on_tokens_refreshed=None,
    )
