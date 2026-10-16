"""Constants for the Airbend attic ventilation controller."""

DOMAIN = "airbend"

PLATFORMS = ["sensor", "binary_sensor", "switch"]

CONF_OUTDOOR_SENSORS = "outdoor_sensors"
CONF_ATTIC_SENSORS = "attic_sensors"
CONF_INDOOR_SENSORS = "indoor_sensors"
CONF_FAN = "fan"
CONF_FAN_TEMPERATURE = "fan_temperature"
CONF_FAN_MODE = "fan_mode"
CONF_MANUAL_MODE = "manual_mode"
CONF_WEATHER = "weather"
CONF_CO2_SENSORS = "co2_sensors"
CONF_CLIMATE = "climate"
CONF_CO2_THRESHOLD = "co2_threshold"
CONF_CO2_HYSTERESIS = "co2_hysteresis"
CONF_CIRCULATE_MODE = "circulate_mode"
CONF_IDLE_FAN_MODE = "idle_fan_mode"

CONF_SUMMER_INDOOR = "summer_indoor_c"
CONF_HYSTERESIS = "hysteresis_c"
CONF_MIN_DELTA = "min_delta_c"
CONF_SAFETY_MAX = "safety_max_c"
CONF_SUMMER_LOW = "summer_low_c"
CONF_SUMMER_MEDIUM = "summer_medium_c"
CONF_SUMMER_HIGH = "summer_high_c"
CONF_WINTER_CEILING = "winter_ceiling_c"
CONF_WINTER_HIGH = "winter_high_c"
CONF_ICE_DAM = "ice_dam_enabled"
CONF_ICE_DAM_OUTDOOR = "ice_dam_outdoor_max_c"
CONF_ICE_DAM_ATTIC = "ice_dam_attic_min_c"
CONF_MIN_ON = "min_on_minutes"
CONF_MIN_OFF = "min_off_minutes"
CONF_STALE_MINUTES = "stale_minutes"

# Absolute temperatures are °F here so the defaults stay readable.
# Deltas are also written in °F and converted with a 5/9 scale only.
DEFAULTS_F = {
    CONF_SUMMER_INDOOR: 74.0,
    CONF_HYSTERESIS: 2.0,
    CONF_MIN_DELTA: 5.0,
    CONF_SAFETY_MAX: 130.0,
    CONF_SUMMER_LOW: 80.0,
    CONF_SUMMER_MEDIUM: 100.0,
    CONF_SUMMER_HIGH: 110.0,
    CONF_WINTER_CEILING: 95.0,
    CONF_WINTER_HIGH: 110.0,
    CONF_ICE_DAM_OUTDOOR: 35.0,
    CONF_ICE_DAM_ATTIC: 60.0,
}

DELTA_KEYS = {CONF_HYSTERESIS, CONF_MIN_DELTA}

DEFAULT_ICE_DAM = True
DEFAULT_MIN_ON = 10
DEFAULT_MIN_OFF = 5
DEFAULT_STALE_MINUTES = 30
DEFAULT_MANUAL_MODE = "Idle"
DEFAULT_CO2_THRESHOLD = 600
DEFAULT_CO2_HYSTERESIS = 50
DEFAULT_CIRCULATE_MODE = "Low"
DEFAULT_IDLE_FAN_MODE = "Auto low"
DEFAULT_NAME = "Airbend"

# Form ranges in °F. The config flow converts them to the user's unit.
FORM_RANGES_F = {
    CONF_SUMMER_INDOOR: (50.0, 90.0, 1.0),
    CONF_HYSTERESIS: (0.5, 10.0, 0.5),
    CONF_MIN_DELTA: (1.0, 20.0, 0.5),
    CONF_SAFETY_MAX: (100.0, 160.0, 1.0),
    CONF_SUMMER_LOW: (60.0, 120.0, 1.0),
    CONF_SUMMER_MEDIUM: (70.0, 140.0, 1.0),
    CONF_SUMMER_HIGH: (90.0, 150.0, 1.0),
    CONF_WINTER_CEILING: (70.0, 130.0, 1.0),
    CONF_WINTER_HIGH: (80.0, 150.0, 1.0),
    CONF_ICE_DAM_OUTDOOR: (20.0, 50.0, 1.0),
    CONF_ICE_DAM_ATTIC: (40.0, 100.0, 1.0),
}
