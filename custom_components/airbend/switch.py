"""Enable switch so automatic control can be paused."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .coordinator import AirbendCoordinator
from .entity import AirbendEntity

_AUTOMATIC = SwitchEntityDescription(
    key="automatic",
    translation_key="automatic",
    icon="mdi:fan-auto",
)


_CIRCULATION = SwitchEntityDescription(
    key="circulation",
    translation_key="circulation",
    icon="mdi:air-purifier",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AirbendCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            AirbendAutomaticSwitch(coordinator),
            AirbendCirculationSwitch(coordinator),
        ]
    )


class AirbendAutomaticSwitch(AirbendEntity, SwitchEntity, RestoreEntity):
    """Turn automatic fan control on or off without deleting the integration."""

    entity_description = _AUTOMATIC
    _attr_assumed_state = False

    def __init__(self, coordinator: AirbendCoordinator) -> None:
        super().__init__(coordinator, "automatic")
        self._attr_is_on = True

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            self._attr_is_on = last.state == "on"
            self.coordinator.enabled = self._attr_is_on
        self.coordinator.control_ready = True
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: object) -> None:
        self._attr_is_on = True
        self.coordinator.set_enabled(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: object) -> None:
        self._attr_is_on = False
        self.coordinator.set_enabled(False)
        self.async_write_ha_state()


class AirbendCirculationSwitch(AirbendEntity, SwitchEntity, RestoreEntity):
    """Pause bedroom CO2 circulation without pausing the attic fan."""

    entity_description = _CIRCULATION

    def __init__(self, coordinator: AirbendCoordinator) -> None:
        super().__init__(coordinator, "circulation")
        self._attr_is_on = True

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            self._attr_is_on = last.state == "on"
            self.coordinator.circulation_enabled = self._attr_is_on
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: object) -> None:
        self._attr_is_on = True
        self.coordinator.set_circulation_enabled(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: object) -> None:
        self._attr_is_on = False
        self.coordinator.set_circulation_enabled(False)
        self.async_write_ha_state()
