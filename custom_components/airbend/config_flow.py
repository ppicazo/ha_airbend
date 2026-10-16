"""Config and options flow for Airbend."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import UnitOfTemperature
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_ATTIC_SENSORS,
    CONF_CIRCULATE_MODE,
    CONF_CLIMATE,
    CONF_CO2_HYSTERESIS,
    CONF_CO2_SENSORS,
    CONF_CO2_THRESHOLD,
    CONF_FAN,
    CONF_FAN_MODE,
    CONF_FAN_TEMPERATURE,
    CONF_HYSTERESIS,
    CONF_ICE_DAM,
    CONF_ICE_DAM_ATTIC,
    CONF_ICE_DAM_OUTDOOR,
    CONF_IDLE_FAN_MODE,
    CONF_INDOOR_SENSORS,
    CONF_MANUAL_MODE,
    CONF_MIN_DELTA,
    CONF_MIN_OFF,
    CONF_MIN_ON,
    CONF_OUTDOOR_SENSORS,
    CONF_SAFETY_MAX,
    CONF_STALE_MINUTES,
    CONF_SUMMER_HIGH,
    CONF_SUMMER_INDOOR,
    CONF_SUMMER_LOW,
    CONF_SUMMER_MEDIUM,
    CONF_WINTER_CEILING,
    CONF_WINTER_HIGH,
    CONF_WEATHER,
    DEFAULT_CIRCULATE_MODE,
    DEFAULT_CO2_HYSTERESIS,
    DEFAULT_CO2_THRESHOLD,
    DEFAULT_ICE_DAM,
    DEFAULT_IDLE_FAN_MODE,
    DEFAULT_MANUAL_MODE,
    DEFAULT_MIN_OFF,
    DEFAULT_MIN_ON,
    DEFAULT_NAME,
    DEFAULT_STALE_MINUTES,
    DOMAIN,
)
from .units import (
    default_options_c,
    form_range,
    from_display,
    to_display,
    user_temperature_unit,
)

TEMP_SENSOR = selector.EntitySelector(
    selector.EntitySelectorConfig(
        domain="sensor",
        device_class="temperature",
        multiple=True,
    )
)
ONE_TEMP_SENSOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
)
FAN_SELECTOR = selector.EntitySelector(selector.EntitySelectorConfig(domain="fan"))
SELECT_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="select")
)
WEATHER_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="weather")
)
CO2_SENSOR = selector.EntitySelector(
    selector.EntitySelectorConfig(
        domain="sensor",
        device_class="carbon_dioxide",
        multiple=True,
    )
)
CLIMATE_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="climate")
)

_BEHAVIOR_KEYS = (
    CONF_SUMMER_INDOOR,
    CONF_HYSTERESIS,
    CONF_MIN_DELTA,
    CONF_SAFETY_MAX,
    CONF_SUMMER_LOW,
    CONF_SUMMER_MEDIUM,
    CONF_SUMMER_HIGH,
    CONF_WINTER_CEILING,
    CONF_WINTER_HIGH,
    CONF_ICE_DAM_OUTDOOR,
    CONF_ICE_DAM_ATTIC,
)

_ORDERED_GROUPS = (
    (CONF_SUMMER_LOW, CONF_SUMMER_MEDIUM, CONF_SUMMER_HIGH, CONF_SAFETY_MAX),
    (CONF_WINTER_CEILING, CONF_WINTER_HIGH, CONF_SAFETY_MAX),
)


def _entities_schema(suggested: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_OUTDOOR_SENSORS,
                description={"suggested_value": suggested.get(CONF_OUTDOOR_SENSORS, [])},
            ): TEMP_SENSOR,
            vol.Required(
                CONF_ATTIC_SENSORS,
                description={"suggested_value": suggested.get(CONF_ATTIC_SENSORS, [])},
            ): TEMP_SENSOR,
            vol.Required(
                CONF_INDOOR_SENSORS,
                description={"suggested_value": suggested.get(CONF_INDOOR_SENSORS, [])},
            ): TEMP_SENSOR,
            vol.Required(
                CONF_FAN, description={"suggested_value": suggested.get(CONF_FAN, "")}
            ): FAN_SELECTOR,
            vol.Optional(
                CONF_FAN_TEMPERATURE,
                description={"suggested_value": suggested.get(CONF_FAN_TEMPERATURE, "")},
            ): ONE_TEMP_SENSOR,
            vol.Optional(
                CONF_FAN_MODE,
                description={"suggested_value": suggested.get(CONF_FAN_MODE, "")},
            ): SELECT_SELECTOR,
            vol.Optional(
                CONF_WEATHER,
                description={"suggested_value": suggested.get(CONF_WEATHER, "")},
            ): WEATHER_SELECTOR,
            vol.Optional(
                CONF_CO2_SENSORS,
                description={"suggested_value": suggested.get(CONF_CO2_SENSORS, [])},
            ): CO2_SENSOR,
            vol.Optional(
                CONF_CLIMATE,
                description={"suggested_value": suggested.get(CONF_CLIMATE, "")},
            ): CLIMATE_SELECTOR,
            vol.Optional(
                CONF_CIRCULATE_MODE,
                description={
                    "suggested_value": suggested.get(CONF_CIRCULATE_MODE, DEFAULT_CIRCULATE_MODE)
                },
            ): selector.TextSelector(),
            vol.Optional(
                CONF_IDLE_FAN_MODE,
                description={
                    "suggested_value": suggested.get(
                        CONF_IDLE_FAN_MODE, DEFAULT_IDLE_FAN_MODE
                    )
                },
            ): selector.TextSelector(),
            vol.Optional(
                CONF_MANUAL_MODE,
                description={
                    "suggested_value": suggested.get(CONF_MANUAL_MODE, DEFAULT_MANUAL_MODE)
                },
            ): selector.TextSelector(),
        }
    )


def _behavior_schema(suggested: dict[str, Any], unit: str) -> vol.Schema:
    fields: dict[Any, Any] = {}
    for key in _BEHAVIOR_KEYS:
        minimum, maximum, step = form_range(key, unit)
        fields[
            vol.Required(key, description={"suggested_value": suggested[key]})
        ] = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=minimum,
                max=maximum,
                step=step,
                mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement=unit,
            )
        )
    fields[
        vol.Required(
            CONF_ICE_DAM,
            description={"suggested_value": suggested.get(CONF_ICE_DAM, DEFAULT_ICE_DAM)},
        )
    ] = selector.BooleanSelector()
    fields[
        vol.Required(
            CONF_MIN_ON,
            description={"suggested_value": suggested.get(CONF_MIN_ON, DEFAULT_MIN_ON)},
        )
    ] = selector.NumberSelector(
        selector.NumberSelectorConfig(min=0, max=60, step=1, unit_of_measurement="min")
    )
    fields[
        vol.Required(
            CONF_MIN_OFF,
            description={"suggested_value": suggested.get(CONF_MIN_OFF, DEFAULT_MIN_OFF)},
        )
    ] = selector.NumberSelector(
        selector.NumberSelectorConfig(min=0, max=60, step=1, unit_of_measurement="min")
    )
    fields[
        vol.Required(
            CONF_STALE_MINUTES,
            description={
                "suggested_value": suggested.get(CONF_STALE_MINUTES, DEFAULT_STALE_MINUTES)
            },
        )
    ] = selector.NumberSelector(
        selector.NumberSelectorConfig(min=5, max=180, step=1, unit_of_measurement="min")
    )
    fields[
        vol.Required(
            CONF_CO2_THRESHOLD,
            description={
                "suggested_value": suggested.get(CONF_CO2_THRESHOLD, DEFAULT_CO2_THRESHOLD)
            },
        )
    ] = selector.NumberSelector(
        selector.NumberSelectorConfig(min=400, max=2000, step=10, unit_of_measurement="ppm")
    )
    fields[
        vol.Required(
            CONF_CO2_HYSTERESIS,
            description={
                "suggested_value": suggested.get(CONF_CO2_HYSTERESIS, DEFAULT_CO2_HYSTERESIS)
            },
        )
    ] = selector.NumberSelector(
        selector.NumberSelectorConfig(min=10, max=300, step=10, unit_of_measurement="ppm")
    )
    return vol.Schema(fields)


def _clean_entities(user_input: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(user_input)
    for key in (
        CONF_FAN_TEMPERATURE,
        CONF_FAN_MODE,
        CONF_MANUAL_MODE,
        CONF_WEATHER,
        CONF_CLIMATE,
        CONF_CO2_SENSORS,
        CONF_CIRCULATE_MODE,
        CONF_IDLE_FAN_MODE,
    ):
        if not cleaned.get(key):
            cleaned.pop(key, None)
    return cleaned


def _display_behavior(stored: dict[str, Any], unit: str) -> dict[str, Any]:
    defaults = default_options_c()
    shown: dict[str, Any] = {}
    for key in _BEHAVIOR_KEYS:
        shown[key] = to_display(key, float(stored.get(key, defaults[key])), unit)
    shown[CONF_ICE_DAM] = stored.get(CONF_ICE_DAM, DEFAULT_ICE_DAM)
    shown[CONF_MIN_ON] = stored.get(CONF_MIN_ON, DEFAULT_MIN_ON)
    shown[CONF_MIN_OFF] = stored.get(CONF_MIN_OFF, DEFAULT_MIN_OFF)
    shown[CONF_STALE_MINUTES] = stored.get(CONF_STALE_MINUTES, DEFAULT_STALE_MINUTES)
    shown[CONF_CO2_THRESHOLD] = stored.get(CONF_CO2_THRESHOLD, DEFAULT_CO2_THRESHOLD)
    shown[CONF_CO2_HYSTERESIS] = stored.get(CONF_CO2_HYSTERESIS, DEFAULT_CO2_HYSTERESIS)
    return shown


def _store_behavior(user_input: dict[str, Any], unit: str) -> dict[str, Any]:
    stored: dict[str, Any] = {}
    for key in _BEHAVIOR_KEYS:
        stored[key] = from_display(key, float(user_input[key]), unit)
    stored[CONF_ICE_DAM] = bool(user_input[CONF_ICE_DAM])
    stored[CONF_MIN_ON] = int(user_input[CONF_MIN_ON])
    stored[CONF_MIN_OFF] = int(user_input[CONF_MIN_OFF])
    stored[CONF_STALE_MINUTES] = int(user_input[CONF_STALE_MINUTES])
    stored[CONF_CO2_THRESHOLD] = int(user_input[CONF_CO2_THRESHOLD])
    stored[CONF_CO2_HYSTERESIS] = int(user_input[CONF_CO2_HYSTERESIS])
    return stored


def _behavior_errors(stored: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    for group in _ORDERED_GROUPS:
        values = [stored[key] for key in group]
        if values != sorted(values) or len(set(values)) != len(values):
            errors["base"] = "threshold_order"
            return errors
    if stored[CONF_HYSTERESIS] <= 0 or stored[CONF_MIN_DELTA] <= 0:
        errors["base"] = "threshold_order"
        return errors
    if stored[CONF_ICE_DAM] and stored[CONF_ICE_DAM_ATTIC] >= stored[CONF_WINTER_CEILING]:
        errors["base"] = "ice_dam_order"
        return errors
    if stored[CONF_CO2_HYSTERESIS] >= stored[CONF_CO2_THRESHOLD]:
        errors["base"] = "co2_hysteresis"
    return errors


class AirbendConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up an Airbend controller."""

    def __init__(self) -> None:
        self._entities: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> AirbendOptionsFlow:
        return AirbendOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._entities = _clean_entities(user_input)
            return await self.async_step_behavior()

        return self.async_show_form(
            step_id="user",
            data_schema=_entities_schema({}),
            errors=errors,
        )

    async def async_step_behavior(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        unit = user_temperature_unit(self.hass)
        errors: dict[str, str] = {}
        if user_input is not None:
            stored = _store_behavior(user_input, unit)
            errors = _behavior_errors(stored)
            if not errors:
                return self.async_create_entry(
                    title=DEFAULT_NAME,
                    data={"name": DEFAULT_NAME},
                    options={**self._entities, **stored},
                )

        suggested = _display_behavior(default_options_c(), unit)
        if user_input is not None:
            suggested.update(user_input)
        return self.async_show_form(
            step_id="behavior",
            data_schema=_behavior_schema(suggested, unit),
            errors=errors,
            description_placeholders={"unit": _unit_name(unit)},
        )


class AirbendOptionsFlow(OptionsFlow):
    """Edit sensors and thresholds."""

    def __init__(self) -> None:
        self._entities: dict[str, Any] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        if user_input is not None:
            self._entities = _clean_entities(user_input)
            return await self.async_step_behavior()

        current = dict(self.config_entry.options)
        return self.async_show_form(
            step_id="init",
            data_schema=_entities_schema(current),
        )

    async def async_step_behavior(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        unit = user_temperature_unit(self.hass)
        errors: dict[str, str] = {}
        if user_input is not None:
            stored = _store_behavior(user_input, unit)
            errors = _behavior_errors(stored)
            if not errors:
                return self.async_create_entry(
                    title="",
                    data={**self._entities, **stored},
                )

        suggested = _display_behavior(dict(self.config_entry.options), unit)
        if user_input is not None:
            suggested.update(user_input)
        return self.async_show_form(
            step_id="behavior",
            data_schema=_behavior_schema(suggested, unit),
            errors=errors,
            description_placeholders={"unit": _unit_name(unit)},
        )


def _unit_name(unit: str) -> str:
    if unit == UnitOfTemperature.FAHRENHEIT:
        return "°F"
    return "°C"
