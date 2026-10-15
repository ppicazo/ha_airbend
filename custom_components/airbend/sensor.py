"""Temperature, season, and status sensors."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AirbendCoordinator, AirbendData, Reading
from .decision import Season
from .entity import AirbendEntity

_SEASON = SensorEntityDescription(
    key="season",
    translation_key="season",
    device_class=SensorDeviceClass.ENUM,
    options=[Season.SUMMER.value, Season.WINTER.value, Season.UNKNOWN.value],
    icon="mdi:sun-snowflake",
)
_TARGET = SensorEntityDescription(
    key="target_speed",
    translation_key="target_speed",
    device_class=SensorDeviceClass.ENUM,
    options=["off", "low", "medium", "high", "paused"],
    icon="mdi:fan",
)
_STATUS = SensorEntityDescription(
    key="status",
    translation_key="status",
    icon="mdi:information-outline",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AirbendCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            AirbendTemperatureSensor(coordinator, "outdoor", "outdoor_temperature"),
            AirbendTemperatureSensor(coordinator, "attic", "attic_temperature"),
            AirbendTemperatureSensor(coordinator, "indoor", "indoor_temperature"),
            AirbendSeasonSensor(coordinator),
            AirbendTargetSensor(coordinator),
            AirbendStatusSensor(coordinator),
        ]
    )


class AirbendTemperatureSensor(AirbendEntity, SensorEntity):
    """Averaged temperature."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: AirbendCoordinator, group: str, key: str) -> None:
        super().__init__(coordinator, key)
        self._group = group
        self._attr_translation_key = key
        self._attr_icon = "mdi:thermometer"

    @property
    def native_value(self) -> float | None:
        reading = self._reading
        if reading is None or reading.value_c is None:
            return None
        return round(reading.value_c, 2)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        reading = self._reading
        if reading is None:
            return {}
        return {
            "sources": reading.sources,
            "source_count": len(reading.sources),
        }

    @property
    def _reading(self) -> Reading | None:
        data = self.coordinator.data
        if data is None:
            return None
        return getattr(data, self._group)


class AirbendSeasonSensor(AirbendEntity, SensorEntity):
    """Summer when the house is warm, winter when it is not."""

    entity_description = _SEASON

    def __init__(self, coordinator: AirbendCoordinator) -> None:
        super().__init__(coordinator, "season")

    @property
    def native_value(self) -> str | None:
        return _decision_value(self.coordinator.data, lambda data: data.decision.season.value)


class AirbendTargetSensor(AirbendEntity, SensorEntity):
    """Speed Airbend wants, or paused when automatic control is off."""

    entity_description = _TARGET

    def __init__(self, coordinator: AirbendCoordinator) -> None:
        super().__init__(coordinator, "target_speed")

    @property
    def native_value(self) -> str | None:
        data = self.coordinator.data
        if data is None:
            return None
        if not data.enabled:
            return "paused"
        return data.decision.speed.value

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        data = self.coordinator.data
        if data is None:
            return {}
        return {
            "recommendation": data.decision.unconstrained_speed.value,
            "fan_available": data.fan_available,
        }


class AirbendStatusSensor(AirbendEntity, SensorEntity):
    """Plain-language reason for the current decision."""

    entity_description = _STATUS

    def __init__(self, coordinator: AirbendCoordinator) -> None:
        super().__init__(coordinator, "status")

    @property
    def native_value(self) -> str | None:
        data = self.coordinator.data
        if data is None:
            return None
        if not data.enabled:
            return f"Paused. {data.decision.reason}"
        if not data.fan_available:
            return f"Fan unavailable. {data.decision.reason}"
        return data.decision.reason

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        data = self.coordinator.data
        if data is None or data.attic.value_c is None or data.outdoor.value_c is None:
            return {}
        return {
            "attic_minus_outdoor": round(data.attic.value_c - data.outdoor.value_c, 2),
        }


def _decision_value(data: AirbendData | None, reader) -> str | None:
    if data is None:
        return None
    return reader(data)
