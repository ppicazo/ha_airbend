"""Whether the controller is currently ventilating."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AirbendCoordinator
from .decision import FanSpeed
from .entity import AirbendEntity

_VENTILATING = BinarySensorEntityDescription(
    key="ventilating",
    translation_key="ventilating",
    icon="mdi:fan",
)


_CIRCULATING = BinarySensorEntityDescription(
    key="circulating",
    translation_key="circulating",
    icon="mdi:air-purifier",
)

_HAZARD = BinarySensorEntityDescription(
    key="hazard",
    translation_key="hazard",
    device_class=BinarySensorDeviceClass.SAFETY,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AirbendCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            AirbendVentilatingSensor(coordinator),
            AirbendCirculatingSensor(coordinator),
            AirbendHazardSensor(coordinator),
        ]
    )


class AirbendVentilatingSensor(AirbendEntity, BinarySensorEntity):
    """On when Airbend is commanding the fan to run."""

    entity_description = _VENTILATING

    def __init__(self, coordinator: AirbendCoordinator) -> None:
        super().__init__(coordinator, "ventilating")

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        if data is None:
            return None
        return data.enabled and data.decision.speed is not FanSpeed.OFF


class AirbendCirculatingSensor(AirbendEntity, BinarySensorEntity):
    """On when bedroom CO2 is asking the house blower to circulate."""

    entity_description = _CIRCULATING

    def __init__(self, coordinator: AirbendCoordinator) -> None:
        super().__init__(coordinator, "circulating")

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        if data is None:
            return None
        return data.circulation_on


class AirbendHazardSensor(AirbendEntity, BinarySensorEntity):
    """On when smoke, carbon monoxide, or gas has stopped air movement."""

    entity_description = _HAZARD

    def __init__(self, coordinator: AirbendCoordinator) -> None:
        super().__init__(coordinator, "hazard")

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        if data is None:
            return None
        return data.hazard_active
