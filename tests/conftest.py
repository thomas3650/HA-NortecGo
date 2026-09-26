"""Fixtures for the Nortec Go tests."""

from collections.abc import Generator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import CONF_DEVICE_ID, CONF_EMAIL
from pynortecgo import Charger, ChargerState, NortecGoClient, Tokens
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
    charger_id: int = FAKE_CHARGER_ID, name: str = FAKE_CHARGER_NAME
) -> Charger:
    """Return an idle charger with no open charge."""
    return Charger(
        id=charger_id,
        name=name,
        max_kw=11.0,
        state=ChargerState.AVAILABLE,
        state_raw="available",
        is_connected=False,
        charge_state=None,
        charge_state_raw=None,
        charge_id=None,
        can_stop=None,
    )


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
