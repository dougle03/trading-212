"""Config flow for the Trading 212 integration."""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Mapping

from aiohttp import ClientSession
import voluptuous as vol

from homeassistant import config_entries
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
    CONF_API_KEY,
    CONF_API_SECRET,
    CONF_ENVIRONMENT,
    CONF_MAX_POSITION_ENTITIES,
    CONF_POSITION_DISPLAY_FORMAT,
    CONF_UPDATE_INTERVAL,
    DEFAULT_ACCOUNT_LABEL,
    DEFAULT_ENVIRONMENT,
    DEFAULT_FEATURE_OPTIONS,
    DEFAULT_MAX_POSITION_ENTITIES,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    ENVIRONMENT_URLS,
    FEATURE_OPTION_DEFAULTS,
    FEATURE_ACCOUNT_SUMMARY,
    FEATURE_DIVIDENDS_SUMMARY,
    FEATURE_MOVERS_DAILY,
    FEATURE_OPTIONS,
    FEATURE_ORDERS_SUMMARY,
    FEATURE_PER_PIE_ENTITIES,
    FEATURE_PER_POSITION_ENTITIES,
    FEATURE_PIES_SUMMARY,
    FEATURE_POSITIONS_SUMMARY,
    MAX_POSITION_ENTITIES,
    MIN_POSITION_ENTITIES,
    MIN_UPDATE_INTERVAL,
    POSITION_DISPLAY_FORMATS,
)
from .options import get_entry_options, merge_entry_options

_LOGGER = logging.getLogger(__name__)


class Trading212ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Trading 212."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return Trading212OptionsFlow(config_entry)

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        require_account_label = bool(self._async_current_entries())

        if user_input is not None:
            environment = user_input[CONF_ENVIRONMENT]
            account_label = _normalise_account_label(user_input.get(CONF_ACCOUNT_LABEL))
            update_interval = int(user_input[CONF_UPDATE_INTERVAL])

            if require_account_label and account_label is None:
                errors[CONF_ACCOUNT_LABEL] = "account_label_required"
            elif update_interval < MIN_UPDATE_INTERVAL:
                errors[CONF_UPDATE_INTERVAL] = "update_interval_too_low"
            else:
                try:
                    summary = await _validate_input(
                        hass=self.hass,
                        session=async_get_clientsession(self.hass),
                        api_key=user_input[CONF_API_KEY],
                        api_secret=user_input[CONF_API_SECRET],
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
                    account_identifier = _account_identifier_from_summary(
                        summary,
                        api_key=user_input[CONF_API_KEY],
                        api_secret=user_input[CONF_API_SECRET],
                        environment=environment,
                    )
                    await self.async_set_unique_id(
                        f"{DOMAIN}_{environment}_{account_identifier}"
                    )
                    self._abort_if_unique_id_configured()

                    data = {
                        CONF_API_KEY: user_input[CONF_API_KEY],
                        CONF_API_SECRET: user_input[CONF_API_SECRET],
                        CONF_ENVIRONMENT: environment,
                        CONF_UPDATE_INTERVAL: update_interval,
                    }
                    if account_label is not None:
                        data[CONF_ACCOUNT_LABEL] = account_label

                    return self.async_create_entry(
                        title=account_label or DEFAULT_ACCOUNT_LABEL,
                        data=data,
                        options=get_entry_options(),
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema(user_input, require_account_label),
            errors=errors,
        )


class Trading212OptionsFlow(config_entries.OptionsFlow):
    """Handle Trading 212 feature options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialise the options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Manage feature options."""
        if user_input is not None:
            options = merge_entry_options(self._config_entry.options, user_input)
            return self.async_create_entry(title="", data=options)

        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(get_entry_options(self._config_entry.options)),
        )


async def _validate_input(
    hass: HomeAssistant,
    session: ClientSession,
    api_key: str,
    api_secret: str,
    environment: str,
) -> dict[str, Any]:
    """Validate the user's Trading 212 credentials by fetching account summary."""
    client = Trading212Client(
        session=session,
        api_key=api_key,
        api_secret=api_secret,
        environment=environment,
    )
    return await client.get_account_summary()


