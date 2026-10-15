"""Shared entity base for Airbend."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AirbendCoordinator

MANUFACTURER = "Airbend"
MODEL = "Attic ventilation"


class AirbendEntity(CoordinatorEntity[AirbendCoordinator]):
    """Base entity attached to the controller device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AirbendCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name=coordinator.entry.title or "Airbend",
            manufacturer=MANUFACTURER,
            model=MODEL,
        )
