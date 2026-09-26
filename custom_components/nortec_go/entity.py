"""Base entities for the Nortec Go charger and car devices."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import NortecGoCoordinator, car_device_identifier


class NortecGoEntity(CoordinatorEntity[NortecGoCoordinator]):
    """An entity with a translated name and the unique ID <charger id>_<key>."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: NortecGoCoordinator, key: str) -> None:
        """Name the entity by its key."""
        super().__init__(coordinator)
        self._attr_translation_key = key
        self._attr_unique_id = f"{coordinator.charger_id}_{key}"


class NortecGoChargerEntity(NortecGoEntity):
    """An entity on the charger device."""

    def __init__(self, coordinator: NortecGoCoordinator, key: str) -> None:
        """Attach the entity to the charger device."""
        super().__init__(coordinator, key)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.charger_id)},
            name=coordinator.data.charger.name or coordinator.config_entry.title,
            manufacturer="Nortec",
        )


class NortecGoCarEntity(NortecGoEntity):
    """An entity on the car device; unavailable until the car has been read."""

    def __init__(self, coordinator: NortecGoCoordinator, key: str) -> None:
        """Attach the entity to the car device, named "Car" until the car is known."""
        super().__init__(coordinator, key)
        vehicle = coordinator.data.vehicle
        device_info = DeviceInfo(
            identifiers={car_device_identifier(coordinator.charger_id)}
        )
        if vehicle is not None and vehicle.name:
            device_info["name"] = vehicle.name
        else:
            device_info["translation_key"] = "car"
        if vehicle is not None and vehicle.brand:
            device_info["manufacturer"] = vehicle.brand
        if vehicle is not None and vehicle.model:
            device_info["model"] = vehicle.model
        self._attr_device_info = device_info

    @property
    def available(self) -> bool:
        """Available when the last update worked and the car has been read."""
        return super().available and self.coordinator.data.vehicle is not None