def _user_schema(
    user_input: dict[str, Any] | None = None,
    require_account_label: bool = False,
) -> vol.Schema:
    """Return the config flow user schema."""
    suggested = user_input or {}
    schema: dict[Any, Any] = {
        vol.Required(
            CONF_API_KEY,
            default=suggested.get(CONF_API_KEY, ""),
        ): str,
        vol.Required(
            CONF_API_SECRET,
            default=suggested.get(CONF_API_SECRET, ""),
        ): str,
        vol.Required(
            CONF_ENVIRONMENT,
            default=suggested.get(CONF_ENVIRONMENT, DEFAULT_ENVIRONMENT),
        ): vol.In(list(ENVIRONMENT_URLS)),
        vol.Required(
            CONF_UPDATE_INTERVAL,
            default=suggested.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        ): vol.All(vol.Coerce(int), vol.Range(min=MIN_UPDATE_INTERVAL)),
    }

    if require_account_label:
        schema[
            vol.Required(
                CONF_ACCOUNT_LABEL,
                default=suggested.get(CONF_ACCOUNT_LABEL, ""),
            )
        ] = str

    return vol.Schema(schema)


def _options_schema(options: Mapping[str, Any] | None = None) -> vol.Schema:
    """Return the options flow schema."""
    suggested = get_entry_options(options)
    return vol.Schema(
        {
            vol.Required(
                FEATURE_ACCOUNT_SUMMARY,
                default=suggested[FEATURE_ACCOUNT_SUMMARY],
            ): bool,
            vol.Required(
                FEATURE_POSITIONS_SUMMARY,
                default=suggested[FEATURE_POSITIONS_SUMMARY],
            ): bool,
            vol.Required(
                FEATURE_PER_POSITION_ENTITIES,
                default=suggested[FEATURE_PER_POSITION_ENTITIES],
            ): bool,
            vol.Required(
                CONF_MAX_POSITION_ENTITIES,
                default=suggested[CONF_MAX_POSITION_ENTITIES],
            ): vol.All(
                vol.Coerce(int),
                vol.Range(min=MIN_POSITION_ENTITIES, max=MAX_POSITION_ENTITIES),
            ),
            vol.Required(
                CONF_POSITION_DISPLAY_FORMAT,
                default=suggested[CONF_POSITION_DISPLAY_FORMAT],
            ): vol.In(POSITION_DISPLAY_FORMATS),
            vol.Required(
                FEATURE_PIES_SUMMARY,
                default=suggested[FEATURE_PIES_SUMMARY],
            ): bool,
            vol.Required(
                FEATURE_PER_PIE_ENTITIES,
                default=suggested[FEATURE_PER_PIE_ENTITIES],
            ): bool,
            vol.Required(
                FEATURE_DIVIDENDS_SUMMARY,
                default=suggested[FEATURE_DIVIDENDS_SUMMARY],
            ): bool,
            vol.Required(
                FEATURE_ORDERS_SUMMARY,
                default=suggested[FEATURE_ORDERS_SUMMARY],
            ): bool,
            vol.Required(
                FEATURE_MOVERS_DAILY,
                default=suggested[FEATURE_MOVERS_DAILY],
            ): bool,
        }
    )




def _normalise_account_label(value: Any) -> str | None:
    """Return a cleaned optional account label."""
    if not isinstance(value, str):
        return None

    label = value.strip()
    if not label or label.casefold() == DEFAULT_ACCOUNT_LABEL.casefold():
        return None

    return label


def _account_identifier_from_summary(
    summary: dict[str, Any],
    *,
    api_key: str,
    api_secret: str,
    environment: str,
) -> str:
    """Return a stable duplicate-detection key for the account."""
    for key in ("accountId", "account_id", "id", "accountCode", "account_code"):
        value = summary.get(key)
        if isinstance(value, (str, int)) and str(value).strip():
            return str(value).strip()

    return _credentials_fingerprint(
        api_key=api_key,
        api_secret=api_secret,
        environment=environment,
    )


def _credentials_fingerprint(
    *,
    api_key: str,
    api_secret: str,
    environment: str,
) -> str:
    """Return a non-reversible fallback identifier when the API exposes no account ID."""
    digest = hashlib.sha256(
        f"{environment}\0{api_key}\0{api_secret}".encode("utf-8")
    ).hexdigest()
    return f"credentials_{digest[:16]}"
