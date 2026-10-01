"""The Nortec Go Refresh button: reads the charger, the car and the prices now (D27)."""

from contextlib import suppress

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import NortecGoCoordinator
from .entity import NortecGoChargerEntity
from .entry import NortecGoConfigEntry

PARALLEL_UPDATES = 1


def read_error(err: BaseException | None) -> HomeAssistantError:
    """The error a press raises for a failed charger read: the read's own text, or read_failed.

    Always a plain HomeAssistantError: the coordinator's error classes belong to setup and polling.
    """
    if (
        isinstance(err, HomeAssistantError)
        and err.translation_domain == DOMAIN
        and err.translation_key
    ):
        return HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key=err.translation_key,
            translation_placeholders=err.translation_placeholders,
        )
    return HomeAssistantError(translation_domain=DOMAIN, translation_key="read_failed")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NortecGoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the Refresh button."""
    async_add_entities([NortecGoRefreshButton(entry.runtime_data)])


class NortecGoRefreshButton(NortecGoChargerEntity, ButtonEntity):
    """Reads the charger, the car and the prices when pressed; raises when a read fails (D43)."""

    def __init__(self, coordinator: NortecGoCoordinator) -> None:
        """Name the button Refresh."""
        super().__init__(coordinator, "refresh")

    @property
    def available(self) -> bool:
        """Available after a failed read too, so the read can be tried again."""
        return True

    async def async_press(self) -> None:
        """Read the charger and the car now, then the prices; raise when a read failed."""
        coordinator = self.coordinator
        await coordinator.async_read_now(with_car=True)
        # last_exception isn't cleared by a good read, so go by last_update_success.
        if coordinator.last_update_success:
            await coordinator.async_read_prices(raise_on_failure=True)
            return
        failed = coordinator.last_exception
        # The prices are read all the same; the charger's error wins when both fail (D43).
        with suppress(HomeAssistantError):
            await coordinator.async_read_prices(raise_on_failure=True)
        raise read_error(failed) from failed
