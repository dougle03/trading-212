"""Diagnostics support for Trading 212."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_TOKEN
from homeassistant.core import HomeAssistant

from .const import CONF_API_KEY, CONF_API_SECRET, DOMAIN

TO_REDACT = {
    CONF_API_KEY,
    CONF_API_SECRET,
    CONF_API_TOKEN,
    "api_key",
    "api_secret",
    "api_token",
    "token",
    "authorization",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry with secrets redacted."""
    stored = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinator = stored.get("coordinator")

    coordinator_data: dict[str, Any] = {}
    if coordinator is not None and getattr(coordinator, "data", None):
        coordinator_data = {
            "has_summary": bool(coordinator.data.get("summary")),
            "open_positions": coordinator.data.get("open_positions"),
            "pies_count": coordinator.data.get("pies_count"),
            "last_update": coordinator.data.get("last_update"),
            "currency": coordinator.data.get("currency"),
            "feature_options": getattr(coordinator, "feature_options", {}),
            "endpoint_groups": getattr(coordinator, "endpoint_group_status", {}),
        }

    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "coordinator": async_redact_data(coordinator_data, TO_REDACT),
    }
