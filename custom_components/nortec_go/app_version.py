"""Tracks calls the service refused for the app version, and the repair issue for them."""

from enum import StrEnum
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pynortecgo import ChargeStartError, UnsupportedAppVersionError

from .const import APP_VERSION_ISSUE_ID, DOMAIN
from .entry import NortecGoConfigEntry

_LOGGER = logging.getLogger(__name__)


class AppVersionCall(StrEnum):
    """The kinds of call that can be refused for the app version."""

    CHARGER_READ = "charger_read"
    CAR_READ = "car_read"
    PRICE_READ = "price_read"
    START = "start"
    STOP = "stop"


def is_refused(err: BaseException) -> bool:
    """Whether the service refused the app version, directly or as a start's cause."""
    if isinstance(err, UnsupportedAppVersionError):
        return True
    return isinstance(err, ChargeStartError) and isinstance(
        err.__cause__, UnsupportedAppVersionError
    )


def async_delete_app_version_issue(hass: HomeAssistant, entry_id: str) -> None:
    """Delete the entry's app version repair issue, if there is one."""
    ir.async_delete_issue(hass, DOMAIN, APP_VERSION_ISSUE_ID.format(entry_id=entry_id))


class AppVersionTracker:
    """Keeps the repair issue up while any kind of call is refused for the app version."""

    def __init__(self, hass: HomeAssistant, entry: NortecGoConfigEntry) -> None:
        """Set up the tracker for one entry, with nothing refused."""
        self._hass = hass
        self._entry = entry
        self._refused: set[AppVersionCall] = set()
        self._closed = False

    @property
    def refused_calls(self) -> frozenset[AppVersionCall]:
        """The kinds of call whose last result was a refusal."""
        return frozenset(self._refused)

    def refused(self, call: AppVersionCall) -> None:
        """Record a refused call; the first one raises the issue."""
        if self._closed:
            return
        was_empty = not self._refused
        self._refused.add(call)
        if was_empty:
            ir.async_create_issue(
                self._hass,
                DOMAIN,
                APP_VERSION_ISSUE_ID.format(entry_id=self._entry.entry_id),
                is_fixable=False,
                is_persistent=False,
                severity=ir.IssueSeverity.ERROR,
                translation_key="app_version",
                translation_placeholders={"name": self._entry.title},
            )

    def succeeded(self, call: AppVersionCall) -> None:
        """Record a call that returned; the last one to do so deletes the issue."""
        if self._closed or call not in self._refused:
            return
        self._refused.discard(call)
        if not self._refused:
            async_delete_app_version_issue(self._hass, self._entry.entry_id)
            _LOGGER.info("The Nortec Go service accepts the app version again")

    def close(self) -> None:
        """Ignore later results, for calls still in flight at unload."""
        self._closed = True
