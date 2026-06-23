"""Constants for the Trading 212 integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "trading212"

PLATFORMS: list[Platform] = [Platform.SENSOR]

CONF_ACCOUNT_LABEL = "account_label"
CONF_ENVIRONMENT = "environment"
CONF_UPDATE_INTERVAL = "update_interval"

DEFAULT_ACCOUNT_LABEL = "Trading 212"
DEFAULT_ENVIRONMENT = "live"
DEFAULT_UPDATE_INTERVAL = 300

MIN_UPDATE_INTERVAL = 60

ENVIRONMENT_URLS = {
    "live": "https://live.trading212.com/api/v0",
    "demo": "https://demo.trading212.com/api/v0",
}
