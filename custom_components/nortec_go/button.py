"""The Nortec Go Refresh button: reads the charger, the car and the prices now (D27)."""

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import NortecGoCoordinator
from .entity import NortecGoChargerEntity
from .entry import NortecGoConfigEntry

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NortecGoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the Refresh button."""
    async_add_entities([NortecGoRefreshButton(entry.runtime_data)])


class NortecGoRefreshButton(NortecGoChargerEntity, ButtonEntity):
    """Reads the charger, the car and the prices when pressed."""

    def __init__(self, coordinator: NortecGoCoordinator) -> None:
        """Name the button Refresh."""
        super().__init__(coordinator, "refresh")

    @property
    def available(self) -> bool:
        """Available after a failed read too, so the read can be tried again."""
        return True

    async def async_press(self) -> None:
        """Read the charger and the car (debounced), then the prices."""
        await self.coordinator.async_request_refresh()
        await self.coordinator.async_read_prices()
