"""Trading 212 Home Assistant integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import Trading212Client
from .const import (
    CONF_API_KEY,
    CONF_API_SECRET,
    CONF_ENVIRONMENT,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import Trading212DataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Set up Trading 212 from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    client = Trading212Client(
        session=async_get_clientsession(hass),
        api_key=str(entry.data[CONF_API_KEY]),
        api_secret=str(entry.data[CONF_API_SECRET]),
        environment=str(entry.data[CONF_ENVIRONMENT]),
    )

    coordinator = Trading212DataUpdateCoordinator(
        hass=hass,
        client=client,
        entry_id=entry.entry_id,
        update_interval_seconds=int(
            entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        ),
        feature_options=dict(entry.options),
    )

    await coordinator.async_initialize()
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Unload a Trading 212 config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok


async def _async_update_listener(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
