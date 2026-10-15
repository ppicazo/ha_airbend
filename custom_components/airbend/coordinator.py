"""Evaluate temperatures and command the attic fan."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfTemperature
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ATTIC_SENSORS,
    CONF_FAN,
    CONF_FAN_MODE,
    CONF_FAN_TEMPERATURE,
    CONF_HYSTERESIS,
    CONF_ICE_DAM,
    CONF_ICE_DAM_ATTIC,
    CONF_ICE_DAM_OUTDOOR,
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
    DEFAULT_ICE_DAM,
    DEFAULT_MANUAL_MODE,
    DEFAULT_MIN_OFF,
    DEFAULT_MIN_ON,
    DEFAULT_STALE_MINUTES,
    DOMAIN,
)
from .decision import (
    ControlSettings,
    Decision,
    FanCommand,
    FanSpeed,
    ForecastPoint,
    Season,
    Snapshot,
    command_for,
    decide,
)
from .units import default_options_c, state_to_celsius

_LOGGER = logging.getLogger(__name__)

_COMMAND_WAIT = timedelta(seconds=20)


class Reading:
    """An averaged temperature and the sensors that produced it."""

    def __init__(self, value_c: float | None, sources: list[str]) -> None:
        self.value_c = value_c
        self.sources = sources


class AirbendData:
    """Latest evaluation, including the temperatures that produced it."""

    def __init__(
        self,
        outdoor: Reading,
        attic: Reading,
        indoor: Reading,
        decision: Decision,
        enabled: bool,
        fan_available: bool,
        forecast: tuple[ForecastPoint, ...] = (),
    ) -> None:
        self.outdoor = outdoor
        self.attic = attic
        self.indoor = indoor
        self.decision = decision
        self.enabled = enabled
        self.fan_available = fan_available
        self.forecast = forecast


class AirbendCoordinator(DataUpdateCoordinator[AirbendData]):
    """Average the configured sensors and drive the fan."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=60),
        )
        self.entry = entry
        self.enabled = True
        # Fan commands wait until the enable switch has restored its state.
        self.control_ready = False
        self._season: Season | None = None
        self._applied_speed = FanSpeed.OFF
        self._applied_at: datetime | None = None
        self._last_command: FanCommand | None = None
        self._last_command_at: datetime | None = None
        self._command_task: asyncio.Task[None] | None = None
        self._manual_mode_retry_at: datetime | None = None
        self.fan_error: str | None = None
        self._forecast: tuple[ForecastPoint, ...] = ()
        self._forecast_at: datetime | None = None

    async def _async_update_data(self) -> AirbendData:
        await self._async_refresh_forecast()
        try:
            return self._evaluate()
        except Exception as err:
            _LOGGER.exception("Airbend could not evaluate the attic")
            return AirbendData(
                outdoor=Reading(None, []),
                attic=Reading(None, []),
                indoor=Reading(None, []),
                decision=Decision(
                    season=Season.UNKNOWN,
                    speed=FanSpeed.OFF,
                    unconstrained_speed=FanSpeed.OFF,
                    reason=f"Airbend hit an error while reading sensors: {err}",
                    safety_bypass=False,
                ),
                enabled=self.enabled,
                fan_available=False,
                forecast=self._forecast,
            )

    def _evaluate(self) -> AirbendData:
        options = self.entry.options
        stale = timedelta(minutes=int(options.get(CONF_STALE_MINUTES, DEFAULT_STALE_MINUTES)))
        outdoor = self._average(self._entity_list(options, CONF_OUTDOOR_SENSORS), stale)
        attic_ids = self._entity_list(options, CONF_ATTIC_SENSORS)
        fan_temp = options.get(CONF_FAN_TEMPERATURE)
        if fan_temp and fan_temp not in attic_ids:
            attic_ids.append(fan_temp)
        attic = self._average(attic_ids, stale)
        indoor = self._average(self._entity_list(options, CONF_INDOOR_SENSORS), stale)
        settings = _settings_from_options(options)
        now = dt_util.utcnow()
        decision = decide(
            Snapshot(
                outdoor_c=outdoor.value_c,
                attic_c=attic.value_c,
                indoor_c=indoor.value_c,
                season=self._season,
                applied_speed=self._applied_speed,
                applied_at=self._applied_at,
                now=now,
                forecast=self._forecast,
            ),
            settings,
        )
        self._season = decision.season

        fan_id = options.get(CONF_FAN)
        fan_state = self.hass.states.get(fan_id) if fan_id else None
        fan_available = (
            fan_state is not None and fan_state.state not in {STATE_UNAVAILABLE, STATE_UNKNOWN}
        )

        if self.enabled and self.control_ready and fan_available:
            self._schedule_command(decision)
        elif self.enabled and self.control_ready and not fan_available:
            _LOGGER.warning("Fan %s is unavailable; Airbend left it alone", fan_id)

        return AirbendData(
            outdoor=outdoor,
            attic=attic,
            indoor=indoor,
            decision=decision,
            enabled=self.enabled,
            fan_available=fan_available,
            forecast=self._forecast,
        )

    @callback
    def _handle_state_change(self, _event: Event) -> None:
        self.hass.async_create_task(self.async_request_refresh())

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        self.hass.async_create_task(self.async_request_refresh())

    def _schedule_command(self, decision: Decision) -> None:
        if self._command_task is not None and not self._command_task.done():
            return
        self._command_task = self.hass.async_create_task(self._async_safe_command(decision))

    async def _async_safe_command(self, decision: Decision) -> None:
        self.fan_error = None
        try:
            await self._async_command_fan(decision, dt_util.utcnow())
        except Exception as err:
            _LOGGER.exception("Airbend could not command the fan")
            self.fan_error = str(err)
        if self.data is not None:
            self.async_set_updated_data(self.data)

    @staticmethod
    def _entity_list(options: dict[str, Any], key: str) -> list[str]:
        configured = options.get(key) or []
        if isinstance(configured, str):
            return [configured]
        return list(configured)

    def watched_entities(self) -> list[str]:
        options = self.entry.options
        entities: list[str] = []
        for key in (CONF_OUTDOOR_SENSORS, CONF_ATTIC_SENSORS, CONF_INDOOR_SENSORS):
            entities.extend(self._entity_list(options, key))
        for key in (CONF_FAN_TEMPERATURE, CONF_FAN, CONF_FAN_MODE, CONF_WEATHER):
            if options.get(key):
                entities.append(options[key])
        return entities

    async def _async_refresh_forecast(self) -> None:
        entity_id = self.entry.options.get(CONF_WEATHER)
        if not entity_id:
            self._forecast = ()
            self._forecast_at = None
            return
        now = dt_util.utcnow()
        if (
            self._forecast_at is not None
            and now - self._forecast_at < timedelta(minutes=30)
        ):
            return
        try:
            response = await self.hass.services.async_call(
                "weather",
                "get_forecasts",
                {"entity_id": entity_id, "type": "hourly"},
                blocking=True,
                return_response=True,
            )
        except Exception:
            _LOGGER.warning("Airbend could not read the forecast from %s", entity_id)
            return
        outdoor = self._average(
            self._entity_list(self.entry.options, CONF_OUTDOOR_SENSORS),
            timedelta(hours=6),
        )
        self._forecast = _parse_forecast(
            self.hass, entity_id, response or {}, outdoor.value_c, now
        )
        self._forecast_at = now

    def listen(self) -> None:
        self.entry.async_on_unload(
            async_track_state_change_event(
                self.hass, self.watched_entities(), self._handle_state_change
            )
        )

    def _average(self, entity_ids: list[str], stale_after: timedelta) -> Reading:
        values: list[float] = []
        sources: list[str] = []
        now = dt_util.utcnow()
        fallback = self.hass.config.units.temperature_unit
        for entity_id in entity_ids:
            state = self.hass.states.get(entity_id)
            if state is None or state.state in {STATE_UNAVAILABLE, STATE_UNKNOWN}:
                continue
            try:
                age = now - state.last_updated
            except TypeError:
                age = timedelta(0)
            if age > stale_after:
                continue
            try:
                raw = float(state.state)
            except (TypeError, ValueError):
                continue
            unit = state.attributes.get("unit_of_measurement")
            try:
                values.append(state_to_celsius(raw, unit, fallback))
            except ValueError:
                _LOGGER.debug("Skipping %s with unsupported unit %s", entity_id, unit)
                continue
            sources.append(entity_id)
        if not values:
            return Reading(None, [])
        return Reading(sum(values) / len(values), sources)

    async def _async_command_fan(self, decision: Decision, now: datetime) -> None:
        options = self.entry.options
        fan_id = options[CONF_FAN]
        await self._async_hold_manual_mode()

        state = self.hass.states.get(fan_id)
        presets = list(state.attributes.get("preset_modes") or []) if state else []
        command = command_for(decision.speed, presets)
        if self._command_matches_state(command, state) or self._command_is_in_flight(command, now):
            if self._command_matches_state(command, state):
                self._remember_applied(decision.speed, now, changed=False)
            return

        service_data: dict[str, Any] = {"entity_id": fan_id}
        if command.on and command.preset_mode:
            service_data["preset_mode"] = command.preset_mode
            service = "turn_on"
        elif command.on:
            service_data["percentage"] = command.percentage
            service = "turn_on"
        else:
            service = "turn_off"

        _LOGGER.info(
            "Airbend set %s to %s (%s)",
            fan_id,
            command.label,
            decision.reason,
        )
        await self.hass.services.async_call("fan", service, service_data, blocking=True)

        self._last_command = command
        self._last_command_at = now
        self._remember_applied(decision.speed, now, changed=True)

    async def _async_hold_manual_mode(self) -> None:
        """Keep QuietCool (or similar) out of its own thermostat mode.

        A failure here must not escape. The installed 0.1.0 build called this
        from the sensor update, so a rejected mode change marked every entity
        unavailable.
        """

        mode_entity = self.entry.options.get(CONF_FAN_MODE)
        if not mode_entity:
            return
        now = dt_util.utcnow()
        if self._manual_mode_retry_at is not None and now < self._manual_mode_retry_at:
            return
        target = str(self.entry.options.get(CONF_MANUAL_MODE) or DEFAULT_MANUAL_MODE)
        state = self.hass.states.get(mode_entity)
        if state is None or state.state in {STATE_UNAVAILABLE, STATE_UNKNOWN}:
            return
        if state.domain != "select":
            self.fan_error = f"{mode_entity} is not a mode select"
            self._manual_mode_retry_at = now + timedelta(minutes=5)
            return
        option = _matching_option(state.attributes.get("options"), target)
        if option is None:
            self.fan_error = f"{mode_entity} has no {target!r} option"
            self._manual_mode_retry_at = now + timedelta(minutes=5)
            return
        if state.state == option:
            return
        try:
            await self.hass.services.async_call(
                "select",
                "select_option",
                {"entity_id": mode_entity, "option": option},
                blocking=True,
            )
        except Exception as err:
            _LOGGER.warning(
                "Airbend could not set %s to %s: %s", mode_entity, option, err
            )
            self.fan_error = f"Could not set {mode_entity} to {option}: {err}"
            self._manual_mode_retry_at = now + timedelta(minutes=2)

    def _command_matches_state(self, command: FanCommand, state: Any) -> bool:
        if state is None:
            return False
        if not command.on:
            return state.state == "off"
        if state.state != "on":
            return False
        if command.preset_mode:
            return state.attributes.get("preset_mode") == command.preset_mode
        current = state.attributes.get("percentage")
        return current is not None and abs(int(current) - int(command.percentage or 0)) <= 2

    def _command_is_in_flight(self, command: FanCommand, now: datetime) -> bool:
        if self._last_command != command or self._last_command_at is None:
            return False
        return now - self._last_command_at < _COMMAND_WAIT

    def _remember_applied(self, speed: FanSpeed, now: datetime, changed: bool) -> None:
        if changed or self._applied_at is None or speed is not self._applied_speed:
            if speed is not self._applied_speed or self._applied_at is None:
                self._applied_at = now
            self._applied_speed = speed


