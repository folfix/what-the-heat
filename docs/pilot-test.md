# Pilot test

How to run the first real test on one closed room. Background and criteria are in section 9.1 of the [specification](specification.md).

## What runs in this test

Only PID and cycles. There is no prediction, no learning and no buffer control. The integration never writes to the heat pump. It reads the heat pump setpoint and writes only to the room's thermostat, and only in `Active` mode.

## 1. Install

With HACS: **HACS → ⋮ → Custom repositories**, add `https://github.com/folfix/what-the-heat` with the type **Integration**, then download **What the Heat**.

Without HACS: copy `custom_components/what_the_heat` to `/config/custom_components/what_the_heat`.

Restart Home Assistant in both cases.

## 2. Add the room

**Settings → Devices & services → Add integration → What the Heat**

| Field | Value |
|---|---|
| Room name | Any name. It becomes part of the entity names. |
| Thermostat | The room's `climate` entity |
| Target temperature | 21 |
| Heat pump or buffer entity | The heat pump's `climate` entity. Its set temperature is used. |
| Buffer temperature when no reading is available | The fixed temperature set on the heat pump |
| Outdoor temperature sensor | The outdoor sensor. It is only logged for now. |
| Delay of the first cycle | 0 |

A new room starts in **Observe** mode. It writes nothing to the thermostat, so this step is safe.

## 3. Baseline

1. Close the room and keep it closed during the test.
2. Set the thermostat itself to 21 °C. In Observe mode the integration does not do this.
3. Set a fixed temperature on the heat pump, at most 38 °C, and leave it unchanged. It also affects all other rooms.
4. Wait until the room has warmed up, then for several more days. The first days are not representative, since walls and soil warm slowly.

The integration measures this period too, which provides the comparison.

## 4. Take over

Set **Mode** to **Active**. The thermostat display will now alternate between target + 2 °C and target - 2 °C, which is expected.

While in Active mode:
- Change the temperature through the **Target** entity. A change made on the thermostat itself is overwritten within minutes.
- A thermostat that is switched off gets switched back on. To stop this, change the mode first.

## 5. What to watch

| Entity | Meaning |
|---|---|
| Time in band today | Share of the day within ±0.3 °C of the target |
| RMS deviation today | Typical deviation from the target |
| Longest closed today | Longest continuous period without heating |
| Heating today | Share of the day the relay was on |
| Duty | The share of time the valve should be open |
| Valve requested | What the controller wants right now |
| Setpoint writes | Total number of writes to the thermostat |
| Resent commands | Commands sent again by the watchdog |
| Problem | On when something needs attention. The `reasons` attribute says what. |

## 6. Stopping

Set **Mode** to **Hand back to thermostat**. The thermostat gets the plain target once and is then left alone. Removing or reloading the integration while in Active mode does the same.

If Home Assistant stops, the thermostat keeps its last setpoint, so the room settles near target + 2 °C or target - 2 °C.

## 7. Collecting results

On the device page, use **⋮ → Download diagnostics**. The file contains the settings and one row per day, including comfort metrics, heating share, mean temperatures and writes. `active_pct` tells baseline days and controlled days apart.
