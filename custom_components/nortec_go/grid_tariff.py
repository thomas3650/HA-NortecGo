"""The grid tariff the client hands over, kept across restarts.

The integration keeps the client's dict unchanged: it doesn't read, check or migrate it.
"""

from collections.abc import Mapping
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import GRID_TARIFF_STORE_KEY, GRID_TARIFF_STORE_VERSION

_LOGGER = logging.getLogger(__name__)


class GridTariffStore:
    """The grid tariff of one config entry, in Home Assistant's storage."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Use the store file of this entry."""
        self._store: Store[dict[str, Any]] = Store(
            hass,
            GRID_TARIFF_STORE_VERSION,
            GRID_TARIFF_STORE_KEY.format(entry_id=entry_id),
        )

    async def async_load(self) -> dict[str, Any] | None:
        """Load the saved tariff; None if the file is missing or isn't a dict."""
        data: Any = await self._store.async_load()
        if data is None:
            return None
        if not isinstance(data, dict):
            _LOGGER.warning(
                "Ignoring the stored grid tariff: it has an unexpected shape"
            )
            return None
        return data

    async def async_save(self, tariff: Mapping[str, Any]) -> None:
        """Save the tariff at once."""
        await self._store.async_save(dict(tariff))

    async def async_remove(self) -> None:
        """Delete the file."""
        await self._store.async_remove()
