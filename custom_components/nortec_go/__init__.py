"""The Nortec Go integration."""

from homeassistant.const import CONF_DEVICE_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.typing import ConfigType
from pynortecgo import Tokens

from .charge_control import async_remove_charge_control
from .const import DOMAIN
from .coordinator import NortecGoCoordinator, car_device_identifier
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
    await coordinator.charge_control.async_load()
    await coordinator.async_load_prices()
    await coordinator.async_config_entry_first_refresh()
    if not coordinator.has_car:
        # No car now: remove the car device (and so its entities) from an earlier setup.
        device_registry = dr.async_get(hass)
        device = device_registry.async_get_device_by_identifier(
            car_device_identifier(coordinator.charger_id), entry.entry_id
        )
        if device is not None:
            device_registry.async_remove_device(device.id)
    await coordinator.async_read_prices(during_setup=True)
    coordinator.async_start_timers()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_remove_entry(hass: HomeAssistant, entry: NortecGoConfigEntry) -> None:
    """Delete the entry's stored prices and charge control, and its repair issue."""
    await PriceStore(hass, entry.entry_id).async_remove()
    await async_remove_charge_control(hass, entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: NortecGoConfigEntry) -> bool:
    """Unload a config entry; the charge control saves and stops taking calls."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.charge_control.async_shutdown()
    return unloaded
