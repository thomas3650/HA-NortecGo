"""Tests for the Nortec Go sensors."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.sensor import (
    ATTR_STATE_CLASS,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_UNIT_OF_MEASUREMENT,
    PERCENTAGE,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    EntityCategory,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pynortecgo import (
    Charger,
    ChargerState,
    ChargeState,
    NortecGoConnectionError,
    VehicleNotFoundError,
)
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.nortec_go.charge_control import CHARGE_STATUS_OPTIONS
from custom_components.nortec_go.const import DOMAIN, MISSING_SLOT_PRICE

from .conftest import (
    FAKE_CHARGER_ID,
    FAKE_LAST_SEEN,
    make_charger,
    make_forecast,
    make_vehicle,
    setup_integration,
)

MIDNIGHT = datetime(2026, 9, 26, 22, 0, tzinfo=UTC)  # 00:00 local on 27 Sep
PRICE = "sensor.garage_charger_current_price"


@pytest.fixture(autouse=True)
async def copenhagen(hass: HomeAssistant) -> None:
    """Run every test in the owner's time zone, with DKK."""
    await hass.config.async_set_time_zone("Europe/Copenhagen")
    hass.config.currency = "DKK"


async def test_current_price(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """State is the current slot's price; attributes are the two lists; unit is DKK/kWh."""
    freezer.move_to(MIDNIGHT + timedelta(minutes=20))  # 00:20 local
    mock_client.get_price_forecast.return_value = make_forecast(
        MIDNIGHT, [1.0, 2.0, 3.0]
    )
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(PRICE)
    assert state is not None
    assert state.state == "2.0"
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == "DKK/kWh"
    assert state.attributes[ATTR_STATE_CLASS] == SensorStateClass.MEASUREMENT
    assert ATTR_DEVICE_CLASS not in state.attributes
    today = state.attributes["prices_today"]
    assert len(today) == 96
    assert today[2]["price"] == 3.0
    assert state.attributes["prices_tomorrow"] == []


async def test_price_unit_follows_forecast_currency(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The unit is the forecast's currency, not Home Assistant's."""
    hass.config.currency = "EUR"
    freezer.move_to(MIDNIGHT + timedelta(minutes=5))
    mock_client.get_price_forecast.return_value = make_forecast(MIDNIGHT, [1.0])
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(PRICE)
    assert state is not None
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == "DKK/kWh"


async def test_price_unit_falls_back_to_home_assistant_currency(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """With no currency known, the unit is Home Assistant's currency."""
    hass.config.currency = "EUR"
    freezer.move_to(MIDNIGHT + timedelta(minutes=5))
    mock_client.get_price_forecast.return_value = make_forecast(
        MIDNIGHT, [1.0], currency=None
    )
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(PRICE)
    assert state is not None
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == "EUR/kWh"


async def test_price_unit_survives_a_reload_with_a_failing_read(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The stored currency is used when the price read fails after a reload."""
    hass.config.currency = "EUR"
    freezer.move_to(MIDNIGHT + timedelta(minutes=5))
    mock_client.get_price_forecast.return_value = make_forecast(MIDNIGHT, [1.0])
    await setup_integration(hass, mock_config_entry)

    mock_client.get_price_forecast.side_effect = NortecGoConnectionError("network down")
    assert await hass.config_entries.async_reload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(PRICE)
    assert state is not None
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == "DKK/kWh"


async def test_price_unit_follows_a_currency_learned_after_setup(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A currency first seen in a later read changes the unit at the next state write."""
    hass.config.currency = "EUR"
    freezer.move_to(MIDNIGHT + timedelta(minutes=5))
    mock_client.get_price_forecast.return_value = make_forecast(
        MIDNIGHT, [1.0], currency=None
    )
    await setup_integration(hass, mock_config_entry)
    assert hass.states.get(PRICE).attributes[ATTR_UNIT_OF_MEASUREMENT] == "EUR/kWh"  # type: ignore[union-attr]

    mock_client.get_price_forecast.return_value = make_forecast(MIDNIGHT, [1.0])
    await mock_config_entry.runtime_data.async_read_prices()
    await hass.async_block_till_done()
    assert hass.states.get(PRICE).attributes[ATTR_UNIT_OF_MEASUREMENT] == "DKK/kWh"  # type: ignore[union-attr]


async def test_current_price_follows_the_tick(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """At :15 the state moves to the next slot without an API call."""
    freezer.move_to(MIDNIGHT + timedelta(minutes=10))
    mock_client.get_price_forecast.return_value = make_forecast(MIDNIGHT, [1.0, 2.0])
    await setup_integration(hass, mock_config_entry)
    assert hass.states.get(PRICE).state == "1.0"  # type: ignore[union-attr]

    when = MIDNIGHT + timedelta(minutes=15)
    freezer.move_to(when)
    async_fire_time_changed(hass, when)
    await hass.async_block_till_done()
    assert hass.states.get(PRICE).state == "2.0"  # type: ignore[union-attr]
    assert mock_client.get_price_forecast.await_count == 1


async def test_current_price_with_nothing_known(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Late evening, no stored prices, forecast failing: available, unknown, 96 padded slots."""
    freezer.move_to(MIDNIGHT + timedelta(hours=21, minutes=30))  # 21:30 local
    mock_client.get_price_forecast.side_effect = NortecGoConnectionError("network down")
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(PRICE)
    assert state is not None
    assert state.state == STATE_UNKNOWN
    today = state.attributes["prices_today"]
    assert len(today) == 96
    assert today[-1]["price"] == MISSING_SLOT_PRICE


async def test_current_price_stays_available_when_charger_fails(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A failing charger read leaves Current price and its lists in place."""
    freezer.move_to(MIDNIGHT + timedelta(minutes=5))
    mock_client.get_price_forecast.return_value = make_forecast(MIDNIGHT, [1.0])
    await setup_integration(hass, mock_config_entry)

    mock_client.get_charger.side_effect = NortecGoConnectionError("network down")
    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    state = hass.states.get(PRICE)
    assert state is not None
    assert state.state == "1.0"
    assert len(state.attributes["prices_today"]) == 96
    assert hass.states.get("sensor.family_car_battery").state == STATE_UNAVAILABLE  # type: ignore[union-attr]
    cable = hass.states.get("binary_sensor.garage_charger_cable_connected")
    assert cable is not None
    assert cable.state == STATE_UNAVAILABLE


def test_price_lists_not_recorded() -> None:
    """The recorder leaves the two lists out."""
    from custom_components.nortec_go.sensor import NortecGoPriceSensor  # noqa: PLC0415

    assert {
        "prices_today",
        "prices_tomorrow",
    } <= NortecGoPriceSensor._unrecorded_attributes  # noqa: SLF001


@pytest.mark.parametrize(
    ("charger", "expected"),
    [
        (make_charger(is_connected=False), "unplugged"),
        (make_charger(is_connected=True), "idle"),
        (
            make_charger(is_connected=True, charge_state=ChargeState.CHARGING),
            "charging",
        ),
        (
            make_charger(is_connected=True, state=ChargerState.BUSY_NON_RELEASED),
            "not_released",
        ),
        (make_charger(is_connected=True, state=ChargerState.UNKNOWN), STATE_UNKNOWN),
    ],
)
async def test_charge_status_sensor(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    charger: Charger,
    expected: str,
) -> None:
    """Charge status is an enum sensor with the spec's options."""
    mock_client.get_charger.return_value = charger
    await setup_integration(hass, mock_config_entry)
    state = hass.states.get("sensor.garage_charger_charge_status")
    assert state is not None
    assert state.state == expected
    assert state.attributes[ATTR_DEVICE_CLASS] == SensorDeviceClass.ENUM
    assert state.attributes["options"] == CHARGE_STATUS_OPTIONS


async def test_charge_status_follows_the_control(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A pending start shows starting at once, without a read."""
    mock_client.get_charger.return_value = make_charger(is_connected=True)
    await setup_integration(hass, mock_config_entry)
    await mock_config_entry.runtime_data.charge_control.async_start()
    state = hass.states.get("sensor.garage_charger_charge_status")
    assert state is not None
    assert state.state == "starting"


LAST_READ = "sensor.garage_charger_last_read"


async def test_last_read_sensor(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    entity_registry: er.EntityRegistry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Last read shows when the charger was read, as a diagnostic timestamp."""
    freezer.move_to("2026-09-27 10:00:00+00:00")
    await setup_integration(hass, mock_config_entry)
    state = hass.states.get(LAST_READ)
    assert state is not None
    assert state.state == "2026-09-27T10:00:00+00:00"
    assert state.attributes["device_class"] == "timestamp"
    registry_entry = entity_registry.async_get(LAST_READ)
    assert registry_entry is not None
    assert registry_entry.entity_category is EntityCategory.DIAGNOSTIC


async def test_last_read_available_after_a_failed_read(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """After a failed read Last read stays available and keeps the last good time."""
    freezer.move_to("2026-09-27 10:00:00+00:00")
    await setup_integration(hass, mock_config_entry)
    mock_client.get_charger.side_effect = NortecGoConnectionError("x")
    freezer.tick(timedelta(minutes=1))
    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    state = hass.states.get(LAST_READ)
    assert state is not None
    assert state.state == "2026-09-27T10:00:00+00:00"


ENERGY = "sensor.garage_charger_energy_this_charge"
POWER = "sensor.garage_charger_charging_power"


def _state(hass: HomeAssistant, entity_id: str) -> str:
    state = hass.states.get(entity_id)
    assert state is not None, entity_id
    return state.state


async def test_charge_energy_and_power_sensors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Energy this charge and Charging power: classes, units, precision, charger device."""
    mock_client.get_charger.return_value = make_charger(
        is_connected=True,
        charge_state=ChargeState.CHARGING,
        charge_kwh=3.25,
        charge_kw=7.4,
    )
    await setup_integration(hass, mock_config_entry)
    charger = _device(device_registry, mock_config_entry, str(FAKE_CHARGER_ID))
    assert charger is not None

    for entity_id, key, value, device_class, unit, state_class, precision in (
        (
            ENERGY,
            "charge_energy",
            "3.25",
            SensorDeviceClass.ENERGY,
            UnitOfEnergy.KILO_WATT_HOUR,
            SensorStateClass.TOTAL_INCREASING,
            2,
        ),
        (
            POWER,
            "charging_power",
            "7.4",
            SensorDeviceClass.POWER,
            UnitOfPower.KILO_WATT,
            SensorStateClass.MEASUREMENT,
            1,
        ),
    ):
        state = hass.states.get(entity_id)
        assert state is not None, entity_id
        assert state.state == value
        assert state.attributes[ATTR_DEVICE_CLASS] == device_class
        assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == unit
        assert state.attributes[ATTR_STATE_CLASS] == state_class
        entry = entity_registry.async_get(entity_id)
        assert entry is not None
        assert entry.unique_id == f"{FAKE_CHARGER_ID}_{key}"
        assert entry.device_id == charger.id
        assert entry.options["sensor"]["suggested_display_precision"] == precision


@pytest.mark.parametrize(
    ("charger", "energy", "power"),
    [
        (make_charger(is_connected=True), STATE_UNKNOWN, "0.0"),
        (
            make_charger(is_connected=True, charge_kwh=5.0, charge_kw=6.0),
            STATE_UNKNOWN,
            "0.0",
        ),
        (
            make_charger(is_connected=True, charge_state=ChargeState.CHARGING),
            STATE_UNKNOWN,
            STATE_UNKNOWN,
        ),
        (
            make_charger(
                is_connected=True,
                charge_state=ChargeState.CHARGING,
                charge_kwh=1.5,
                charge_kw=0.0,
            ),
            "1.5",
            "0.0",
        ),
    ],
    ids=[
        "no_charge",
        "no_charge_ignores_fields",
        "open_charge_no_readings",
        "open_charge_with_readings",
    ],
)
async def test_charge_energy_and_power_values(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    charger: Charger,
    energy: str,
    power: str,
) -> None:
    """No open charge: energy unknown and power 0; an open charge shows its readings or unknown."""
    mock_client.get_charger.return_value = charger
    await setup_integration(hass, mock_config_entry)
    assert _state(hass, ENERGY) == energy
    assert _state(hass, POWER) == power


async def test_charge_energy_and_power_unavailable_after_a_failed_read(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A failed charger read makes both sensors unavailable."""
    mock_client.get_charger.return_value = make_charger(
        is_connected=True,
        charge_state=ChargeState.CHARGING,
        charge_kwh=2.0,
        charge_kw=7.0,
    )
    await setup_integration(hass, mock_config_entry)
    mock_client.get_charger.side_effect = NortecGoConnectionError("network down")
    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, ENERGY) == STATE_UNAVAILABLE
    assert _state(hass, POWER) == STATE_UNAVAILABLE


async def test_charge_energy_starts_a_new_cycle_per_charge(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A charge at 10.5 kWh, then no charge (unknown, 0 kW), then a new charge at 0.2 kWh."""
    mock_client.get_charger.return_value = make_charger(
        is_connected=True,
        charge_state=ChargeState.CHARGING,
        charge_kwh=10.5,
        charge_kw=7.2,
    )
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    seen: list[tuple[str, str, str]] = []

    def record() -> None:
        energy = hass.states.get(ENERGY)
        assert energy is not None
        seen.append(
            (energy.state, _state(hass, POWER), energy.attributes[ATTR_STATE_CLASS])
        )

    record()
    mock_client.get_charger.return_value = make_charger(is_connected=True)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    record()
    mock_client.get_charger.return_value = make_charger(
        is_connected=True,
        charge_state=ChargeState.CHARGING,
        charge_kwh=0.2,
        charge_kw=3.6,
    )
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    record()

    increasing = SensorStateClass.TOTAL_INCREASING
    assert seen == [
        ("10.5", "7.2", increasing),
        (STATE_UNKNOWN, "0.0", increasing),
        ("0.2", "3.6", increasing),
    ]


async def test_car_sensors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Battery, Charge limit and Last seen on the car device."""
    await setup_integration(hass, mock_config_entry)

    battery = hass.states.get("sensor.family_car_battery")
    assert battery is not None
    assert battery.state == "55.0"
    assert battery.attributes[ATTR_DEVICE_CLASS] == SensorDeviceClass.BATTERY
    assert battery.attributes[ATTR_UNIT_OF_MEASUREMENT] == PERCENTAGE
    limit = hass.states.get("sensor.family_car_charge_limit")
    assert limit is not None
    assert limit.state == "80.0"
    assert ATTR_DEVICE_CLASS not in limit.attributes
    seen = hass.states.get("sensor.family_car_last_seen")
    assert seen is not None
    assert seen.state == FAKE_LAST_SEEN.isoformat()
    entry = entity_registry.async_get("sensor.family_car_last_seen")
    assert entry is not None
    assert entry.entity_category is EntityCategory.DIAGNOSTIC
    assert entry.unique_id == f"{FAKE_CHARGER_ID}_last_seen"


async def test_car_values_unknown(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A car that reports nothing shows unknown, not unavailable."""
    mock_client.get_vehicle.return_value = make_vehicle(
        battery_level=None, charge_limit=None, plugged_in=None, last_seen=None
    )
    await setup_integration(hass, mock_config_entry)
    for entity_id in (
        "sensor.family_car_battery",
        "sensor.family_car_charge_limit",
        "sensor.family_car_last_seen",
    ):
        assert hass.states.get(entity_id).state == STATE_UNKNOWN, entity_id  # type: ignore[union-attr]


def _device(
    device_registry: dr.DeviceRegistry, entry: MockConfigEntry, identifier: str
) -> dr.DeviceEntry | None:
    return device_registry.async_get_device_by_identifier(
        (DOMAIN, identifier), entry.entry_id
    )


async def test_devices(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    device_registry: dr.DeviceRegistry,
) -> None:
    """A charger device and a separate car device, not linked."""
    await setup_integration(hass, mock_config_entry)
    charger = _device(device_registry, mock_config_entry, str(FAKE_CHARGER_ID))
    car = _device(device_registry, mock_config_entry, f"{FAKE_CHARGER_ID}_car")
    assert charger is not None
    assert (charger.name, charger.manufacturer) == ("Garage charger", "Nortec")
    assert car is not None
    assert (car.name, car.manufacturer, car.model) == (
        "Family car",
        "Example",
        "Model E",
    )
    assert car.via_device_id is None


async def test_device_name_fallbacks(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    device_registry: dr.DeviceRegistry,
) -> None:
    """An empty charger name uses the entry title; an empty car name becomes "Car"."""
    mock_client.get_charger.return_value = make_charger(name="")
    await setup_integration(hass, mock_config_entry)
    charger = _device(device_registry, mock_config_entry, str(FAKE_CHARGER_ID))
    assert charger is not None
    assert charger.name == mock_config_entry.title

    mock_client.get_vehicle.return_value = make_vehicle(name="")
    await mock_config_entry.runtime_data.async_read_now(with_car=True)
    await hass.async_block_till_done()
    car = _device(device_registry, mock_config_entry, f"{FAKE_CHARGER_ID}_car")
    assert car is not None
    assert car.name == "Car"


async def test_car_placeholder_until_first_read(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    device_registry: dr.DeviceRegistry,
) -> None:
    """A car read failing at setup: device "Car", entities unavailable; a good read fixes both."""
    mock_client.get_vehicle.side_effect = NortecGoConnectionError("network down")
    await setup_integration(hass, mock_config_entry)
    car = _device(device_registry, mock_config_entry, f"{FAKE_CHARGER_ID}_car")
    assert car is not None
    assert car.name == "Car"
    assert hass.states.get("sensor.car_battery").state == STATE_UNAVAILABLE  # type: ignore[union-attr]

    mock_client.get_vehicle.side_effect = None
    await mock_config_entry.runtime_data.async_read_now(with_car=True)
    await hass.async_block_till_done()
    updated = device_registry.async_get(car.id, include_child_devices=False)
    assert updated is not None
    assert updated.name == "Family car"
    assert hass.states.get("sensor.car_battery").state == "55.0"  # type: ignore[union-attr]


async def test_no_car_no_car_entities(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    device_registry: dr.DeviceRegistry,
) -> None:
    """No car on the account: no car device and no car entities."""
    mock_client.get_vehicle.side_effect = VehicleNotFoundError("no car")
    await setup_integration(hass, mock_config_entry)
    assert _device(device_registry, mock_config_entry, f"{FAKE_CHARGER_ID}_car") is None
    assert hass.states.get(PRICE) is not None
    for entity_id in (
        "sensor.family_car_battery",
        "sensor.family_car_charge_limit",
        "sensor.family_car_last_seen",
        "binary_sensor.family_car_plugged_in",
        "binary_sensor.family_car_connected_to_charger",
    ):
        assert hass.states.get(entity_id) is None, entity_id
