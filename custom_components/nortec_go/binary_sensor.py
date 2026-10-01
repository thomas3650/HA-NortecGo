"""Nortec Go binary sensors: the charger's cable and charge, and the car's plug."""

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pynortecgo import Charger, ChargeState, Vehicle

from .coordinator import NortecGoCoordinator
from .entity import NortecGoCarEntity, NortecGoChargerEntity
from .entry import NortecGoConfigEntry

PARALLEL_UPDATES = 0


def connected_to_charger(charger: Charger, vehicle: Vehicle) -> bool | None:
    """Our car at our charger: the cable is connected and the car says it's plugged in."""
    if not charger.is_connected:
        return False
    return vehicle.plugged_in


@dataclass(frozen=True, kw_only=True)
class NortecGoChargerBinarySensorDescription(BinarySensorEntityDescription):
    """A charger binary sensor and how to read it."""

    value_fn: Callable[[Charger], bool | None]


@dataclass(frozen=True, kw_only=True)
class NortecGoCarBinarySensorDescription(BinarySensorEntityDescription):
    """A car binary sensor and how to read it from the charger and the car."""

    value_fn: Callable[[Charger, Vehicle], bool | None]


CHARGER_BINARY_SENSORS: tuple[NortecGoChargerBinarySensorDescription, ...] = (
    NortecGoChargerBinarySensorDescription(
        key="cable_connected",
        device_class=BinarySensorDeviceClass.PLUG,
        value_fn=lambda charger: charger.is_connected,
    ),
    NortecGoChargerBinarySensorDescription(
        key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda charger: charger.charge_state is ChargeState.CHARGING,
    ),
)

CAR_BINARY_SENSORS: tuple[NortecGoCarBinarySensorDescription, ...] = (
    NortecGoCarBinarySensorDescription(
        key="plugged_in",
        device_class=BinarySensorDeviceClass.PLUG,
        value_fn=lambda charger, vehicle: vehicle.plugged_in,
    ),
    NortecGoCarBinarySensorDescription(
        key="connected_to_charger",
        device_class=BinarySensorDeviceClass.PLUG,
        value_fn=connected_to_charger,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NortecGoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the charger binary sensors, and the car ones when the account has a car."""
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [
        NortecGoChargerBinarySensor(coordinator, description)
        for description in CHARGER_BINARY_SENSORS
    ]
    if coordinator.has_car:
        entities.extend(
            NortecGoCarBinarySensor(coordinator, description)
            for description in CAR_BINARY_SENSORS
        )
    async_add_entities(entities)


class NortecGoChargerBinarySensor(NortecGoChargerEntity, BinarySensorEntity):
    """A binary sensor on the charger."""

    entity_description: NortecGoChargerBinarySensorDescription

    def __init__(
        self,
        coordinator: NortecGoCoordinator,
        description: NortecGoChargerBinarySensorDescription,
    ) -> None:
        """Set up the binary sensor from its description."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """The charger's value."""
        return self.entity_description.value_fn(self.coordinator.data.charger)


class NortecGoCarBinarySensor(NortecGoCarEntity, BinarySensorEntity):
    """A binary sensor on the car."""

    entity_description: NortecGoCarBinarySensorDescription

    def __init__(
        self,
        coordinator: NortecGoCoordinator,
        description: NortecGoCarBinarySensorDescription,
    ) -> None:
        """Set up the binary sensor from its description."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """The value from the charger and the car, or None while the car is gone."""
        vehicle = self.coordinator.data.vehicle
        # for mypy: HA doesn't read is_on while the entity is unavailable
        if vehicle is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data.charger, vehicle)
