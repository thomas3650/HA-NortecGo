"""The Nortec Go coordinator: charger and car polling, price reads and the quarter-hour tick."""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
import logging

from homeassistant.core import CALLBACK_TYPE, HassJob, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_call_later, async_track_time_change
from homeassistant.helpers.typing import UNDEFINED
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from pynortecgo import (
    ApiError,
    AuthError,
    Charger,
    ChargerNotFoundError,
    ChargeState,
    MultipleVehiclesError,
    NortecGoClient,
    NortecGoConnectionError,
    NortecGoError,
    RateLimitError,
    UnexpectedResponseError,
    Vehicle,
    VehicleNotFoundError,
)

from .charge_control import ChargeControl, ChargeControlState, charge_status
from .const import (
    CAR_READ_MIN_AGE,
    DOMAIN,
    FAST_READ_MAX_AGE,
    INTERVAL_CHANGING,
    INTERVAL_CHARGING,
    INTERVAL_IDLE,
    PRICE_READ_HOURS,
    PRICE_READ_MINUTE,
    PRICE_RETRY_DELAY,
    TICK_MINUTES,
)
from .entry import NortecGoConfigEntry
from .prices import KnownSlots, PriceStore, merge_forecast, next_price_read, prune

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class NortecGoData:
    """One read of the charger and the car, with the charge control's state.

    vehicle is None until the car is read. read_at is when the charger was last read
    successfully.
    """

    charger: Charger
    vehicle: Vehicle | None
    control: ChargeControlState
    read_at: datetime


def interval_for(
    charger: Charger, control: ChargeControlState, age: timedelta
) -> timedelta:
    """The next polling interval, from the charge status and the last good read's age (D29, D31)."""
    if charge_status(charger, control) in ("starting", "stopping"):
        if control.start_pending or control.stop_pending or age < FAST_READ_MAX_AGE:
            return INTERVAL_CHANGING
        return INTERVAL_CHARGING  # the charger's own state, not seen for a while: a charge is open
    if charger.charge_state is ChargeState.CHARGING:
        return INTERVAL_CHARGING
    return INTERVAL_IDLE


def car_device_identifier(charger_id: str) -> tuple[str, str]:
    """The car device's identifier, keyed on the charger (§2.1)."""
    return (DOMAIN, f"{charger_id}_car")


