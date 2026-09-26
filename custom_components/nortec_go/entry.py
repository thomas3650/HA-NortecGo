"""The Nortec Go config entry: its type, its stored tokens and its client."""

from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pynortecgo import NortecGoClient, Tokens

from .const import CONF_EXPIRES_AT, CONF_REFRESH_TOKEN

type NortecGoConfigEntry = ConfigEntry[NortecGoClient]


def tokens_to_data(tokens: Tokens) -> dict[str, str]:
    """Return the entry.data fields that store the tokens."""
    return {
        CONF_ACCESS_TOKEN: tokens.access_token,
        CONF_REFRESH_TOKEN: tokens.refresh_token,
        CONF_EXPIRES_AT: tokens.expires_at.isoformat(),
    }


def tokens_from_data(data: Mapping[str, Any]) -> Tokens:
    """Rebuild the tokens from entry.data."""
    return Tokens(
        access_token=data[CONF_ACCESS_TOKEN],
        refresh_token=data[CONF_REFRESH_TOKEN],
        expires_at=datetime.fromisoformat(data[CONF_EXPIRES_AT]),
    )


def create_client(
    hass: HomeAssistant,
    *,
    tokens: Tokens | None = None,
    device_id: str | None = None,
    on_tokens_refreshed: Callable[[Tokens], Awaitable[None]] | None = None,
) -> NortecGoClient:
    """Build a client on Home Assistant's shared aiohttp session."""
    return NortecGoClient(
        async_get_clientsession(hass),
        tokens=tokens,
        device_id=device_id,
        on_tokens_refreshed=on_tokens_refreshed,
    )
