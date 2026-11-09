# Pilot test

How to run the first real test on one closed room. Background and criteria are in section 9.1 of the [specification](specification.md).

## What runs in this test

Only PID and cycles, with no prediction from the forecast. Each room learns its steady demand and, with a PV sensor, what the sun does to it at each hour. The integration writes only to the room's thermostat, and only in `Active` mode. It neither reads nor changes the mixing valves, the buffer or the heat pump.

## 1. Install

With the Marketplace (HACS before Home Assistant 2026.11): add `https://github.com/folfix/what-the-heat` as a custom repository of the type **Integration**, then download **What the Heat**.

Without HACS: copy `custom_components/what_the_heat` to `/config/custom_components/what_the_heat`.

Restart Home Assistant in both cases.

## 2. Add the shared settings and the room

**Settings → Devices & services → Add integration → What the Heat**

The first time, the form asks for the sensors shared by all rooms:

| Field | Value |
|---|---|
| Outdoor temperature sensor | The outdoor sensor, preferably in the shade. Each room learns how much more heat it needs when it is colder outside than usual. |
| PV power sensor | The power of a PV installation, if there is one, preferably read locally. Each room then learns what the sun does to it. |

They become the **Shared settings** entry of the integration. Change them later with **Configure** on that entry.

Before adding the room, check the thermostat's own dead zone, which Meross LAN shows as a separate number entity. It should be at most about 2.5 °C. With a wider one, the setpoints the controller uses may not switch the thermostat while the room is near its target, so lower it.

Then add the room with **Add entry**:

| Field | Value |
|---|---|
| Room name | Any name. It becomes part of the entity names. |
| Thermostat | The room's `climate` entity |
| Target temperature | 21 |
| Delay of the first cycle | 0 |

A new room starts in **Active** mode and takes over the thermostat right away. The thermostat display will alternate between target + 3 °C and target - 3 °C, which is expected.

Then open the **What the Heat** page in the sidebar and set the water temperature to what the mixing valves are set to. It is shared by all rooms, and the default is 30 °C.

## 3. Baseline

For a comparison with the plain thermostat, run a baseline first:

1. Close the room and keep it closed during the test.
2. Set the room's **Mode** entity to **Observe**. The thermostat gets the plain target back, and from then on nothing is written to it.
3. Keep the mixing valve at the same temperature for both the baseline and the controlled period. Any change also affects the other rooms on that floor.
4. Wait until the room has warmed up, then for several more days. The first days are not representative, since walls and soil warm slowly.

The integration measures this period too, which provides the comparison.

## 4. Take over

Set the room's **Mode** entity back to **Active**.

While in Active mode:
- Change the temperature through the **Target** entity. A change made on the thermostat itself is overwritten within minutes.
- A thermostat that is switched off gets switched back on. To stop this, change the mode first.

## 5. What to watch

The **What the Heat** page in the sidebar shows the main values for all rooms, and its own version in the header. Each room also has a thermostat entity for a regular tile or thermostat card on a dashboard, which changes the target and the mode.

| Entity | Meaning |
|---|---|
| Time in band today | Share of the day within ±0.3 °C of the target |
| RMS deviation today | Typical deviation from the target |
| Longest closed today | Longest continuous period without heating |
| Heating today | Share of the day the relay was on |
| Duty | The share of time the valve should be open |
| Learned demand | The share of time the valve needs to be open to hold the target at the current water temperature. Empty until there are about 6 hours of data near the target. The attributes say how much data is behind it and where it comes from. |
| Sun correction | How much the sun takes off the duty right now, with a PV sensor set. It stays at 0 until the room has learned from 3 sunny days, which the `sunny_days` attribute counts. `sun_pct` is the PV power as a share of the highest seen lately. |
| Outdoor correction | How much the weather adds to or takes off the duty right now, with an outdoor sensor set. `colder_than_usual` says how much colder than the last day's average it is outside, and stays empty for the first day. `weight` is what the room has learned so far, and starts at 0. |
| Valve requested | What the controller wants right now |
| Setpoint writes | Total number of writes to the thermostat |
| Resent commands | Commands sent again by the watchdog |
| Problem | On when something needs attention. The `reasons` attribute says what. |

If something unusual has misled the controller, such as a long open window, use the **Reset learning** button on the room's device page. It clears the learned demand and what the room learned about the sun, and keeps the mode, the target and the daily measurements. Expect the room to dip for a while as the controller learns again, so note the moment when comparing results.

## 6. Stopping

Set the room's **Mode** entity to **Hand back to thermostat**. The thermostat gets the plain target once and is then left alone. Going from Active to Observe, or removing or reloading the integration while in Active mode, does the same.

If Home Assistant stops, the thermostat keeps its last setpoint, so the room slowly moves toward target + 3 °C or target - 3 °C.

## 7. Collecting results

Use **Download full report** at the bottom of the **What the Heat** page. It saves one file with the last 7 days of all rooms: the recorded history of the thermostats, the outdoor and PV sensors and the rooms' own entities, and everything below. It needs the recorder, which Home Assistant runs by default.

For a single room, use **Download diagnostics** on its device page. The file contains the settings and one row per day, including comfort metrics, heating share, mean temperatures, writes, the day's PV energy and the mean sun correction. `active_pct` tells baseline days and controlled days apart. What the room learned about the sun is under `runner` and `learned`.

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
