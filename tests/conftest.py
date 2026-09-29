"""Fixtures for the Nortec Go tests."""

from collections.abc import Generator, Sequence
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import CONF_DEVICE_ID, CONF_EMAIL
from homeassistant.core import HomeAssistant
from pynortecgo import (
    Charger,
    ChargerState,
    ChargeState,
    NortecGoClient,
    PriceForecast,
    PriceSlot,
    Tokens,
    Vehicle,
)
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nortec_go.const import DOMAIN
from custom_components.nortec_go.entry import tokens_to_data

# Obviously fake values; nothing here comes from a real account (hard rules 3 and 7).
FAKE_EMAIL = "user@example.com"
FAKE_PASSWORD = "fake-password-123"
FAKE_DEVICE_ID = "00000000-0000-4000-8000-000000000000"
FAKE_CHARGER_ID = 918273645
OTHER_CHARGER_ID = 564738291
FAKE_CHARGER_NAME = "Garage charger"
FAKE_VEHICLE_NAME = "Family car"
FAKE_LAST_SEEN = datetime(2026, 9, 26, 8, 30, tzinfo=UTC)
DEFAULT_FORECAST_START = datetime(2026, 9, 26, 22, 0, tzinfo=UTC)
FAKE_TOKENS = Tokens(
    access_token="fake-access-token",
    refresh_token="fake-refresh-token",
    expires_at=datetime(2030, 1, 1, 12, 0, tzinfo=UTC),
)
NEW_TOKENS = Tokens(
    access_token="new-fake-access-token",
    refresh_token="new-fake-refresh-token",
    expires_at=datetime(2030, 1, 2, 12, 0, tzinfo=UTC),
)


def make_charger(
    charger_id: int = FAKE_CHARGER_ID,
    name: str = FAKE_CHARGER_NAME,
    *,
    is_connected: bool = False,
    charge_state: ChargeState | None = None,
    state: ChargerState = ChargerState.AVAILABLE,
) -> Charger:
    """Return a charger; idle and unplugged unless told otherwise."""
    return Charger(
        id=charger_id,
        name=name,
        max_kw=11.0,
        state=state,
        state_raw=state.value,
        is_connected=is_connected,
        charge_state=charge_state,
        charge_state_raw=None if charge_state is None else charge_state.value,
        charge_id=None if charge_state is None else "fake-charge-id",
        can_stop=None if charge_state is None else True,
        charge_kwh=None,
        charge_kw=None,
    )


def make_vehicle(
    *,
    name: str = FAKE_VEHICLE_NAME,
    brand: str | None = "Example",
    model: str | None = "Model E",
    battery_level: float | None = 55.0,
    charge_limit: float | None = 80.0,
    plugged_in: bool | None = False,
    last_seen: datetime | None = FAKE_LAST_SEEN,
) -> Vehicle:
    """Return the account's car with fake values."""
    return Vehicle(
        id=424242,
        name=name,
        capacity_kwh=60.0,
        max_kw_ac=11.0,
        brand=brand,
        model=model,
        battery_level=battery_level,
        charge_limit=charge_limit,
        plugged_in=plugged_in,
        power_delivery_state=None,
        power_delivery_state_raw=None,
        last_seen=last_seen,
    )


def make_forecast(
    start: datetime, prices: Sequence[float], currency: str | None = "DKK"
) -> PriceForecast:
    """Return 15-minute slots from start, one per total price; the spot price is 0.5 less."""
    step = timedelta(minutes=15)
    return PriceForecast(
        area_id=99,
        area_name="Test area",
        currency=currency,
        slots=[
            PriceSlot(
                start=start + i * step,
                end=start + (i + 1) * step,
                price=price,
                spot_price=price - 0.5,
                tariff_estimated=False,
            )
            for i, price in enumerate(prices)
        ],
    )


async def setup_integration(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Add the entry and set it up."""
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant load integrations from custom_components in every test."""


@pytest.fixture
def mock_client_class() -> Generator[MagicMock]:
    """Patch the client class; every construction returns the same mocked client."""
    with patch(
        "custom_components.nortec_go.entry.NortecGoClient", autospec=True
    ) as client_class:
        client = AsyncMock(spec=NortecGoClient)
        client.login.return_value = FAKE_TOKENS
        client.get_charger.return_value = make_charger()
        client.get_vehicle.return_value = make_vehicle()
        client.get_price_forecast.return_value = make_forecast(
            DEFAULT_FORECAST_START, [1.25] * 8
        )
        client.tokens = FAKE_TOKENS
        client.device_id = FAKE_DEVICE_ID
        client_class.return_value = client
        yield client_class


@pytest.fixture
def mock_client(mock_client_class: MagicMock) -> AsyncMock:
    """The mocked client instance."""
    client: AsyncMock = mock_client_class.return_value
    return client


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """A config entry as the user step creates it."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=FAKE_CHARGER_NAME,
        unique_id=str(FAKE_CHARGER_ID),
        data={
            CONF_EMAIL: FAKE_EMAIL,
            CONF_DEVICE_ID: FAKE_DEVICE_ID,
            **tokens_to_data(FAKE_TOKENS),
        },
    )
