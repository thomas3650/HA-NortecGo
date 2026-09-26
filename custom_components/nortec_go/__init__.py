"""The Nortec Go integration."""

from homeassistant.const import CONF_DEVICE_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from pynortecgo import Tokens

from .const import DOMAIN
from .coordinator import NortecGoCoordinator
from .entry import NortecGoConfigEntry, create_client, tokens_from_data, tokens_to_data
from .prices import PriceStore

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]


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

    coordinator = NortecGoCoordinator(hass, entry, client)
    await coordinator.async_load_prices()
    await coordinator.async_config_entry_first_refresh()
    await coordinator.async_read_prices(during_setup=True)
    coordinator.async_start_timers()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_remove_entry(hass: HomeAssistant, entry: NortecGoConfigEntry) -> None:
    """Delete the entry's stored prices."""
    await PriceStore(hass, entry.entry_id).async_remove()


async def async_unload_entry(hass: HomeAssistant, entry: NortecGoConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
