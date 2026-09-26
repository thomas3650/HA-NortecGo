"""The Nortec Go integration."""

from homeassistant.const import CONF_DEVICE_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryError,
    ConfigEntryNotReady,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from pynortecgo import (
    ApiError,
    AuthError,
    ChargerNotFoundError,
    NortecGoConnectionError,
    RateLimitError,
    Tokens,
    UnexpectedResponseError,
)

from .const import DOMAIN
from .entry import NortecGoConfigEntry, create_client, tokens_from_data, tokens_to_data

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = []


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Nortec Go integration."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: NortecGoConfigEntry) -> bool:
    """Set up Nortec Go from a config entry, with the stored tokens."""

    async def _async_store_tokens(tokens: Tokens) -> None:
        # Runs inside the client's refresh: must not call the client.
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, **tokens_to_data(tokens)}
        )

    client = create_client(
        hass,
        tokens=tokens_from_data(entry.data),
        device_id=entry.data[CONF_DEVICE_ID],
        on_tokens_refreshed=_async_store_tokens,
    )
    # Read the config flow's charger directly; a removed one raises ChargerNotFoundError.
    assert entry.unique_id is not None  # the config flow always sets it
    client.set_charger(int(entry.unique_id))
    # pynortecgo's messages hold no tokens, emails or IDs, so they may be passed on.
    try:
        await client.get_charger()
    except AuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except (NortecGoConnectionError, RateLimitError, ApiError) as err:
        raise ConfigEntryNotReady(str(err)) from err
    except (UnexpectedResponseError, ChargerNotFoundError) as err:
        raise ConfigEntryError(str(err)) from err

    entry.runtime_data = client
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: NortecGoConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
