"""Nortec Go sensors: the price for EV Smart Charging, the charge status, the open charge's energy, power and cost, the total energy, the last charge's cost, the last read and the car's values."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util
from pynortecgo import ActiveCharge, Charger, Vehicle

from .charge_control import CHARGE_STATUS_OPTIONS, charge_status
from .coordinator import NortecGoCoordinator
from .costs import charge_cost, last_charge_completed_at, last_charge_cost
from .entity import NortecGoCarEntity, NortecGoChargerEntity
from .entry import NortecGoConfigEntry
from .prices import current_price, prices_today, prices_tomorrow

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class NortecGoCarSensorDescription(SensorEntityDescription):
    """A car sensor and how to read it from the car."""

    value_fn: Callable[[Vehicle], StateType | datetime]


CAR_SENSORS: tuple[NortecGoCarSensorDescription, ...] = (
    NortecGoCarSensorDescription(
        key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda vehicle: vehicle.battery_level,
    ),
    NortecGoCarSensorDescription(
        key="charge_limit",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda vehicle: vehicle.charge_limit,
    ),
    NortecGoCarSensorDescription(
        key="last_seen",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda vehicle: vehicle.last_seen,
    ),
)


@dataclass(frozen=True, kw_only=True)
class NortecGoChargeSensorDescription(SensorEntityDescription):
    """A sensor for the open charge, its value when no charge is open, and how to read it."""

    no_charge_value: float | None
    value_fn: Callable[[ActiveCharge], float | None]


CHARGE_SENSORS: tuple[NortecGoChargeSensorDescription, ...] = (
    NortecGoChargeSensorDescription(
        key="charge_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        no_charge_value=None,
        value_fn=lambda active: active.kwh,
    ),
    NortecGoChargeSensorDescription(
        key="charging_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        no_charge_value=0.0,
        value_fn=lambda active: active.kw,
    ),
)


@dataclass(frozen=True, kw_only=True)
class NortecGoCostSensorDescription(SensorEntityDescription):
    """A cost sensor: how to read it from the charger, and when its cycle started, if it has cycles."""

    value_fn: Callable[[Charger], float | None]
    last_reset_fn: Callable[[Charger], datetime | None] | None = None


# Cost this charge has no state class: a per-charge value without last_reset would give a
# wrong statistics sum. Last charge cost starts a new cycle per completed charge (D42).
COST_SENSORS: tuple[NortecGoCostSensorDescription, ...] = (
    NortecGoCostSensorDescription(
        key="charge_cost",
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        value_fn=charge_cost,
    ),
    NortecGoCostSensorDescription(
        key="last_charge_cost",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        value_fn=last_charge_cost,
        last_reset_fn=last_charge_completed_at,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NortecGoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the charger sensors, and the car sensors when the account has a car."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        NortecGoPriceSensor(coordinator),
        NortecGoChargeStatusSensor(coordinator),
        NortecGoLastReadSensor(coordinator),
        NortecGoTotalEnergySensor(coordinator),
    ]
    entities.extend(
        NortecGoChargeSensor(coordinator, description) for description in CHARGE_SENSORS
    )
    entities.extend(
        NortecGoCostSensor(coordinator, description) for description in COST_SENSORS
    )
    if coordinator.has_car:
        entities.extend(
            NortecGoCarSensor(coordinator, description) for description in CAR_SENSORS
        )
    async_add_entities(entities)


class NortecGoPriceSensor(NortecGoChargerEntity, SensorEntity):
    """The current price, with EV Smart Charging's day lists (§3.4)."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _unrecorded_attributes = frozenset({"prices_today", "prices_tomorrow"})

    def __init__(self, coordinator: NortecGoCoordinator) -> None:
        """Name the sensor Current price."""
        super().__init__(coordinator, "current_price")

    @property
    def available(self) -> bool:
        """Always available, so the lists are always there (§4.4)."""
        return True

    @property
    def native_unit_of_measurement(self) -> str:
        """The forecast's currency per kWh, or Home Assistant's while none is known (D34)."""
        currency = self.coordinator.price_currency or self.hass.config.currency
        return f"{currency}/kWh"

    @property
    def native_value(self) -> float | None:
        """The known price of the current slot."""
        return current_price(self.coordinator.known_prices, dt_util.utcnow())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """prices_today and prices_tomorrow in EV Smart Charging's format."""
        now = dt_util.utcnow()
        time_zone = dt_util.get_default_time_zone()
        known = self.coordinator.known_prices
        return {
            "prices_today": prices_today(known, now, time_zone),
            "prices_tomorrow": prices_tomorrow(known, now, time_zone),
        }


