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
| Typical buffer temperature | Used while the heat pump exposes no set temperature, such as on its own weather curve. See step 4. |
| Outdoor temperature sensor | The outdoor sensor. It is only logged for now. |
| Delay of the first cycle | 0 |

A new room starts in **Observe** mode. It writes nothing to the thermostat, so this step is safe.

## 3. Baseline

1. Close the room and keep it closed during the test.
2. Set the thermostat itself to 21 °C. In Observe mode the integration does not do this.
3. Leave the heat pump in one mode for both the baseline and the controlled period: on its own curve, or at a fixed temperature of at most 38 °C. On the curve, the limit depends on the curve's settings. Any change also affects all other rooms.
4. Wait until the room has warmed up, then for several more days. The first days are not representative, since walls and soil warm slowly.

The integration measures this period too, which provides the comparison.

## 4. Take over

If the heat pump runs on its own curve, first set **Typical buffer temperature** in the integration's settings to the water temperature it usually runs at. Within about 2 °C of the real value the results barely change in simulation. At 4 °C most simulated rooms still hold, but some get clearly worse. At a fixed temperature, its set value is read directly.

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

On the device page, use **Download diagnostics**. The file contains the settings and one row per day, including comfort metrics, heating share, mean temperatures and writes. `active_pct` tells baseline days and controlled days apart.

## 8. Logs

By default only failed commands and problems reach the log. To see every decision, add this to `configuration.yaml` and restart:

```yaml
logger:
  default: warning
  logs:
    custom_components.what_the_heat: debug
```

Then look under **Settings → System → Logs → Show raw logs**, or search for `what_the_heat`. At this level there is one line per minute for each room with the temperatures, duty, integral and requested setpoint, as well as commands, mode changes and problems. Use `info` instead of `debug` to keep only commands, mode changes and problems.

For following behaviour over time, charts of the integration's entities are usually easier to read than the log. Try **Duty**, **Requested setpoint** and **Filtered temperature** next to the thermostat's own history.
