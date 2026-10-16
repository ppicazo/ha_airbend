"""Pure ventilation decisions.

Temperatures are Celsius. Deltas are Celsius degrees, not absolute
temperatures — do not run them through an absolute unit converter.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum


class Season(str, Enum):
    SUMMER = "summer"
    WINTER = "winter"
    UNKNOWN = "unknown"


class FanSpeed(str, Enum):
    OFF = "off"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


SPEED_RANK = {
    FanSpeed.OFF: 0,
    FanSpeed.LOW: 1,
    FanSpeed.MEDIUM: 2,
    FanSpeed.HIGH: 3,
}

_PRESET_ORDER = {
    FanSpeed.LOW: ("low",),
    FanSpeed.MEDIUM: ("medium", "med", "high", "low"),
    FanSpeed.HIGH: ("high", "medium", "med", "low"),
}

_PERCENT = {
    FanSpeed.LOW: 33,
    FanSpeed.MEDIUM: 66,
    FanSpeed.HIGH: 100,
}


@dataclass(frozen=True)
class ControlSettings:
    """Thresholds, stored in Celsius."""

    summer_indoor_c: float
    hysteresis_c: float
    min_delta_c: float
    safety_max_c: float
    summer_low_c: float
    summer_medium_c: float
    summer_high_c: float
    winter_ceiling_c: float
    winter_high_c: float
    ice_dam_enabled: bool
    ice_dam_outdoor_max_c: float
    ice_dam_attic_min_c: float
    min_on: timedelta
    min_off: timedelta


@dataclass(frozen=True)
class ForecastPoint:
    """One hourly outdoor forecast temperature."""

    hours: float
    temp_c: float


@dataclass(frozen=True)
class Snapshot:
    """Inputs for one evaluation."""

    outdoor_c: float | None
    attic_c: float | None
    indoor_c: float | None
    season: Season | None
    applied_speed: FanSpeed
    applied_at: datetime | None
    now: datetime
    forecast: tuple[ForecastPoint, ...] = ()


@dataclass(frozen=True)
class FanCommand:
    """What to send to the fan entity."""

    on: bool
    preset_mode: str | None = None
    percentage: int | None = None

    @property
    def label(self) -> str:
        if not self.on:
            return FanSpeed.OFF.value
        if self.preset_mode:
            return self.preset_mode
        return f"{self.percentage}%"


@dataclass(frozen=True)
class Decision:
    """Result of one evaluation."""

    season: Season
    speed: FanSpeed
    unconstrained_speed: FanSpeed
    reason: str
    safety_bypass: bool


def resolve_season(
    indoor_c: float | None,
    settings: ControlSettings,
    previous: Season | None,
) -> Season:
    """Pick summer or winter from indoor temperature, with hysteresis."""

    if indoor_c is None:
        return previous or Season.UNKNOWN

    if previous is Season.SUMMER:
        if indoor_c <= settings.summer_indoor_c - settings.hysteresis_c:
            return Season.WINTER
        return Season.SUMMER

    if previous is Season.WINTER:
        if indoor_c >= settings.summer_indoor_c:
            return Season.SUMMER
        return Season.WINTER

    if indoor_c >= settings.summer_indoor_c:
        return Season.SUMMER
    return Season.WINTER


def decide(snapshot: Snapshot, settings: ControlSettings) -> Decision:
    """Choose a fan speed for the current temperatures."""

    season = resolve_season(snapshot.indoor_c, settings, snapshot.season)
    raw_speed, reason, bypass = _raw_speed(snapshot, settings, season)
    speed = _apply_cycle(raw_speed, bypass, snapshot, settings)
    if speed is not raw_speed:
        reason = (
            f"{reason} Holding {speed.value} a little longer so the motor "
            "is not short-cycled."
        )
    return Decision(
        season=season,
        speed=speed,
        unconstrained_speed=raw_speed,
        reason=reason,
        safety_bypass=bypass,
    )


def command_for(speed: FanSpeed, preset_modes: list[str] | None) -> FanCommand:
    """Map a logical speed onto the fan's presets or a percentage."""

    if speed is FanSpeed.OFF:
        return FanCommand(on=False)

    available = {}
    for mode in preset_modes or []:
        key = mode.strip().lower()
        if key and key not in {"off", "on"}:
            available.setdefault(key, mode)

    for key in _PRESET_ORDER[speed]:
        if key in available:
            return FanCommand(on=True, preset_mode=available[key])

    return FanCommand(on=True, percentage=_PERCENT[speed])


