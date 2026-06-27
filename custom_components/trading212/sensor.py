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

from .const import (
    CONF_ACCOUNT_LABEL,
    DEFAULT_ACCOUNT_LABEL,
    DOMAIN,
    FEATURE_MOVERS_DAILY,
    FEATURE_PIES_SUMMARY,
    FEATURE_POSITIONS_SUMMARY,
)
from .coordinator import Trading212DataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class Trading212SensorEntityDescription(SensorEntityDescription):
    """Trading 212 sensor description."""

    value_key: str
    attributes_key: str | None = None
    feature_option: str | None = None


SENSOR_DESCRIPTIONS: tuple[Trading212SensorEntityDescription, ...] = (
    Trading212SensorEntityDescription(
        key="account_value",
        translation_key="account_value",
        value_key="account_value",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
    ),
    Trading212SensorEntityDescription(
        key="cash",
        translation_key="cash",
        value_key="cash",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
    ),
    Trading212SensorEntityDescription(
        key="free_funds",
        translation_key="free_funds",
        value_key="free_funds",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
    ),
    Trading212SensorEntityDescription(
        key="invested",
        translation_key="invested",
        value_key="invested",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
    ),
    Trading212SensorEntityDescription(
        key="result",
        translation_key="result",
        value_key="result",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
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
        feature_option=FEATURE_POSITIONS_SUMMARY,
    ),
    Trading212SensorEntityDescription(
        key="daily_gain_loss",
        translation_key="daily_gain_loss",
        value_key="daily_gain_loss",
        attributes_key="daily_gain_loss_attrs",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        feature_option=FEATURE_MOVERS_DAILY,
    ),
    Trading212SensorEntityDescription(
        key="daily_gain_loss_percent",
        translation_key="daily_gain_loss_percent",
        value_key="daily_gain_loss_percent",
        attributes_key="daily_gain_loss_percent_attrs",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        feature_option=FEATURE_MOVERS_DAILY,
    ),
    Trading212SensorEntityDescription(
        key="top_daily_mover",
        translation_key="top_daily_mover",
        value_key="top_daily_mover",
        attributes_key="top_daily_mover_attrs",
        feature_option=FEATURE_MOVERS_DAILY,
    ),
    Trading212SensorEntityDescription(
        key="bottom_daily_mover",
        translation_key="bottom_daily_mover",
        value_key="bottom_daily_mover",
        attributes_key="bottom_daily_mover_attrs",
        feature_option=FEATURE_MOVERS_DAILY,
    ),
    Trading212SensorEntityDescription(
        key="biggest_daily_gain_value",
        translation_key="biggest_daily_gain_value",
        value_key="biggest_daily_gain_value",
        attributes_key="biggest_daily_gain_value_attrs",
        feature_option=FEATURE_MOVERS_DAILY,
    ),
    Trading212SensorEntityDescription(
        key="biggest_daily_loss_value",
        translation_key="biggest_daily_loss_value",
        value_key="biggest_daily_loss_value",
        attributes_key="biggest_daily_loss_value_attrs",
        feature_option=FEATURE_MOVERS_DAILY,
    ),
    Trading212SensorEntityDescription(
        key="largest_position",
        translation_key="largest_position",
        value_key="largest_position",
        attributes_key="largest_position_attrs",
        feature_option=FEATURE_POSITIONS_SUMMARY,
    ),
    Trading212SensorEntityDescription(
        key="largest_position_value",
        translation_key="largest_position_value",
        value_key="largest_position_value",
        attributes_key="largest_position_value_attrs",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        feature_option=FEATURE_POSITIONS_SUMMARY,
    ),
    Trading212SensorEntityDescription(
        key="largest_position_percentage",
        translation_key="largest_position_percentage",
        value_key="largest_position_percentage",
        attributes_key="largest_position_percentage_attrs",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        feature_option=FEATURE_POSITIONS_SUMMARY,
    ),
    Trading212SensorEntityDescription(
        key="top_5_position_concentration_percentage",
        translation_key="top_5_position_concentration_percentage",
        value_key="top_5_position_concentration_percentage",
        attributes_key="top_5_position_concentration_percentage_attrs",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        feature_option=FEATURE_POSITIONS_SUMMARY,
    ),
    Trading212SensorEntityDescription(
        key="positions_in_profit",
        translation_key="positions_in_profit",
        value_key="positions_in_profit",
        attributes_key="positions_in_profit_attrs",
        state_class=SensorStateClass.MEASUREMENT,
        feature_option=FEATURE_POSITIONS_SUMMARY,
    ),
    Trading212SensorEntityDescription(
        key="positions_in_loss",
        translation_key="positions_in_loss",
        value_key="positions_in_loss",
        attributes_key="positions_in_loss_attrs",
        state_class=SensorStateClass.MEASUREMENT,
        feature_option=FEATURE_POSITIONS_SUMMARY,
    ),
    Trading212SensorEntityDescription(
        key="total_unrealised_result",
        translation_key="total_unrealised_result",
        value_key="total_unrealised_result",
        attributes_key="total_unrealised_result_attrs",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        feature_option=FEATURE_POSITIONS_SUMMARY,
    ),
    Trading212SensorEntityDescription(
        key="best_position",
        translation_key="best_position",
        value_key="best_position",
        attributes_key="best_position_attrs",
        feature_option=FEATURE_POSITIONS_SUMMARY,
    ),
    Trading212SensorEntityDescription(
        key="best_position_result",
        translation_key="best_position_result",
        value_key="best_position_result",
        attributes_key="best_position_result_attrs",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        feature_option=FEATURE_POSITIONS_SUMMARY,
    ),
    Trading212SensorEntityDescription(
        key="worst_position",
        translation_key="worst_position",
        value_key="worst_position",
        attributes_key="worst_position_attrs",
        feature_option=FEATURE_POSITIONS_SUMMARY,
    ),
    Trading212SensorEntityDescription(
        key="worst_position_result",
        translation_key="worst_position_result",
        value_key="worst_position_result",
        attributes_key="worst_position_result_attrs",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        feature_option=FEATURE_POSITIONS_SUMMARY,
    ),
    Trading212SensorEntityDescription(
        key="pies_count",
        translation_key="pies_count",
        value_key="pies_count",
        attributes_key="pies_count_attrs",
        state_class=SensorStateClass.MEASUREMENT,
        feature_option=FEATURE_PIES_SUMMARY,
    ),
    Trading212SensorEntityDescription(
        key="total_pies_value",
        translation_key="total_pies_value",
        value_key="total_pies_value",
        attributes_key="total_pies_value_attrs",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        feature_option=FEATURE_PIES_SUMMARY,
    ),
    Trading212SensorEntityDescription(
        key="total_pies_cash",
        translation_key="total_pies_cash",
        value_key="total_pies_cash",
        attributes_key="total_pies_cash_attrs",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        feature_option=FEATURE_PIES_SUMMARY,
    ),
    Trading212SensorEntityDescription(
        key="total_pies_result",
        translation_key="total_pies_result",
        value_key="total_pies_result",
        attributes_key="total_pies_result_attrs",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        feature_option=FEATURE_PIES_SUMMARY,
    ),
    Trading212SensorEntityDescription(
        key="largest_pie",
        translation_key="largest_pie",
        value_key="largest_pie",
        attributes_key="largest_pie_attrs",
        feature_option=FEATURE_PIES_SUMMARY,
    ),
    Trading212SensorEntityDescription(
        key="largest_pie_value",
        translation_key="largest_pie_value",
        value_key="largest_pie_value",
        attributes_key="largest_pie_value_attrs",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        feature_option=FEATURE_PIES_SUMMARY,
    ),
    Trading212SensorEntityDescription(
        key="last_pie_update_time",
        translation_key="last_pie_update_time",
        value_key="last_pie_update_time",
        attributes_key="last_pie_update_time_attrs",
        device_class=SensorDeviceClass.TIMESTAMP,
        feature_option=FEATURE_PIES_SUMMARY,
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
        account_label = DEFAULT_ACCOUNT_LABEL

    async_add_entities(
        Trading212Sensor(coordinator, entry, account_label, description)
        for description in SENSOR_DESCRIPTIONS
        if _sensor_enabled(coordinator, description)
    )


def _sensor_enabled(
    coordinator: Trading212DataUpdateCoordinator,
    description: Trading212SensorEntityDescription,
) -> bool:
    """Return whether a sensor should be added for the current feature options."""
    if description.feature_option is None:
        return True
    return bool(coordinator.feature_options.get(description.feature_option))


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

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return sensor attributes."""
        attributes_key = self.entity_description.attributes_key
        if attributes_key is None:
            return None
        attributes = self.coordinator.data.get(attributes_key)
        if isinstance(attributes, dict):
            return attributes
        return None
