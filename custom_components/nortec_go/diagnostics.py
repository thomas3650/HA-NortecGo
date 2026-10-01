"""Diagnostics for Nortec Go: only the sign-in secrets are redacted (D38)."""

from dataclasses import asdict
from typing import Any, Final

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    CONF_ACCESS_TOKEN,
    CONF_DEVICE_ID,
    CONF_EMAIL,
    CONF_PASSWORD,
)
from homeassistant.core import HomeAssistant

from .const import CONF_REFRESH_TOKEN
from .entry import NortecGoConfigEntry

# The password is never stored; it is here in case a later bug stores it. The device ID is
# sent at sign-in. IDs and names stay (D38).
TO_REDACT: Final = {
    CONF_ACCESS_TOKEN,
    CONF_DEVICE_ID,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: NortecGoConfigEntry
) -> dict[str, Any]:
    """Return the entry, the last read and how the reads are going."""
    diagnostics: dict[str, Any] = {
        "entry": {
            "title": entry.title,
            "unique_id": entry.unique_id,
            "data": dict(entry.data),
            "options": dict(entry.options),
        }
    }
    if entry.state is not ConfigEntryState.LOADED:
        # The download is served for any entry; an unloaded one has no coordinator.
        diagnostics.update(
            {"loaded": False, "state": entry.state.value, "reason": entry.reason}
        )
        return async_redact_data(diagnostics, TO_REDACT)

    coordinator = entry.runtime_data
    data = coordinator.data  # set: the entry loads only after a good first read
    error = coordinator.last_exception
    interval = coordinator.update_interval
    slots = coordinator.known_prices
    diagnostics.update(
        {
            "loaded": True,
            "coordinator": {
                "last_update_success": coordinator.last_update_success,
                # HA keeps the last error after a good read; show only a current one.
                "last_exception": (
                    str(error)
                    if error is not None and not coordinator.last_update_success
                    else None
                ),
                "update_interval_seconds": (
                    interval.total_seconds() if interval is not None else None
                ),
                "has_car": coordinator.has_car,
                "car_read_failing": coordinator.car_read_failing,
                "car_gone": coordinator.car_gone,
                "price_read_failing": coordinator.price_read_failing,
                "price_retry_pending": coordinator.price_retry_pending,
            },
            "data": {
                "read_at": data.read_at,
                "charger": asdict(data.charger),
                "vehicle": asdict(data.vehicle) if data.vehicle is not None else None,
                "control": asdict(data.control),
            },
            # A summary: the slots are keyed by datetime and would show every price.
            "prices": {
                "currency": coordinator.price_currency,
                "slot_count": len(slots),
                "first_slot_start": min(slots, default=None),
                "last_slot_start": max(slots, default=None),
            },
            # The Total energy ledger; charge IDs aren't secrets (D38).
            "energy": asdict(coordinator.energy_ledger),
        }
    )
    return async_redact_data(diagnostics, TO_REDACT)