def _parse_forecast(
    hass: HomeAssistant,
    entity_id: str,
    response: dict[str, Any],
    outdoor_c: float | None,
    now: datetime,
) -> tuple[ForecastPoint, ...]:
    payload = response.get(entity_id) or {}
    rows = payload.get("forecast") or []
    samples: list[tuple[float, float]] = []
    for row in rows:
        temperature = row.get("temperature")
        stamp = row.get("datetime")
        if temperature is None or stamp is None:
            continue
        moment = dt_util.parse_datetime(str(stamp))
        if moment is None:
            continue
        hours = (moment - now).total_seconds() / 3600
        if hours < -0.5 or hours > 24:
            continue
        samples.append((hours, float(temperature)))
    if not samples:
        return ()
    nearest = min(samples, key=lambda item: abs(item[0]))[1]
    unit = _forecast_unit(hass, entity_id, nearest, outdoor_c)
    return tuple(
        ForecastPoint(
            hours=hours,
            temp_c=state_to_celsius(temperature, unit, UnitOfTemperature.CELSIUS),
        )
        for hours, temperature in samples
    )


def _forecast_unit(
    hass: HomeAssistant,
    entity_id: str,
    sample: float,
    outdoor_c: float | None,
) -> str:
    state = hass.states.get(entity_id)
    explicit = None if state is None else state.attributes.get("temperature_unit")
    if explicit:
        return str(explicit)
    if outdoor_c is None:
        return UnitOfTemperature.CELSIUS
    as_celsius = abs(sample - outdoor_c)
    as_fahrenheit = abs(((sample - 32.0) * 5.0 / 9.0) - outdoor_c)
    if as_fahrenheit + 1.5 < as_celsius:
        return UnitOfTemperature.FAHRENHEIT
    return UnitOfTemperature.CELSIUS