class NortecGoCoordinator(DataUpdateCoordinator[NortecGoData]):
    """Reads the charger and car on a state-based interval, and the prices on a schedule."""

    config_entry: NortecGoConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: NortecGoConfigEntry, client: NortecGoClient
    ) -> None:
        """Set up the coordinator for one entry."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=INTERVAL_IDLE,
            always_update=False,
        )
        assert entry.unique_id is not None  # the config flow always sets it
        self.client = client
        self.charge_control = ChargeControl(
            hass,
            entry,
            client,
            on_change=self._async_control_changed,
            request_refresh=self.async_read_now,
        )
        self.charger_id = entry.unique_id
        self.has_car = True
        self.known_prices: KnownSlots = {}
        self.price_currency: str | None = None
        self._car_checked = False
        self._car_failing = False
        self._vehicle: Vehicle | None = None
        self._car_read_at: datetime | None = None
        self._read_car_next = False
        self._price_store = PriceStore(hass, entry.entry_id)
        self._prices_failing = False
        self._price_retry: CALLBACK_TYPE | None = None
        # The setup read can schedule a retry before the timers start.
        entry.async_on_unload(self._async_cancel_price_retry)

    async def _async_update_data(self) -> NortecGoData:
        """Read the charger, then the car when due; set the next interval."""
        start_attempts = self.charge_control.start_attempts
        # The user sees our translated texts; the client's text goes only to the debug log (#37).
        try:
            charger = await self._async_read_charger()
        except AuthError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="auth_failed"
            ) from err
        except RateLimitError as err:
            raise UpdateFailed(
                retry_after=err.retry_after,
                translation_domain=DOMAIN,
                translation_key="rate_limited",
            ) from err
        except NortecGoConnectionError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="cannot_connect"
            ) from err
        except ApiError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="api_error"
            ) from err
        except ChargerNotFoundError as err:
            raise ConfigEntryError(
                translation_domain=DOMAIN, translation_key="charger_not_found"
            ) from err
        except UnexpectedResponseError as err:
            raise ConfigEntryError(
                translation_domain=DOMAIN, translation_key="unexpected_response"
            ) from err
        except NortecGoError as err:
            # Last: the specific errors above are its subclasses. A later client version may add more.
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="read_failed"
            ) from err

        self.charge_control.on_charger_read(charger, start_attempts)
        self._async_update_charger_device(charger)
        read_at = dt_util.utcnow()
        if self._car_due(read_at):
            self._car_read_at = read_at
            self._read_car_next = False
            vehicle = await self._async_read_vehicle()
        else:
            vehicle = self._vehicle
        control = self.charge_control.state
        self.update_interval = interval_for(charger, control, timedelta(0))
        return NortecGoData(
            charger=charger, vehicle=vehicle, control=control, read_at=read_at
        )

    async def _async_read_charger(self) -> Charger:
        """Read the charger; a failed read first sets the next interval from the last good one (D31)."""
        try:
            return await self.client.get_charger()
        except NortecGoError as err:
            _LOGGER.debug("Reading the charger failed: %s", err)
            if self.data is not None:
                self.update_interval = interval_for(
                    self.data.charger,
                    self.charge_control.state,
                    dt_util.utcnow() - self.data.read_at,
                )
            raise

    def _car_due(self, now: datetime) -> bool:
        """Read the car the first time, when asked, or when its last try is old enough (§3.2)."""
        return (
            self._read_car_next
            or self._car_read_at is None
            or now - self._car_read_at >= CAR_READ_MIN_AGE
        )

    @callback
    def _async_control_changed(self) -> None:
        """Carry a control change made outside a read to the entities.

        Not async_set_updated_data: it would mark a failed coordinator as successful and
        cancel a requested read.
        """
        if self.data is None:
            return
        control = self.charge_control.state
        self.data = replace(self.data, control=control)
        # Before the read right away: if that read fails, HA reuses this interval.
        self.update_interval = interval_for(
            self.data.charger, control, dt_util.utcnow() - self.data.read_at
        )
        self.async_update_listeners()

    async def async_read_now(self, *, with_car: bool = False) -> None:
        """Read the charger now, not debounced; the car too when asked (§3.3)."""
        if with_car:
            self._read_car_next = True
        await self.async_refresh()

    async def _async_read_vehicle(self) -> Vehicle | None:
        """Read the car; a car error never fails the update (§4.2)."""
        if not self.has_car:
            return None
        try:
            vehicle = await self.client.get_vehicle()
        except AuthError as err:
            _LOGGER.debug("Reading the car was rejected: %s", err)
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="auth_failed"
            ) from err
        except (VehicleNotFoundError, MultipleVehiclesError) as err:
            if not self._car_checked:
                self._car_checked = True
                self.has_car = False
                _LOGGER.info("No car entities: %s", err)
                return None
            self._log_car_error(err)
            return self._vehicle
        except NortecGoError as err:
            self._car_checked = True
            self._log_car_error(err)
            return self._vehicle

        self._car_checked = True
        if self._car_failing:
            self._car_failing = False
            _LOGGER.info("Reading the car works again")
        self._vehicle = vehicle
        self._async_update_car_device(vehicle)
        return vehicle

    def _log_car_error(self, err: NortecGoError) -> None:
        """Log the first car read failure of a run at warning."""
        if not self._car_failing:
            self._car_failing = True
            _LOGGER.warning("Could not read the car; keeping its last data: %s", err)

    @callback
    def _async_update_car_device(self, vehicle: Vehicle) -> None:
        """Bring the car device's name, brand and model up to date (§2.1)."""
        registry = dr.async_get(self.hass)
        identifier = car_device_identifier(self.charger_id)
        if (
            registry.async_get_device_by_identifier(
                identifier, self.config_entry.entry_id
            )
            is None
        ):
            return  # the entities create the device
        # Updates the existing device; an empty name falls back to the translated "Car".
        registry.async_get_or_create(
            config_entry_id=self.config_entry.entry_id,
            identifiers={identifier},
            name=vehicle.name or UNDEFINED,
            translation_key=None if vehicle.name else "car",
            manufacturer=vehicle.brand or UNDEFINED,
            model=vehicle.model or UNDEFINED,
        )

    @callback
    def _async_update_charger_device(self, charger: Charger) -> None:
        """Follow a rename of the charger in the app (#22); the owner's own name still wins."""
        registry = dr.async_get(self.hass)
        device = registry.async_get_device_by_identifier(
            (DOMAIN, self.charger_id), self.config_entry.entry_id
        )
        if device is None:
            return  # the entities create the device
        name = charger.name or self.config_entry.title
        if device.name != name:
            registry.async_update_device(device.id, name=name)

    async def async_load_prices(self) -> None:
        """Load the stored slots, without yesterday's, and the prices' currency."""
        stored = await self._price_store.async_load()
        self.known_prices = prune(
            stored.slots, dt_util.utcnow(), dt_util.get_default_time_zone()
        )
        self.price_currency = stored.currency

    async def async_read_prices(
        self, *, during_setup: bool = False, retry_on_failure: bool = False
    ) -> None:
        """Read the forecast, merge, prune and save it with its currency; keep the known slots on failure (§4.3).

        A failed read asked to retry on failure is read once more later (D37).
        """
        try:
            forecast = await self.client.get_price_forecast()
        except AuthError as err:
            _LOGGER.debug("Reading the price forecast was rejected: %s", err)
            self._async_cancel_price_retry()
            if during_setup:
                raise ConfigEntryAuthFailed(
                    translation_domain=DOMAIN, translation_key="auth_failed"
                ) from err
            self.config_entry.async_start_reauth(self.hass)
            return
        except NortecGoError as err:
            self._log_price_error(err)
            if retry_on_failure:
                self._async_schedule_price_retry(err)
            return
        self._async_cancel_price_retry()
        if self._prices_failing:
            self._prices_failing = False
            _LOGGER.info("Reading the price forecast works again")
        self.known_prices = prune(
            merge_forecast(self.known_prices, forecast),
            dt_util.utcnow(),
            dt_util.get_default_time_zone(),
        )
        if forecast.currency is not None:
            self.price_currency = forecast.currency
        await self._price_store.async_save(self.known_prices, self.price_currency)
        self.async_update_listeners()

    def _log_price_error(self, err: NortecGoError) -> None:
        """Log the first price read failure of a run at warning, later ones at debug (D37)."""
        level = logging.DEBUG if self._prices_failing else logging.WARNING
        self._prices_failing = True
        _LOGGER.log(
            level,
            "Could not read the price forecast; keeping the known prices: %s",
            err,
        )

    @callback
    def _async_schedule_price_retry(self, err: NortecGoError) -> None:
        """Read the prices once more later, unless the next scheduled read comes first (D37)."""
        delay = PRICE_RETRY_DELAY
        if isinstance(err, RateLimitError) and err.retry_after is not None:
            delay = max(delay, timedelta(seconds=err.retry_after))
        now = dt_util.utcnow()
        if now + delay >= next_price_read(now, dt_util.get_default_time_zone()):
            return
        self._async_cancel_price_retry()

        @callback
        def _due(_now: datetime) -> None:
            self._price_retry = None
            self.async_start_price_read()

        self._price_retry = async_call_later(
            self.hass,
            delay,
            HassJob(_due, f"{DOMAIN} price read retry", cancel_on_shutdown=True),
        )

    @callback
    def _async_cancel_price_retry(self) -> None:
        """Cancel a pending price read retry, if any."""
        if self._price_retry is not None:
            self._price_retry()
            self._price_retry = None

    @callback
    def async_start_price_read(self, *, retry_on_failure: bool = False) -> None:
        """Start one price read as a background task that unload cancels."""
        self.config_entry.async_create_background_task(
            self.hass,
            self.async_read_prices(retry_on_failure=retry_on_failure),
            f"{DOMAIN} price read",
        )

    @callback
    def async_start_timers(self) -> None:
        """Start the price reads and the quarter-hour tick; unload stops them."""

        @callback
        def _price_time(now: datetime) -> None:
            # The scheduled read replaces a pending retry (D37).
            self._async_cancel_price_retry()
            self.async_start_price_read(retry_on_failure=True)

        @callback
        def _tick(now: datetime) -> None:
            self.async_update_listeners()

        self.config_entry.async_on_unload(
            async_track_time_change(
                self.hass,
                _price_time,
                hour=PRICE_READ_HOURS,
                minute=PRICE_READ_MINUTE,
                second=0,
            )
        )
        self.config_entry.async_on_unload(
            async_track_time_change(self.hass, _tick, minute=TICK_MINUTES, second=0)
        )
