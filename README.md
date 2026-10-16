# Airbend

Home Assistant controller for a QuietCool (or any preset/percentage) attic fan. It averages the outdoor, attic, and indoor temperature sensors you choose, then runs the fan only when outside air will actually help. It can also run the house blower when a bedroom gets stuffy.

This integration does not talk to the fan over Bluetooth. Pair the fan with something like [QuietCool BLE](https://github.com/rwarner/ha-quietcool-ble) or the ESPHome QuietCool firmware first, then point Airbend at that fan entity.

## What it does

**Averaging.** Outdoor, attic, and indoor temperatures are each the average of the sensors you select. The attic average includes the fan's own temperature sensor when you select it. If a sensor goes unavailable, Airbend keeps its last reading in the average until that reading is 30 minutes old. A short dropout does not make the average jump to whichever sensor stayed up. After 30 minutes with no new reading, that sensor is left out.

**Summer** starts when the indoor average reaches the target indoor temperature (default 74°F) and stays active until the house falls by the hysteresis (default 2°F). Speed then follows the attic average:

- Low at 80°F attic
- Medium at 100°F, or sooner when outside air is at least 8°F cooler than the attic
- High at 110°F

A house at 75°F with a 70°F target, an 85°F attic, and 77°F outside air runs on low. Below the low-speed temperature the fan still runs on low when the attic is warmer than the house and outside air is at least 5°F cooler. It keeps running after the attic falls below the indoor temperature, while the house is still warm and outside air is at least 5°F cooler than the attic. It stays off when outside air can barely move the attic. At 75°F indoors, 79°F in the attic, and 78°F outside, the fan stays off: running it could only shave about 1°F, and the attic would still be warmer than the house.

**Winter** uses warmer outside air to lift a cold attic toward the indoor target. A 61°F house with a 50°F attic and 68°F outside air runs the fan, because that outside air can warm the attic and slow the heat loss through the ceiling. The fan stays off once the attic is up to the indoor target, or when outside air is less than 5°F warmer than the attic. It also cools the attic if the buffer gets too hot (default 95°F, high at 110°F). Outdoor air hotter than that buffer limit is not pulled in.

**Forecast** is optional. Point Airbend at a weather entity that provides an hourly forecast, such as Met.no. In the next 12 hours, if a hot afternoon is coming and outside air is still cooler than the attic, the fan flushes the attic before the heat arrives. If a cold night is coming first and outside air is warmer than the attic, the fan banks that warmth. A cold night that arrives before the hot afternoon wins, so the attic is not emptied of heat the house will want overnight. Forecast high and forecast low show the next 18 hours.

**Safety** always wins. At 130°F the fan goes to high if outside air is cooler. If outside air is hotter, it stays off rather than making the attic worse. That override ignores the minimum on/off timers.

**Ice-dam guard** (on by default) runs the fan on low when it is freezing outside (35°F or below) and the attic is still 60°F or warmer. A mild winter attic, around 50°F, is left alone. Turn the guard off in the integration options if you would rather keep every degree of attic warmth.

The fan also stays at a speed for a minimum run (10 minutes) and minimum off time (5 minutes). Stepping *up* is immediate. A safety trip is immediate in either direction.

Two-speed QuietCool fans expose Low and High. Airbend maps medium onto high. Fans with no presets get 33% / 66% / 100%.

**Hazard shutdown.** Select smoke, carbon monoxide, and gas detectors, plus any smart outlets that should turn off. If any detector is on, Airbend turns the attic fan off, turns the HVAC off, and turns those outlets off. It ignores the minimum run time. When every detector is clear, it restores the HVAC mode and the outlets it turned off. A detector that is unavailable does not count as an alarm. This does not replace the detectors' own alarms.

**Bedroom CO2** replaces a separate Fresh Air automation. Pick the bedroom carbon-dioxide sensors and the house thermostat. If any bedroom reaches 600 ppm, Airbend sets the thermostat fan to `Low`. It returns the fan to `Auto low` only after every bedroom is under 550 ppm, and only if the fan is still on `Low`. The attic speed does not change. Use the **CO2 circulation** switch to pause this without pausing the attic fan. If your thermostat uses different fan-mode names, set those names in the options.

## Install

Home Assistant 2025.1 or newer.

### HACS

1. In HACS, open **Custom repositories** (the same dialog as the three-dot menu on the Integrations page).
2. Add `https://github.com/ppicazo/ha_airbend` and set the type to **Integration**.
3. Search for **Airbend** in HACS integrations and download it.
4. Restart Home Assistant.
5. Go to **Settings → Devices & services → Add integration** and select **Airbend**.

### Manual

1. Copy `custom_components/airbend` into your Home Assistant `config/custom_components/airbend` directory.
2. Restart Home Assistant.
3. Add the **Airbend** integration.

### Setup

1. Select one or more outdoor, attic, and indoor temperature sensors. They need the `temperature` device class. Each group is averaged, and a sensor that drops out keeps its last reading for 30 minutes.
2. Select the QuietCool fan.
3. Select the fan's temperature sensor if you want it included in the attic average.
4. Select the fan's mode entity and set **Mode to select before taking control** to the option that means manual. ESPHome QuietCool uses `Run` (Timer / Run / Smart). The BLE integration uses `Idle` (Idle / Timer / TH). Airbend switches to that mode so the fan's built-in thermostat does not fight these rules.
5. For bedroom circulation, select the carbon-dioxide sensors and the house thermostat. The defaults match a thermostat whose fan modes are `Low` and `Auto low`. Change those names if yours differ, then turn off any older automation that was setting the same fan mode.

The status sensor says why the fan is at its current speed. **Automatic control** pauses the attic fan, and **CO2 circulation** pauses the bedroom blower. Turning one off leaves that device where it is.

Thresholds are in the integration's configure dialog and follow your unit system (°F or °C).