def _matching_option(options: Any, target: str) -> str | None:
    if not isinstance(options, list):
        return None
    folded = target.casefold()
    for option in options:
        text = str(option)
        if text.casefold() == folded:
            return text
    return None


def _settings_from_options(options: dict[str, Any]) -> ControlSettings:
    defaults = default_options_c()

    def _temp(key: str) -> float:
        return float(options.get(key, defaults[key]))

    return ControlSettings(
        summer_indoor_c=_temp(CONF_SUMMER_INDOOR),
        hysteresis_c=_temp(CONF_HYSTERESIS),
        min_delta_c=_temp(CONF_MIN_DELTA),
        safety_max_c=_temp(CONF_SAFETY_MAX),
        summer_low_c=_temp(CONF_SUMMER_LOW),
        summer_medium_c=_temp(CONF_SUMMER_MEDIUM),
        summer_high_c=_temp(CONF_SUMMER_HIGH),
        winter_ceiling_c=_temp(CONF_WINTER_CEILING),
        winter_high_c=_temp(CONF_WINTER_HIGH),
        ice_dam_enabled=bool(options.get(CONF_ICE_DAM, DEFAULT_ICE_DAM)),
        ice_dam_outdoor_max_c=_temp(CONF_ICE_DAM_OUTDOOR),
        ice_dam_attic_min_c=_temp(CONF_ICE_DAM_ATTIC),
        min_on=timedelta(minutes=int(options.get(CONF_MIN_ON, DEFAULT_MIN_ON))),
        min_off=timedelta(minutes=int(options.get(CONF_MIN_OFF, DEFAULT_MIN_OFF))),
    )
