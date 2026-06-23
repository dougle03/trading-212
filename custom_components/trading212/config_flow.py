"""Config flow for the Trading 212 integration."""

from __future__ import annotations

import logging
from typing import Any

from aiohttp import ClientSession
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_API_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    Trading212AuthError,
    Trading212Client,
    Trading212ConnectionError,
    Trading212Error,
    Trading212RateLimitError,
)
from .const import (
    CONF_ACCOUNT_LABEL,
    CONF_ENVIRONMENT,
    CONF_UPDATE_INTERVAL,
    DEFAULT_ACCOUNT_LABEL,
    DEFAULT_ENVIRONMENT,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    ENVIRONMENT_URLS,
    MIN_UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class Trading212ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Trading 212."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            environment = user_input[CONF_ENVIRONMENT]
            account_label = user_input[CONF_ACCOUNT_LABEL].strip()
            update_interval = int(user_input[CONF_UPDATE_INTERVAL])

            if update_interval < MIN_UPDATE_INTERVAL:
                errors[CONF_UPDATE_INTERVAL] = "update_interval_too_low"
            else:
                try:
                    await _validate_input(
                        hass=self.hass,
                        session=async_get_clientsession(self.hass),
                        api_token=user_input[CONF_API_TOKEN],
                        environment=environment,
                    )
                except Trading212AuthError:
                    errors["base"] = "auth"
                except Trading212RateLimitError:
                    errors["base"] = "rate_limited"
                except Trading212ConnectionError:
                    errors["base"] = "cannot_connect"
                except Trading212Error:
                    errors["base"] = "unknown"
                except Exception:
                    _LOGGER.exception("Unexpected Trading 212 config flow error")
                    errors["base"] = "unknown"
                else:
                    await self.async_set_unique_id(
                        f"{DOMAIN}_{environment}_{account_label.lower()}"
                    )
                    self._abort_if_unique_id_configured()

                    return self.async_create_entry(
                        title=account_label,
                        data={
                            CONF_API_TOKEN: user_input[CONF_API_TOKEN],
                            CONF_ENVIRONMENT: environment,
                            CONF_ACCOUNT_LABEL: account_label,
                            CONF_UPDATE_INTERVAL: update_interval,
                        },
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema(user_input),
            errors=errors,
        )


async def _validate_input(
    hass: HomeAssistant,
    session: ClientSession,
    api_token: str,
    environment: str,
) -> None:
    """Validate the user's Trading 212 token by fetching account summary."""
    client = Trading212Client(
        session=session,
        api_token=api_token,
        environment=environment,
    )
    await client.get_account_summary()


def _user_schema(user_input: dict[str, Any] | None = None) -> vol.Schema:
    """Return the config flow user schema."""
    suggested = user_input or {}

    return vol.Schema(
        {
            vol.Required(
                CONF_API_TOKEN,
                default=suggested.get(CONF_API_TOKEN, ""),
            ): str,
            vol.Required(
                CONF_ENVIRONMENT,
                default=suggested.get(CONF_ENVIRONMENT, DEFAULT_ENVIRONMENT),
            ): vol.In(list(ENVIRONMENT_URLS)),
            vol.Required(
                CONF_ACCOUNT_LABEL,
                default=suggested.get(CONF_ACCOUNT_LABEL, DEFAULT_ACCOUNT_LABEL),
            ): str,
            vol.Required(
                CONF_UPDATE_INTERVAL,
                default=suggested.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
            ): vol.All(vol.Coerce(int), vol.Range(min=MIN_UPDATE_INTERVAL)),
        }
    )
