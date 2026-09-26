"""Config flow for Nortec Go."""

from collections.abc import Mapping
import logging
from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_DEVICE_ID, CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from pynortecgo import (
    ApiError,
    AuthError,
    Charger,
    ChargerNotFoundError,
    MultipleChargersError,
    NortecGoClient,
    NortecGoConnectionError,
    RateLimitError,
    Tokens,
)
import voluptuous as vol  # noqa: TID251  (HA 2026.9.3's flow API is typed for voluptuous schemas)

from .const import DOMAIN
from .entry import create_client, tokens_to_data

_LOGGER = logging.getLogger(__name__)

DEFAULT_TITLE = "Nortec Go"

EMAIL_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")
)
PASSWORD_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
)
USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): EMAIL_SELECTOR,
        vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR,
    }
)
REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR})


async def _async_sign_in(
    client: NortecGoClient, email: str, password: str
) -> tuple[Charger, Tokens] | str:
    """Log in once and read the charger; return them, or the error key for the form."""
    try:
        await client.login(email, password)
        charger = await client.get_charger()
    except AuthError:
        return "invalid_auth"
    except NortecGoConnectionError, ApiError:
        return "cannot_connect"
    except RateLimitError:
        return "rate_limited"
    except ChargerNotFoundError:
        return "no_charger"
    except MultipleChargersError:
        return "multiple_chargers"
    except Exception:
        # Never log the email or password; pynortecgo's messages hold neither.
        _LOGGER.exception("Unexpected error while signing in to Nortec Go")
        return "unknown"
    tokens = client.tokens
    assert tokens is not None  # login() sets them
    return charger, tokens


class NortecGoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Nortec Go."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the email and password, then create the entry."""
        errors: dict[str, str] = {}
        suggested: dict[str, Any] | None = None
        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            client = create_client(self.hass)
            result = await _async_sign_in(client, email, user_input[CONF_PASSWORD])
            if isinstance(result, str):
                errors["base"] = result
                suggested = {CONF_EMAIL: email}
            else:
                charger, tokens = result
                await self.async_set_unique_id(str(charger.id))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=charger.name or DEFAULT_TITLE,
                    data={
                        CONF_EMAIL: email,
                        CONF_DEVICE_ID: client.device_id,
                        **tokens_to_data(tokens),
                    },
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, suggested),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauth when the stored tokens are rejected."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the password again and store the new tokens."""
        entry = self._get_reauth_entry()
        email: str = entry.data[CONF_EMAIL]
        errors: dict[str, str] = {}
        if user_input is not None:
            client = create_client(self.hass, device_id=entry.data[CONF_DEVICE_ID])
            result = await _async_sign_in(client, email, user_input[CONF_PASSWORD])
            if isinstance(result, str):
                errors["base"] = result
            else:
                charger, tokens = result
                await self.async_set_unique_id(str(charger.id))
                self._abort_if_unique_id_mismatch(reason="wrong_account")
                return self.async_update_reload_and_abort(
                    entry, data_updates=tokens_to_data(tokens)
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=REAUTH_SCHEMA,
            description_placeholders={"email": email},
            errors=errors,
        )
