"""The Nortec Go Charge switch: starts and stops a charge (§2.1)."""

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .charge_control import is_charge_on
from .coordinator import NortecGoCoordinator
from .entity import NortecGoChargerEntity
from .entry import NortecGoConfigEntry

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NortecGoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the Charge switch."""
    async_add_entities([NortecGoChargeSwitch(entry.runtime_data)])


class NortecGoChargeSwitch(NortecGoChargerEntity, SwitchEntity):
    """Starts and stops a charge through the charge control."""

    def __init__(self, coordinator: NortecGoCoordinator) -> None:
        """Name the switch Charge."""
        super().__init__(coordinator, "charge")

    @property
    def available(self) -> bool:
        """Available after a failed read too, so turn_off still reaches stop_charge (§2.1)."""
        return True

    @property
    def is_on(self) -> bool:
        """On for an open, not ending charge, or our pending start; off while a stop asked for is stored."""
        data = self.coordinator.data
        return is_charge_on(data.charger, data.control)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start a charge (guarded; never retried)."""
        await self.coordinator.charge_control.async_start()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop the charge."""
        await self.coordinator.charge_control.async_stop()