def _raw_speed(
    snapshot: Snapshot,
    settings: ControlSettings,
    season: Season,
) -> tuple[FanSpeed, str, bool]:
    attic = snapshot.attic_c
    outdoor = snapshot.outdoor_c

    if attic is None:
        return (
            FanSpeed.OFF,
            "Attic temperature is unavailable, so the fan stays off.",
            False,
        )

    delta = None if outdoor is None else attic - outdoor
    outdoor_useful = delta is not None and delta >= settings.min_delta_c

    if attic >= settings.safety_max_c:
        if outdoor is None or outdoor_useful:
            return (
                FanSpeed.HIGH,
                "Attic is above the safety limit and outside air can help.",
                True,
            )
        return (
            FanSpeed.OFF,
            "Attic is above the safety limit, but outside air is not cooler.",
            True,
        )

    if season is Season.SUMMER:
        base = _summer_speed(
            attic, outdoor, snapshot.indoor_c, outdoor_useful, settings
        )
    elif season is Season.UNKNOWN:
        base = (
            FanSpeed.OFF,
            "Indoor temperature is unavailable, so only the safety limit would run the fan.",
            False,
        )
    else:
        base = _winter_speed(attic, outdoor, outdoor_useful, settings)

    return _prefer_forecast(
        base,
        _forecast_speed(attic, outdoor, season, settings, snapshot.forecast),
    )


def _summer_speed(
    attic: float,
    outdoor: float | None,
    indoor: float | None,
    outdoor_useful: bool,
    settings: ControlSettings,
) -> tuple[FanSpeed, str, bool]:
    if outdoor is None:
        return (
            FanSpeed.OFF,
            "Summer mode, but outdoor temperature is unavailable.",
            False,
        )
    if not outdoor_useful:
        return (
            FanSpeed.OFF,
            "Summer mode, and outside air is not usefully cooler than the attic.",
            False,
        )
    if indoor is not None and attic <= indoor:
        return (
            FanSpeed.OFF,
            "Summer: the attic is already no warmer than the house.",
            False,
        )
    if attic >= settings.summer_high_c:
        return FanSpeed.HIGH, "Summer: the attic is hot and outside air is cooler.", False
    if attic >= settings.summer_medium_c:
        return (
            FanSpeed.MEDIUM,
            "Summer: the attic reached the medium-speed temperature.",
            False,
        )
    if attic >= settings.summer_low_c:
        if attic - outdoor >= _MEDIUM_BOOST_C:
            return (
                FanSpeed.MEDIUM,
                "Summer: outside air is cool enough to use medium.",
                False,
            )
        return (
            FanSpeed.LOW,
            "Summer: the attic reached the low-speed temperature.",
            False,
        )
    return (
        FanSpeed.LOW,
        "Summer: the attic is warming the house and outside air can bring it down.",
        False,
    )


# Warm the attic on medium once outside air is this much warmer.
_WARM_MEDIUM_C = 15.0 * 5.0 / 9.0
# In summer, step from low to medium when outside air is this much cooler than the attic.
_MEDIUM_BOOST_C = 8.0 * 5.0 / 9.0
# A later forecast this much colder than the current outdoor air is a cold night.
_COLD_DROP_C = 10.0 * 5.0 / 9.0
_HOT_LOOKAHEAD_H = 12.0
_COLD_LOOKAHEAD_H = 18.0


def _winter_speed(
    attic: float,
    outdoor: float | None,
    outdoor_useful: bool,
    settings: ControlSettings,
) -> tuple[FanSpeed, str, bool]:
    if attic >= settings.winter_high_c and (outdoor is None or outdoor_useful):
        return (
            FanSpeed.HIGH,
            "Winter: the attic is hot enough that the buffer is no longer useful.",
            False,
        )
    if attic >= settings.winter_ceiling_c and outdoor_useful:
        midpoint = (settings.winter_ceiling_c + settings.winter_high_c) / 2
        if attic >= midpoint:
            return (
                FanSpeed.MEDIUM,
                "Winter: the attic is warmer than the buffer allows.",
                False,
            )
        return (
            FanSpeed.LOW,
            "Winter: easing the attic back down to a useful buffer.",
            False,
        )
    if (
        settings.ice_dam_enabled
        and outdoor is not None
        and outdoor <= settings.ice_dam_outdoor_max_c
        and attic >= settings.ice_dam_attic_min_c
        and outdoor_useful
    ):
        return (
            FanSpeed.LOW,
            "Winter: outside is freezing and the attic is warm enough to melt roof snow.",
            False,
        )
    warming = _winter_warm(attic, outdoor, settings)
    if warming is not None:
        return warming
    if (
        outdoor is not None
        and outdoor > attic
        and attic < settings.summer_indoor_c
    ):
        return (
            FanSpeed.OFF,
            "Winter: outside air is not warm enough to lift the attic toward the house.",
            False,
        )
    return (
        FanSpeed.OFF,
        "Winter: holding a warmer attic so the house loses less heat upward.",
        False,
    )


