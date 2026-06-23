"""Sensors for the Trading 212 integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ACCOUNT_LABEL, DOMAIN
from .coordinator import Trading212DataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class Trading212SensorEntityDescription(SensorEntityDescription):
    """Trading 212 sensor description."""

    value_key: str


SENSOR_DESCRIPTIONS: tuple[Trading212SensorEntityDescription, ...] = (
    Trading212SensorEntityDescription(
        key="account_value",
        translation_key="account_value",
        value_key="account_value",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    Trading212SensorEntityDescription(
        key="cash",
        translation_key="cash",
        value_key="cash",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    Trading212SensorEntityDescription(
        key="free_funds",
        translation_key="free_funds",
        value_key="free_funds",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    Trading212SensorEntityDescription(
        key="invested",
        translation_key="invested",
        value_key="invested",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    Trading212SensorEntityDescription(
        key="result",
        translation_key="result",
        value_key="result",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    Trading212SensorEntityDescription(
        key="result_percent",
        translation_key="result_percent",
        value_key="result_percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    Trading212SensorEntityDescription(
        key="open_positions",
        translation_key="open_positions",
        value_key="open_positions",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    Trading212SensorEntityDescription(
        key="last_update",
        translation_key="last_update",
        value_key="last_update",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Trading 212 sensors."""
    coordinator: Trading212DataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]

    account_label = entry.data.get(CONF_ACCOUNT_LABEL) or entry.data.get(CONF_NAME)
    if not isinstance(account_label, str) or not account_label.strip():
        account_label = "Trading 212"

    async_add_entities(
        Trading212Sensor(coordinator, entry, account_label, description)
        for description in SENSOR_DESCRIPTIONS
    )


class Trading212Sensor(CoordinatorEntity[Trading212DataUpdateCoordinator], SensorEntity):
    """Trading 212 account summary sensor."""

    entity_description: Trading212SensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: Trading212DataUpdateCoordinator,
        entry: ConfigEntry,
        account_label: str,
        description: Trading212SensorEntityDescription,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": account_label,
            "manufacturer": "Trading 212",
            "model": "Read-only API",
        }

    @property
    def native_value(self) -> Any:
        """Return the native sensor value."""
        return self.coordinator.data.get(self.entity_description.value_key)

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement."""
        if self.entity_description.native_unit_of_measurement is not None:
            return self.entity_description.native_unit_of_measurement

        if self.entity_description.device_class == SensorDeviceClass.MONETARY:
            currency = self.coordinator.data.get("currency")
            if isinstance(currency, str) and currency:
                return currency

        return None