class NortecGoChargeStatusSensor(NortecGoChargerEntity, SensorEntity):
    """The charge's phase and the start guard (§2.2)."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = CHARGE_STATUS_OPTIONS

    def __init__(self, coordinator: NortecGoCoordinator) -> None:
        """Name the sensor Charge status."""
        super().__init__(coordinator, "charge_status")

    @property
    def native_value(self) -> str | None:
        """The status, or None (unknown) for an unknown charger state."""
        data = self.coordinator.data
        return charge_status(data.charger, data.control)


class NortecGoLastReadSensor(NortecGoChargerEntity, SensorEntity):
    """When the charger was last read successfully (§4)."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: NortecGoCoordinator) -> None:
        """Name the sensor Last read."""
        super().__init__(coordinator, "last_read")

    @property
    def available(self) -> bool:
        """Always available: after a failed read it shows how old the data is."""
        return True

    @property
    def native_value(self) -> datetime:
        """The last successful read's time."""
        return self.coordinator.data.read_at


class NortecGoChargeSensor(NortecGoChargerEntity, SensorEntity):
    """A sensor for one of the open charge's values."""

    entity_description: NortecGoChargeSensorDescription

    def __init__(
        self,
        coordinator: NortecGoCoordinator,
        description: NortecGoChargeSensorDescription,
    ) -> None:
        """Set up the sensor from its description."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        """The charge's value, or the no-charge value when no charge is open."""
        active = self.coordinator.data.charger.active_charge
        if active is None:
            return self.entity_description.no_charge_value
        return self.entity_description.value_fn(active)


class NortecGoTotalEnergySensor(NortecGoChargerEntity, SensorEntity):
    """The energy delivered since the sensor was added, summed per charge (D47)."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    # total_increasing: a restart from 0 (a lost store, a re-added entry) is a new cycle.
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: NortecGoCoordinator) -> None:
        """Name the sensor Total energy."""
        super().__init__(coordinator, "total_energy")

    @property
    def native_value(self) -> float:
        """The ledger's total, rounded so the state carries no noise from adding floats."""
        return round(self.coordinator.data.total_energy_kwh, 3)


class NortecGoCostSensor(NortecGoChargerEntity, SensorEntity):
    """A cost the client reports, in the charger's currency (D42)."""

    entity_description: NortecGoCostSensorDescription

    def __init__(
        self,
        coordinator: NortecGoCoordinator,
        description: NortecGoCostSensorDescription,
    ) -> None:
        """Set up the sensor from its description."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_unit_of_measurement(self) -> str:
        """The charger's currency, then the forecast's, then Home Assistant's (D34, D42)."""
        return (
            self.coordinator.data.charger.currency
            or self.coordinator.price_currency
            or self.hass.config.currency
        )

    @property
    def native_value(self) -> float | None:
        """The cost, or None (unknown) when the client has none."""
        return self.entity_description.value_fn(self.coordinator.data.charger)

    @property
    def last_reset(self) -> datetime | None:
        """When the sensor's cycle started: the last charge's completion time, if it has cycles."""
        last_reset_fn = self.entity_description.last_reset_fn
        if last_reset_fn is None:
            return None
        return last_reset_fn(self.coordinator.data.charger)


class NortecGoCarSensor(NortecGoCarEntity, SensorEntity):
    """A sensor for one of the car's values."""

    entity_description: NortecGoCarSensorDescription

    def __init__(
        self,
        coordinator: NortecGoCoordinator,
        description: NortecGoCarSensorDescription,
    ) -> None:
        """Set up the sensor from its description."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType | datetime:
        """The car's value, or None when the car doesn't report it."""
        vehicle = self.coordinator.data.vehicle
        return None if vehicle is None else self.entity_description.value_fn(vehicle)
