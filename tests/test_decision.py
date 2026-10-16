"""Decisions for summer cooling, winter buffer, and fan-speed mapping."""

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "airbend"
    / "decision.py"
)
_SPEC = importlib.util.spec_from_file_location("airbend_decision", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
decision = importlib.util.module_from_spec(_SPEC)
sys.modules["airbend_decision"] = decision
_SPEC.loader.exec_module(decision)

ControlSettings = decision.ControlSettings
FanSpeed = decision.FanSpeed
Season = decision.Season
Snapshot = decision.Snapshot
command_for = decision.command_for
decide = decision.decide
ForecastPoint = decision.ForecastPoint

NOW = datetime(2026, 7, 1, 15, 0, tzinfo=timezone.utc)


def settings(**overrides: object) -> ControlSettings:
    base = dict(
        summer_indoor_c=23.3,
        hysteresis_c=1.1,
        min_delta_c=2.8,
        safety_max_c=54.4,
        summer_low_c=26.7,
        summer_medium_c=37.8,
        summer_high_c=43.3,
        winter_ceiling_c=35.0,
        winter_high_c=43.3,
        ice_dam_enabled=True,
        ice_dam_outdoor_max_c=1.7,
        ice_dam_attic_min_c=15.6,
        min_on=timedelta(minutes=10),
        min_off=timedelta(minutes=5),
    )
    base.update(overrides)
    return ControlSettings(**base)


def snap(**overrides: object) -> Snapshot:
    base = dict(
        outdoor_c=26.0,
        attic_c=40.0,
        indoor_c=26.0,
        season=None,
        applied_speed=FanSpeed.OFF,
        applied_at=None,
        now=NOW,
    )
    base.update(overrides)
    return Snapshot(**base)


def test_summer_uses_cooler_outside_air_and_steps_the_fan() -> None:
    low = decide(snap(attic_c=33.0, outdoor_c=30.0, indoor_c=25.0), settings())
    medium = decide(snap(attic_c=39.0, outdoor_c=25.0, indoor_c=25.0), settings())
    high = decide(snap(attic_c=45.0, outdoor_c=30.0, indoor_c=25.0), settings())

    assert low.season is Season.SUMMER
    assert low.speed is FanSpeed.LOW
    assert medium.speed is FanSpeed.MEDIUM
    assert high.speed is FanSpeed.HIGH


def test_summer_does_not_pull_hotter_air_into_the_attic() -> None:
    decision = decide(snap(attic_c=40.0, outdoor_c=42.0, indoor_c=27.0), settings())

    assert decision.speed is FanSpeed.OFF
    assert "not usefully cooler" in decision.reason


def test_summer_cools_the_attic_when_it_is_warming_a_house_above_the_target() -> None:
    # Want 70°F indoors. The house is 75°F, the attic is 85°F, and it is 77°F outside.
    decision = decide(
        snap(indoor_c=23.9, attic_c=29.4, outdoor_c=25.0),
        settings(summer_indoor_c=21.1),
    )

    assert decision.season is Season.SUMMER
    assert decision.speed is FanSpeed.LOW
    assert "low-speed" in decision.reason


def test_summer_runs_low_below_the_speed_step_when_outside_air_can_help() -> None:
    # 75°F house, 78°F attic, 70°F outside. Attic is under the 80°F low step.
    decision = decide(
        snap(indoor_c=23.9, attic_c=25.6, outdoor_c=21.1),
        settings(summer_indoor_c=21.1),
    )

    assert decision.speed is FanSpeed.LOW
    assert "bring it down" in decision.reason


def test_summer_stays_off_when_outside_air_cannot_meaningfully_cool_the_attic() -> None:
    # 75°F house, 79°F attic, 78°F outside. The fan could only shave about 1°F.
    decision = decide(snap(indoor_c=23.9, attic_c=26.1, outdoor_c=25.6), settings())

    assert decision.season is Season.SUMMER
    assert decision.speed is FanSpeed.OFF
    assert "not usefully cooler" in decision.reason


def test_winter_imports_warmer_outside_air_into_a_cold_attic() -> None:
    # 61°F house, 50°F attic, 68°F outside.
    decision = decide(snap(indoor_c=16.1, attic_c=10.0, outdoor_c=20.0), settings())

    assert decision.season is Season.WINTER
    assert decision.speed is FanSpeed.MEDIUM
    assert "lifting a cold attic" in decision.reason


def test_summer_stays_off_when_the_attic_is_not_warming_the_house() -> None:
    # 77°F house, 73°F attic, 64°F outside.
    decision = decide(snap(indoor_c=25.0, attic_c=22.8, outdoor_c=17.8), settings())

    assert decision.speed is FanSpeed.OFF
    assert "no warmer than the house" in decision.reason


def test_indoor_hysteresis_holds_summer_until_the_house_actually_cools() -> None:
    held = decide(
        snap(indoor_c=22.5, season=Season.SUMMER, attic_c=33.0, outdoor_c=30.0),
        settings(),
    )
    released = decide(
        snap(indoor_c=22.0, season=Season.SUMMER, attic_c=33.0, outdoor_c=24.0),
        settings(),
    )

    assert held.season is Season.SUMMER
    assert held.speed is FanSpeed.LOW
    assert released.season is Season.WINTER
    assert released.speed is FanSpeed.OFF


def test_winter_holds_a_warm_attic_as_a_buffer() -> None:
    decision = decide(
        snap(indoor_c=20.0, attic_c=28.0, outdoor_c=5.0),
        settings(),
    )

    assert decision.season is Season.WINTER
    assert decision.speed is FanSpeed.OFF
    assert "warmer attic" in decision.reason


def test_winter_ventilates_a_hot_attic_and_a_melting_roof_deck() -> None:
    hot = decide(snap(indoor_c=20.0, attic_c=36.0, outdoor_c=10.0), settings())
    ice = decide(snap(indoor_c=20.0, attic_c=18.0, outdoor_c=0.0), settings())

    assert hot.speed is FanSpeed.LOW
    assert ice.speed is FanSpeed.LOW
    assert "snow" in ice.reason


def test_safety_limit_overrides_a_hot_outdoor_and_a_minimum_runtime() -> None:
    hotter_outside = decide(
        snap(attic_c=60.0, outdoor_c=62.0, indoor_c=20.0),
        settings(),
    )
    forced = decide(
        snap(
            attic_c=60.0,
            outdoor_c=30.0,
            indoor_c=20.0,
            applied_speed=FanSpeed.OFF,
            applied_at=NOW - timedelta(minutes=1),
        ),
        settings(),
    )

    assert hotter_outside.speed is FanSpeed.OFF
    assert hotter_outside.safety_bypass is True
    assert forced.speed is FanSpeed.HIGH
    assert forced.safety_bypass is True


def test_minimum_runtime_holds_a_drop_but_not_a_step_up() -> None:
    held = decide(
        snap(
            attic_c=22.0,
            outdoor_c=16.0,
            indoor_c=26.0,
            season=Season.SUMMER,
            applied_speed=FanSpeed.LOW,
            applied_at=NOW - timedelta(minutes=2),
        ),
        settings(),
    )
    stepped = decide(
        snap(
            attic_c=45.0,
            outdoor_c=28.0,
            indoor_c=26.0,
            season=Season.SUMMER,
            applied_speed=FanSpeed.LOW,
            applied_at=NOW - timedelta(minutes=2),
        ),
        settings(),
    )

    assert held.speed is FanSpeed.LOW
    assert held.unconstrained_speed is FanSpeed.OFF
    assert "short-cycled" in held.reason
    assert stepped.speed is FanSpeed.HIGH


def test_missing_attic_temperature_turns_the_fan_off() -> None:
    decision = decide(snap(attic_c=None), settings())

    assert decision.speed is FanSpeed.OFF


def test_two_speed_fan_maps_medium_to_high() -> None:
    assert command_for(FanSpeed.OFF, ["Low", "High"]).on is False
    assert command_for(FanSpeed.LOW, ["Low", "High"]).preset_mode == "Low"
    assert command_for(FanSpeed.MEDIUM, ["Low", "High"]).preset_mode == "High"
    assert command_for(FanSpeed.HIGH, ["Low", "Medium", "High"]).preset_mode == "High"


def test_percentage_fan_when_there_are_no_presets() -> None:
    command = command_for(FanSpeed.LOW, None)

    assert command.on is True
    assert command.preset_mode is None
    assert command.percentage == 33


def test_summer_uses_medium_when_outside_air_is_clearly_cooler() -> None:
    # 78.7°F house, 82.8°F attic, 73.9°F outside.
    decision = decide(
        snap(indoor_c=25.94, attic_c=28.22, outdoor_c=23.28),
        settings(),
    )

    assert decision.season is Season.SUMMER
    assert decision.speed is FanSpeed.MEDIUM
    assert "medium" in decision.reason


def test_forecast_flushes_the_attic_before_a_hot_afternoon() -> None:
    # 68°F house, 75°F attic, 61°F outside, 88°F forecast in 6 hours.
    decision = decide(
        snap(
            indoor_c=20.0,
            attic_c=24.0,
            outdoor_c=16.0,
            forecast=(ForecastPoint(6.0, 31.0),),
        ),
        settings(),
    )

    assert decision.season is Season.WINTER
    assert decision.speed is FanSpeed.LOW
    assert "hot day" in decision.reason


def test_forecast_does_not_dump_heat_before_a_cold_night() -> None:
    decision = decide(
        snap(
            indoor_c=20.0,
            attic_c=24.0,
            outdoor_c=16.0,
            forecast=(ForecastPoint(3.0, 4.0), ForecastPoint(10.0, 31.0)),
        ),
        settings(),
    )

    assert decision.speed is FanSpeed.OFF
    assert "hot day" not in decision.reason


def test_forecast_banks_warmth_faster_before_a_cold_night() -> None:
    # 61°F house, 50°F attic, 58°F outside, 36°F tonight.
    decision = decide(
        snap(
            indoor_c=16.0,
            attic_c=10.0,
            outdoor_c=14.5,
            forecast=(ForecastPoint(8.0, 2.0),),
        ),
        settings(),
    )

    assert decision.speed is FanSpeed.MEDIUM
    assert "cold night" in decision.reason
