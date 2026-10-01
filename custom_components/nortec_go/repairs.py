"""The Nortec Go repair fix flows: allow charge starts again (§3.5), and remove a car that is gone (D44)."""

from typing import Any

from homeassistant.components.repairs import RepairsFlow, RepairsFlowResult
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from .const import CAR_GONE_ISSUE_ID
from .entry import NortecGoConfigEntry


class StartBlockedRepairFlow(RepairsFlow):
    """One confirm step that clears the start block."""

    def __init__(self, entry_id: str) -> None:
        """Remember the entry the issue belongs to."""
        self._entry_id = entry_id

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> RepairsFlowResult:
        """Go to the confirm step."""
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> RepairsFlowResult:
        """Clear the block when the owner confirms."""
        entry: NortecGoConfigEntry | None = self.hass.config_entries.async_get_entry(
            self._entry_id
        )
        if entry is None or entry.state is not ConfigEntryState.LOADED:
            return self.async_abort(reason="not_loaded")
        if user_input is not None:
            entry.runtime_data.charge_control.clear_block()
            return self.async_create_entry(data={})
        return self.async_show_form(
            step_id="confirm", description_placeholders={"name": entry.title}
        )


class CarGoneRepairFlow(RepairsFlow):
    """One confirm step that reloads the entry; its setup removes a car device without a car."""

    def __init__(self, entry_id: str) -> None:
        """Remember the entry the issue belongs to."""
        self._entry_id = entry_id

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> RepairsFlowResult:
        """Go to the confirm step."""
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> RepairsFlowResult:
        """Reload the entry when the owner confirms."""
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if entry is None:
            return self.async_abort(reason="entry_not_found")
        if user_input is not None:
            self.hass.config_entries.async_schedule_reload(self._entry_id)
            return self.async_create_entry(data={})
        return self.async_show_form(
            step_id="confirm", description_placeholders={"name": entry.title}
        )


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None
) -> RepairsFlow:
    """Create the fix flow for a car_gone or a start_blocked issue."""
    assert data is not None  # every issue is created with its entry ID
    entry_id = str(data["entry_id"])
    if issue_id == CAR_GONE_ISSUE_ID.format(entry_id=entry_id):
        return CarGoneRepairFlow(entry_id)
    return StartBlockedRepairFlow(entry_id)
