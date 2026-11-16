"""Tests for the stored grid tariff."""

import logging
from typing import Any

from homeassistant.core import HomeAssistant
import pytest

from custom_components.nortec_go.grid_tariff import GridTariffStore

from .conftest import FAKE_GRID_TARIFF

KEY = "nortec_go.entry1.grid_tariff"
WARNING = "Ignoring the stored grid tariff: it has an unexpected shape"


async def test_store_round_trip(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """The tariff is stored as handed over, and survives save and load."""
    store = GridTariffStore(hass, "entry1")
    await store.async_save(FAKE_GRID_TARIFF)
    assert hass_storage[KEY]["version"] == 1
    assert hass_storage[KEY]["data"] == FAKE_GRID_TARIFF
    assert await GridTariffStore(hass, "entry1").async_load() == FAKE_GRID_TARIFF
    await store.async_remove()
    assert KEY not in hass_storage


async def test_store_missing_file(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """No file gives None, without a warning."""
    with caplog.at_level(logging.WARNING):
        assert await GridTariffStore(hass, "entry1").async_load() is None
    assert WARNING not in caplog.text


@pytest.mark.parametrize("data", [[1, 2], "text", 5])
async def test_store_wrong_shape(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    data: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Data that isn't a dict gives None and one warning."""
    hass_storage[KEY] = {"version": 1, "minor_version": 1, "key": KEY, "data": data}
    with caplog.at_level(logging.WARNING):
        assert await GridTariffStore(hass, "entry1").async_load() is None
    assert caplog.text.count(WARNING) == 1