def _winter_warm(
    attic: float,
    outdoor: float | None,
    settings: ControlSettings,
) -> tuple[FanSpeed, str, bool] | None:
    """Import outdoor air when it can warm a cold attic up toward the house."""

    if outdoor is None or outdoor > settings.winter_ceiling_c:
        return None
    if attic >= settings.summer_indoor_c:
        return None
    rise = outdoor - attic
    if rise < settings.min_delta_c:
        return None
    reason = "Winter: outside air is warmer, so the fan is lifting a cold attic toward the house."
    if rise >= _WARM_MEDIUM_C and outdoor <= settings.summer_indoor_c:
        return FanSpeed.MEDIUM, reason, False
    return FanSpeed.LOW, reason, False


def _prefer_forecast(
    base: tuple[FanSpeed, str, bool],
    forecast: tuple[FanSpeed, str] | None,
) -> tuple[FanSpeed, str, bool]:
    speed, reason, bypass = base
    if forecast is None:
        return base
    forecast_speed, forecast_reason = forecast
    if SPEED_RANK[forecast_speed] > SPEED_RANK[speed]:
        return forecast_speed, forecast_reason, bypass
    return base


def _forecast_speed(
    attic: float,
    outdoor: float | None,
    season: Season,
    settings: ControlSettings,
    forecast: tuple[ForecastPoint, ...],
) -> tuple[FanSpeed, str] | None:
    """Flush before a hot day, or bank warmth before a cold night."""

    if outdoor is None or not forecast:
        return None
    hot = _first_where(
        forecast,
        _HOT_LOOKAHEAD_H,
        lambda point: point.temp_c >= settings.summer_low_c,
    )
    cold = _first_where(
        forecast,
        _COLD_LOOKAHEAD_H,
        lambda point: outdoor - point.temp_c >= _COLD_DROP_C,
    )
    hot_first = hot is not None and (cold is None or hot.hours <= cold.hours)
    cold_first = cold is not None and (hot is None or cold.hours < hot.hours)

    if (
        hot_first
        and hot is not None
        and attic - outdoor >= settings.min_delta_c
        and hot.temp_c - outdoor >= settings.min_delta_c
    ):
        speed = (
            FanSpeed.MEDIUM
            if hot.temp_c >= settings.summer_high_c
            else FanSpeed.LOW
        )
        return (
            speed,
            "A hot day is coming, so the fan is flushing the attic while outside air is still cool.",
        )

    if (
        cold_first
        and season is not Season.SUMMER
        and attic < settings.summer_indoor_c
        and outdoor <= settings.winter_ceiling_c
        and outdoor - attic >= settings.min_delta_c
    ):
        drop = outdoor - cold.temp_c if cold is not None else 0.0
        speed = FanSpeed.MEDIUM if drop >= _WARM_MEDIUM_C else FanSpeed.LOW
        return (
            speed,
            "A cold night is coming, so the fan is banking warmer outside air in the attic.",
        )
    return None


def _first_where(forecast, horizon: float, predicate) -> ForecastPoint | None:
    for point in sorted(forecast, key=lambda item: item.hours):
        if point.hours < 0 or point.hours > horizon:
            continue
        if predicate(point):
            return point
    return None


def _apply_cycle(
    desired: FanSpeed,
    bypass: bool,
    snapshot: Snapshot,
    settings: ControlSettings,
) -> FanSpeed:
    applied = snapshot.applied_speed
    applied_at = snapshot.applied_at
    if bypass or desired is applied or applied_at is None:
        return desired

    elapsed = snapshot.now - applied_at
    if SPEED_RANK[desired] > SPEED_RANK[applied]:
        return desired
    if applied is FanSpeed.OFF and elapsed < settings.min_off:
        return applied
    if elapsed < settings.min_on:
        return applied
    return desired
