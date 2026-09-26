"""Config flow for Nortec Go."""

from homeassistant.config_entries import ConfigFlow

from .const import DOMAIN


class NortecGoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Nortec Go. The steps come in a later task."""
