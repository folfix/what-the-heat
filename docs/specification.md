# what-the-heat: specification

Smart control of water-based underfloor heating in Home Assistant, built from scratch as a custom integration.

Conventions: **[REQUIREMENT]** comes from the owner, **[PROPOSAL]** comes from analysis and may change, **[TODO]** is missing information.

All simulation figures in this document come from throwaway models with assumed room data. They compare design options. They do not predict how a real house behaves, and every threshold must be checked against real data.

---

## 1. Goal

Keep each room at its target temperature with the smallest possible deviation, using loops that stay open for as long as possible at a low, fixed water temperature.

Today each room runs a plain on/off thermostat with a 0.3 °C differential. That heats the screed in bursts and ignores the large thermal inertia of the floor, the sun and the water temperature.

The guiding principle **[REQUIREMENT]**: it is better to use a low water temperature and keep a loop open nearly 100% of the time than to use hot water and run rare, short cycles.

---

## 2. Owner requirements

### 2.1 Current state
- **[REQUIREMENT]** Water-based underfloor heating. Every room has a thermostat and every thermostat is connected to Home Assistant.
- **[REQUIREMENT]** A thermostat is normally set to about 21 °C with a 0.3 °C differential.
- **[REQUIREMENT]** The heat source is a heat pump with a buffer. Each floor has a three-way mixing valve that sets the temperature of the water going into its loops.
- **[REQUIREMENT]** There are no floor sensors. Floor temperature is unknown and will stay unknown.

### 2.2 Predictive switching
- **[REQUIREMENT]** Use historical data to determine how the floor behaves in each room.
- **[REQUIREMENT]** When a room temperature gradually falls, open the loop earlier than the thermostat would, by raising the thermostat setpoint from Home Assistant.
- **[REQUIREMENT]** Likewise close the loop earlier, because the floor keeps releasing heat for a long time.
- **[REQUIREMENT]** Take time of day and the sun into account.
- **[REQUIREMENT]** Take the water temperature into account.

### 2.3 Loop modulation, like an induction hob (preferred)
- **[REQUIREMENT]** Loops open and close at a frequency chosen by the algorithm, for example 20 minutes open and 20 minutes closed.
- **[REQUIREMENT]** The floor is never cold, and heating it from cold is avoided.
- **[REQUIREMENT]** Control still works through thermostat setpoints from Home Assistant.

### 2.4 Learning
- **[REQUIREMENT]** A learning algorithm studies each room individually and adapts the parameters accordingly. The water temperature and external factors such as the sun matter.

### 2.5 Water temperature
- **[REQUIREMENT]** The mixing valves are set by hand to a fixed temperature, currently 30 °C.
- **[REQUIREMENT]** The integration neither reads nor changes the buffer or the heat pump. Modulating the buffer temperature is dropped.
- **[REQUIREMENT]** The water temperature is one global setting.

### 2.6 Repository
- **[REQUIREMENT]** The solution is built from scratch. Existing projects serve as references.
- **[REQUIREMENT]** Everything in the repository is written in English.

### 2.7 Cold rooms
- **[REQUIREMENT]** A room may have been off for days, leaving its floor and walls cold. The controller must handle that recovery.

### 2.8 First real test
- **[REQUIREMENT]** The goal is a real test on one closed basement room with little outside influence, at a target of 21 °C.

---

## 3. Installation

| Element | Known | Consequence or open item |
|---|---|---|
| Home Assistant | HA OS on Home Assistant Yellow (Raspberry Pi CM5, 16 GB RAM), 250 GB NVMe | Plenty of capacity. The control core still stays dependency-free. |
| Thermostats | Meross MTS200, one per room, Wi-Fi, local control through the Meross LAN custom integration | See section 3.1. **[TODO]** room list, `climate` entities, targets. |
| Valve actuators | Driven directly by the thermostat relay | Wax actuators that tolerate frequent movement and take 2 to 3 minutes to move, according to the owner. Not measured. |
| Heat pump | Samsung EHS Mono, 12 kW | Not used by the integration. See section 3.2. |
| Buffer and mixing valves | About 200 L buffer, one three-way mixing valve per floor, fixed at 30 °C | The value is a global setting of the integration (6.6). |
| Manifold pump | Unknown | **[TODO]** behaviour when all loops are closed (bypass, relief valve, pump stop). |
| Floors | No floor sensors | The temperature set on the mixing valves is what protects the floor. |
| Outdoor temperature | Sonoff SNZB-02P over Zigbee, placed in the shade | Primary outdoor reading, one for all rooms. Weak link margin (about -89 dBm) and 42% battery seen, so a fallback is required. |
| Weather | AccuWeather integration | Hourly forecast with cloud coverage. |
| PV installation | Inverter read locally in Home Assistant | Its power is the sun signal (6.5), one for all rooms. Never required. |
| History | **[TODO]** recorder retention | Learning needs at least 14 days of data. Extend retention now. |

### 3.1 MTS200 through Meross LAN (checked in the integration source)
- `hvac_action` reflects the device's active state (`state` in the payload), so actual heating is observable.
- Temperature is reported in tenths of a degree. The setpoint step is 0.5 °C. The device reports its own `min` and `max`, typically 5 and 35 °C.
- `climate.set_temperature` forces manual mode by default.
- Reads are polled, every 30 seconds by default.
- The integration updates its stored target optimistically before the reply arrives, so a setpoint read straight after a write proves nothing. The watchdog must confirm through a later read and `hvac_action`.
- The overheat protection relies on an external sensor. Without one it cannot be counted on, so it gives no floor protection here.
- A `Lock` entity, a window-open binary sensor and a tracked-sensor option exist. Their behaviour is still to be verified.
- How the device stores setpoints in flash, and the resulting wear, could not be determined. Write counts will be logged.

### 3.2 Samsung EHS

The integration does not use the heat pump. What was found before this decision, for the record:

- The current temperature of its SmartThings climate entity is the water leaving the pump, not the buffer. No source was found showing that the EHS exposes a buffer temperature. The standard sensor kit lists sensors for the hot water tank and a mixing valve.
- SmartThings is a cloud service. On one observed day the heat pump entities were unavailable for over three hours.

---

## 4. Prior art

No project combines per-room duty cycling on plain thermostats, per-room learning and solar prediction. Parts exist in several projects. Both projects below are MIT licensed, so any reused code must keep the attribution.

### 4.1 lnagel/hass-ufh-controller (read: documentation and source)
Built specifically for water-based underfloor heating.

Adopted as a reference:
- 60 second loop, PID with `kp = 50`, `ki = 0.001`, `kd = 0`, integral clamping.
- 10 minute exponential smoothing of temperature.
- Valve position estimated from travel time, with flow confirmed at 85% position.
- Per-zone fault isolation and status model.
- Pausing integration while a window is open.
- Simulation tests running the real controller with no Home Assistant dependency.

Not adopted:
- Time windows aligned to midnight, where every zone with remaining quota opens at the start of the window. In the simulations here, starting zones together gave worse comfort.
- A single-node room model in simulations, which hides the screed delay.
- It needs a `switch` per valve rather than a `climate` entity.

### 4.2 snazzybean/roommind (read: documentation and source)
A general per-room MPC with online learning.

Adopted as a reference:
- Solar model without dependencies: solar position, clear-sky irradiance, Kasten-Czeplak cloud attenuation (`1 - 0.75 * n^3.4`), facade orientation.
- Normalised parameters for identifiability.
- Using a learned model only once it is calibrated, with a simpler controller as fallback.
- Handing the target back to the thermostat when the integration stops controlling it.
- Periodic valve exercise, every 7 days by default.
- Tagging its own service calls with a context, to tell them apart from user actions.
- Keeping setpoints one step below `max_temp`, because some integrations reject the exact maximum.
- Re-syncing model temperature after gaps before learning resumes.
- Outdoor sensor watchdog, and a diagnostics download.

Not adopted:
- A first-order room model with a fixed residual-heat time constant (90 minutes for underfloor). Issue reports show it struggling with screed behaviour: residual heat attributed to the sun (#35), unstable time constants (#115), learning from a thermostat acting on its own (#36).
- Full MPC. A much simpler feed-forward did as well in simulation, though the MPC tested was a simplified one, not RoomMind's optimizer.
- Shading control and other features outside the current scope. Shading may be worth revisiting for strongly sunlit rooms.

Lessons from its issue tracker: thermostats may ignore `hvac_mode: off` and remain stuck on high setpoints (#134, #160), which motivates setpoint-only control with a watchdog.

### 4.3 Others
- jmcollin78/versatile_thermostat: TPI without an integral term, and it does not work in `over_climate` mode.
- ScratMan/smart-thermostat-pid, vindaalex/multizone-thermostat, domectrl/ha-slow_pwm: older PID and slow PWM projects.

---

## 5. Key findings

1. **Duty cycling solves most of the problem.** The screed acts as a low-pass filter. In a constant-conditions simulation the mean screed temperature swings about 1.0 K with a 90 minute cycle, against about 3.8 K with the thermostat.
2. **Floor temperature is not needed for control.** Results without it were nearly the same as with it, even with a fixed estimate (table 8.1).
3. **A physical two-node model cannot be identified from air temperature alone.** Fitted floor parameters were off by up to a factor of ten, although short-term predictions of air temperature were good. A daily heat balance recovers the useful quantities far more reliably.
4. **Learning belongs in small, explainable layers.** Data per room is limited to weeks, and a neural network offers little here.
5. **A low, fixed water temperature fits the goal.** Stable water gave very even control and long open times in simulation. The limit is demand: rooms with high losses cannot reach the target in cold weather (8.7).
6. **Short cycles cost writes.** An early simulation saw no visible benefit from a 20/20 minute cycle, at 72 writes per day against 32 at 50% duty. Later runs with the implemented controller did show one (8.8), and the owner chose a 30 minute window for smoother modulation.
7. **Absolute results depend heavily on assumptions.** Solar overshoot at 1 kW was +1.8 °C in one model and +0.44 °C in another. The ranking of the variants was more stable than the numbers.

---

## 6. Architecture [PROPOSAL]

### 6.1 Control law

For each room:

```
L     = k1 * (T_target - T_outdoor) - sun[hour] - gains[hour]
duty  = (L + pid_correction) / (T_water - T_room - k3 * L_filtered)
```

- `L` is the heat a room needs, expressed in kelvin of water-to-floor temperature difference.
- `k1` relates room losses to loop power. `k3` is how much warmer than the air the floor must be per unit of `L`. Both are learned.
- `sun[hour]` and `gains[hour]` are learned hourly profiles.
- In `duty`, `L` uses the outdoor temperature forecast 2 hours ahead. `L_filtered` uses current values with a 3 hour low-pass filter, standing in for the unknown floor temperature.

Worked example with `k1 = 0.27`, `k3 = 0.94`, target 21 °C, 3 °C outdoors: `L = 4.8` and `k3 * L = 4.5`. At a water temperature of 34 °C the loop is open 56% of the time. At 30 °C it would need 107%, so this assumed room would stay fully open and fall slightly short of the target.

### 6.2 Layers

| Layer | Purpose | Rate |
|---|---|---|
| L0 Valve | Opens and closes the loop through the setpoint, with a watchdog | writes on change, checks every 5 min |
| L1 Zone | PID, duty calculation, cycle scheduling across zones | 60 s |
| L2 Prediction | Solar feed-forward from PV, the outdoor correction from the local sensor, and feed-forward from the forecast (planned) | 60 s, 30 min for the forecast |
| Learning | Refits per-room parameters, such as the solar profile | nightly |

### 6.3 L0: valve

- ON setpoint is target + 3 °C, OFF setpoint is target - 3 °C. Extreme setpoints such as 30 °C and 5 °C are not used.
- The band must exceed the thermostat's own dead zone by about 0.5 °C, or the ON setpoint does not switch the relay while the room is near the target. Meross LAN exposes this dead zone as a number entity, with limits reported by the device. All thermostats in the pilot house are set to 0.3 °C, which is the differential assumed here, so a ±2 °C band would also switch them and ±3 °C leaves margin. Simulated with the relay switching on at setpoint minus dead zone: up to 1 °C the band makes no difference. At 2.5 °C a ±2 °C band keeps the room within ±0.3 °C only 7-20% of the time, against 100% for ±3 °C. At 3.5 °C a ±3 °C band fails the same way. How the real device applies its dead zone has not been measured.
- With a 0.3 °C differential the controller decides as long as the room stays within about target ±2.7 °C. Outside that range the thermostat takes over, which is intended: it closes on overheating and opens on cooling.
- If Home Assistant stops, the thermostat holds its last setpoint, so the room slowly moves toward target ±3 °C without any software running. A wider band costs nothing in normal operation, and this is its price: in a simulated two-day outage the lowest temperature fell by 1 °C compared with a ±2 °C band, from about 18.7 °C to 17.7 °C at a target of 21 °C.
- Setpoints are clamped to the device range, one step below `max_temp`.
- Control uses the setpoint only. `hvac_mode` stays on `heat`, in manual mode, with no device schedule.
- Commands are tagged with a context so that user changes can be recognised.
- The watchdog compares the commanded state with later reads and `hvac_action`, retries, and raises an alert after 3 consecutive mismatches. The commanded state is stored by the controller, separately from what is read back.
- Wall display and manual changes: the display shows the setpoint alternating around the target. For now the watchdog overwrites a manual change on the wall. Proposed handling: treat it as shifting the target by the same difference. **[TODO]** decide, or use the `Lock` entity.

### 6.4 L1: zone

- PID in normalised power units, so that the duty scales correctly with the water temperature. Integration pauses at saturation, while a window is open, without valid data, and when the thermostat acts outside the L0 band.
- Until `k3` is learned, the floor is assumed to be 3 K warmer than the air when scaling for the water temperature.
- Integration runs four times faster while the error exceeds 0.3 K. Without this, a room recovering from a cold start crawls over the last degree for many hours, because the integral starts near zero. No initial estimate of the room's demand is needed. The integral is kept across restarts, so a room that was switched off recovers faster.
- Cycle length: 30 minutes at any duty, never a pulse shorter than 5 minutes.
- The 5 minutes leave an actuator, which takes 2 to 3 minutes to move, time to pass water. The minimum stays although the actuators tolerate frequent movement, because a shorter pulse would pass little or none.
- On-time that is too short to run is carried over to the next cycle, so a very low duty skips cycles and a very high one closes only now and then. Low and high duties therefore no longer stretch the cycle. Demand is only looked at when a cycle starts, and a stretched cycle of up to 3 hours left a real room cooling behind a closed valve until the duty reached 100%, down to 0.6 °C below its target.
- Zones are staggered in phase, so the load stays even and the loops do not all close at once. Zones are not run strictly in sequence, since heating several at once is better for the source.

### 6.5 L2: prediction

- Implemented: a learned outdoor correction. Each room adds `weight * (usual - now)` to the controller output, in the same percent as the integral, where `usual` is the outdoor temperature averaged over about a day and `now` is the reading smoothed over 15 minutes. The integral keeps the demand at the usual temperature, and the correction follows the swings around it: the night, the afternoon, a front. The weight learns while the room is active and the integral could move, but only while the share of full sun is below 10%, because the sun warms the air outside and the room at the same time. It moves by `0.01 * error * (usual - now)` per hour and stays between 0 and 5, so colder weather never means less heat, and a basement room that hardly feels the weather learns a small weight. The correction acts after a day of readings, and stops after 2 hours without one.
- Outdoor temperature comes from the local sensor. A forecast would contribute only its change: `T_out(+2 h) = sensor(now) + forecast(+2 h) - forecast(now)`. This is planned. The forecast and the sensor differ (6.8 °C against 4.2 °C on one observed day), and a constant ±2.6 K error did not change the simulated result.
- The solar signal is the power of a PV installation read locally, as a share of full sun. Full sun is the highest power seen, fading with a 30 day half-life, so that the lower sun of another season reaches full sun again. PV shows the sun as it shines, often before the room does: in the pilot house in November the panels saw the sun from about 07:30, and the main room's reading jumped at about 09:20. When the sun reaches the panels and each room's windows is learned per room, hour by hour (6.7). Snow on the panels reads as no sun, so the room then runs as it would without PV.
- The hourly cloud forecast through the Kasten-Czeplak attenuation would warn earlier, before sunrise. It is planned, with scaling by clear-sky irradiance for seasonal change, and not yet implemented.

### 6.6 Water temperature

- One global value for all rooms, by default 30 °C, in the range 20-38 °C. It may change over time, so it is set on the sidebar page or with the service `what_the_heat.set_water_temperature`, and must match the mixing valves.
- It only tells the controller what the temperature is. Nothing is read from or written to the mixing valves, the buffer or the heat pump.
- It scales the duty, since hotter water delivers the same heat in less time.
- A room that needs more than the water can deliver stays fully open and below its target. Raising the temperature is then a manual step.
- Buffer control was designed and simulated first (8.4), and dropped once the owner chose fixed mixing valves.

### 6.7 Learning

Three layers per room, updated nightly from that room's own data. Before enough data exists, the room runs on PID alone.

**Daily balance: `k1`, `k3` (and a starting value for the sun).** One row per day: fraction of time heating (from `hvac_action`), room temperature, outdoor temperature, water temperature, sun estimate. The fit uses a rolling 30 day window:

```
L    = k1 * (T_room - T_outdoor) - k2 * sun
duty = L / (T_water - T_room - k3 * L)
```

New values are blended in (85% old, 15% new). No deliberate cooling of rooms is needed, so step tests are optional.

**Solar profile: 24 values, implemented with PV.** After each day, each hourly value moves by `rate * gain * share * deviation`: the mean share of full sun in that hour, times the room's mean deviation from its target 2 hours later, with a rate of 0.25 and a gain of 80 %/K like the proportional gain. The profile is then smoothed, each hour taking 0.2 of each neighbour, and kept between 0 and 100, in the controller's percent like the integral. It learns only in active mode. Once it has learned from 3 sunny days, meaning days with at least 2 hours' worth of full sun, it subtracts `value[hour] * share now` from the controller output, so that the valve opens less while the sun shines, and never more. The hours are solar time, from UTC and the longitude set in Home Assistant, so the profile stays with the sun when the clocks change, and the solar day starts at solar midnight. Each value stands for the middle of its hour, and the moments in between take from both neighbours, so the correction does not jump at the full hour. Window orientation does not have to be configured. In an earlier simulation that weighted the deviation by the forecast clearness instead of PV, the peak correction emerged by itself: 8:00 for an east room, 10:00 for a south room, 13:00 for a west room.

**Recurring gains: 24 values.** The same rule, weighted towards cloudy days, with the mean removed and values limited. This captures things like cooking.

**Safeguards.** Parameters are bounded. The daily balance becomes active only after at least 14 days of data and a daily balance error below about 5 percentage points. The solar profile acts sooner, after 3 sunny days, because it can only lower the heating, is bounded, and learns back when the room ends up below its target. A room falls back to PID if it performs worse with learning than without it over a recent window (this safeguard is not yet simulated). Learned values are visible in diagnostics, and learning can be switched off per room. Learning skips periods with open windows and re-syncs after data gaps. It also skips days when a room is recovering from a cold start, because heat going into a cold floor and cold walls says nothing about steady losses.

### 6.8 Failure handling

| Failure | Behaviour |
|---|---|
| Home Assistant down | Thermostats keep the room within about target ±3 °C. |
| Integration unloaded or crashed | Thermostats get the plain target as setpoint and regulate on their own (hand-back). Heartbeat entity for monitoring. |
| Thermostat unavailable | Zone reports unavailable instead of a false "off", and integration pauses. Other zones are unaffected. |
| Room temperature stale | After 30 min the last duty is held. After 60 min the zone is handed back to the thermostat. |
| Outdoor sensor lost | The outdoor correction stops after 2 h without a reading, and the room runs on the integral alone. A fallback to AccuWeather with the last known offset is planned. |
| Forecast lost | Current outdoor temperature is used, and solar feed-forward is disabled. |
| Model not trusted | PID only. |

Valve exercise: any loop idle for 7 days is opened for 15 minutes. The 15 seconds used by RoomMind is too short for thermal actuators.

### 6.9 Integration and repository

Each room is one configuration entry. The outdoor and PV sensors are shared by all rooms and rarely change, so they are kept in one more entry, **Shared settings**, which the first setup of the integration asks for and Configure changes later. Without it the rooms use no sensors. Its title starts with a gear, so that it sorts above the rooms. The water temperature is shared too, but may change over time, so it is set on the sidebar page (6.6). The integration exposes the target, duty, PID terms, sun and outdoor corrections, valve state, status and daily comfort metrics as entities, plus a diagnostics download with one row per day. Each room also has a thermostat entity for dashboards, with the modes as presets. A sidebar page shows all rooms as tiles, using plain JavaScript with no build step. It changes the targets and the water temperature, and nothing else. Each zone has a mode: `active` (the default for a new room), `observe` (calculates and logs only), or `handback`, set with its Mode entity.

On switching from `observe` to `active`, the integral starts from how much the thermostat has recently been heating, but only if the room is near its target. Otherwise it starts from zero.

Until the learning of 6.7 exists, what a room has learned is its steady demand. The `Learned demand` sensor and the sidebar page show it as the valve opening needed at the current water temperature, once at least 6 hours of data are behind it. While `active` it comes from the integral, and only time when the integral could move counts as data, so a cold room warming at full duty learns nothing. Otherwise it comes from the heating share of the thermostat, if the room is near its target. A `Reset learning` button on the device page clears the integral, the carried on-time, the heating share, the solar profile, the outdoor weight and the data counters. It keeps the mode, the target, the counters of writes and the daily rows, which are measurements and not learned. In simulation a reset of a settled room at 34 °C or 38 °C water lowered the minimum by 0.4 to 1.6 °C, and cost 3 to 15 extra hours outside ±0.3 °C in most rooms. The worst cases were a room with high losses at 34 °C with 31 hours, and a room with heavy air at 30 °C with 60 hours.

```
custom_components/what_the_heat/
  core/          pure Python, no Home Assistant imports
                 (pid, cycle, valve, zone, runner, daily, sun)
  frontend/      sidebar page
  ...            thin Home Assistant layer
tests/           core tests, no dependencies
  simulation/    three-node rooms, actuators, faults
tests_ha/        integration tests on a real Home Assistant core
docs/
```

---

## 7. Starting parameters

| Parameter | Value | Source |
|---|---|---|
| Control loop | 60 s | hass-ufh-controller |
| Temperature smoothing | 10 min | hass-ufh-controller |
| `kp` | 80 %/K | pilot simulation (hass-ufh-controller: 50) |
| `ki` | 0.0005 %/(K·s), i.e. 1.8% per K·h | pilot simulation (hass-ufh-controller: 0.001) |
| Faster integration | 4 times, while the error exceeds 0.3 K | pilot simulation |
| Cycle length | 30 min | owner, compared in simulation (8.8) |
| Minimum open and closed time | 5 min | actuator travel plus time to pass water |
| Actuator travel | 2-3 min, not measured | owner |
| Setpoint band | target ±3 °C | this project, wider than the thermostat's dead zone |
| Outdoor lead | 2 h | simulation |
| Floor offset filter | 3 h | simulation |
| Water temperature | 30 °C, one global value | owner |
| Learning window | 30 days, minimum 14 days | simulation |
| Full sun | Highest PV power seen, half-life 30 days | this project |
| Solar profile | Rate 0.25 and gain 80 %/K per day, deviation lag 2 h, smoothing 0.2, values 0-100 | simulation (8.9), lag as seen in the pilot house |
| Solar profile acts after | 3 sunny days, each with at least 2 hours' worth of full sun | this project |
| Solar profile hours | Solar time from the longitude, values at the middle of each hour, interpolated | this project |
| Outdoor correction | Usual temperature over 24 h, reading smoothed 15 min, rate 0.01 per K² and hour, weight 0-5 %/K, learns below 10% sun, acts after a day, stops after 2 h without readings | simulation (8.10) |
| Gains learning rate | 1 per day, deviation lag 2 h | simulation |
| Model trust threshold | daily balance error under about 5 points | proposal, unverified |
| Watchdog | every 5 min, alert after 3 mismatches | hass-ufh-controller, this project |
| Valve exercise | 7 days, 15 min | RoomMind (interval) |

---

## 8. Simulation evidence

Common assumptions: a 20 m² reference room scaled by area, three thermal nodes (screed, air, wall mass) with 60% of solar gain landing on the floor, screed 0.65 kWh/K, actuators 3.5 minutes with flow at 85% position, sensor resolution 0.1 °C. The controller sees room air temperature, water temperature, valve state and forecasts. The controller and the fits assume a simpler model than the plant. Results vary by several points between runs. The complete system (learning and several rooms on one heat source) has not yet been simulated as one. Unless stated otherwise, the results below predate the ±3 °C band, the 30 minute window, the 5 minute minimum and the 2.5 minute actuators, and were not recomputed.

### 8.1 Floor temperature is not needed

Fixed 36 °C water, outdoor 3 ±3 °C, sun every other day. Time within ±0.3 °C and temperature range:

| Sun | Thermostat | PID only | Without floor temperature | With floor temperature (reference) |
|---|---|---|---|---|
| None | 60%, 20.57-21.48 | 100%, 20.75-21.24 | 100%, 20.88-21.11 | 100%, 20.88-21.10 |
| 400 W | 57%, 20.57-21.67 | 92%, 20.70-21.67 | 98%, 20.55-21.15 | 100%, 20.70-21.15 |
| 1000 W | 55%, 20.57-22.60 | 87%, 20.72-22.61 | 90%, 20.45-21.44 | 92%, 20.44-21.43 |

### 8.2 Identification from air temperature

True equivalent values: `k1` = 0.248, `k3` = 0.94, `k2` about 3.33. Three random weather sequences.

| Method | `k1` | `k3` | `k2` | Closed loop within ±0.3 °C |
|---|---|---|---|---|
| Daily balance, 14-42 days | 0.227-0.265 | 0.78-1.23 | 1.58-3.08 | 93-99% |
| Two-node fit, passive data | 0.123-0.307 | 0.21-2.45 | 1.51-3.88 | 94-96% |
| Two-node fit with step tests | 0.180-0.269 | 0.43-1.30 | 2.32-3.48 | 95-99% |

For comparison, ideal parameters gave 96% and PID alone 91%. Two-node floor parameters were far from their true values (`aw` 0.5-4.4 against 0.23).

### 8.3 Learning under its own control

70 days, variable weather, heat pump on a curve with DHW breaks, 5 rooms of differing orientation, one with 350 W of evening gains. Days 42-70, mean over rooms, two weather sequences:

| Variant | Within ±0.3 °C | RMS deviation |
|---|---|---|
| Thermostat | 64% | 0.28 °C |
| PID only | 90% | 0.20 °C |
| + daily balance | 92-93% | 0.18 °C |
| + solar profile | 93% | 0.16 °C |
| + recurring gains | 94% | 0.14 °C |

These runs used a learning rate of 1. A rate of 2 did better in the two rooms tested: 97% for the south room and 83% for the kitchen, against 95% and 78%. East, west and north rooms reached about 99%.

The water temperature matters when it varies. With steps of ±3 K, learning that knows the temperature reached 96.5%, and without it 79%. This is why the global setting must match the mixing valves.

### 8.4 Buffer control (dropped)

Kept for the record, since this design was replaced by fixed mixing valves. Six zones with differing demand, 100 L buffer, sun on some zones, DHW twice a day. Values are for: stable 5 °C / cold front / -5 °C / thaw 8 °C.

| Control | Buffer (°C) | Within ±0.3 °C | Mean open | Most demanding zone open | Starts per day |
|---|---|---|---|---|---|
| Fixed 40 °C | 40 / 40 / 40 / 40 | 96 / 90 / 88 / 94% | 25 / 47 / 51 / 20% | 35 / 67 / 74 / 27% | 19 / 15 / 6 / 22 |
| Fixed 35 °C | 35 / 35 / 35 / 35 | 92 / 72 / 63 / 96% | 38 / 70 / 75 / 30% | 54 / 98 / 100 / 42% | 13 / 5 / 3 / 17 |
| Reactive 75-85% | 34 / 37 / 41 / 32 | 95 / 88 / 90 / 97% | 44 / 61 / 49 / 39% | 64 / 88 / 69 / 55% | 15 / 6 / 14 / 15 |
| Reactive 85-95% | 32 / 35 / 39 / 31 | 91 / 72 / 91 / 94% | 52 / 69 / 57 / 46% | 76 / 96 / 83 / 67% | 14 / 3 / 6 / 16 |
| Reactive 90-100% | 30 / 30 / 30 / 28 | 77 / 26 / 16 / 79% | 68 / 94 / 98 / 70% | 98 / 100 / 100 / 98% | 10 / 3 / 2 / 16 |
| Model, target 100% | 31 / 37 / 38 / 29 | 96 / 94 / 96 / 97% | 59 / 61 / 58 / 61% | 87 / 89 / 85 / 91% | 15 / 10 / 11 / 16 |
| Same, balanced manifold | 32 / 37 / 39 / 29 | 96 / 88 / 94 / 97% | 68 / 72 / 68 / 73% | 83 / 86 / 81 / 89% | 8 / 4 / 4 / 10 |

Notes:
- Fixed 35 °C dropped to 19.3 °C during frost. Reactive 90-100% dropped to 16.3 °C.
- A 9 K lower buffer at 5 °C suggests roughly 18-26% less energy using the rule of thumb of 2-3% per kelvin. At -5 °C the gain is only about 2 K.
- With model errors of ±25% in `k1`, stable periods stayed at 94-97%, and the cold front fell to 81-93%.
- Compressor starts depend most on the heat pump's minimum power and on the buffer volume. In related runs a 1500 W minimum gave 6 starts per day at 5 °C and 3500 W gave 22. A 50 L buffer gave 17 and a 300 L buffer gave 4.

### 8.5 Manifold balancing

This ran with the buffer control above, but the principle does not depend on it. Reducing flow in low-demand loops evens out opening times: with an open target of 90%, zone opening ranged 27-66% before and 49-68% after, and at a target of 100% it ranged 56-83%. Starts also fall. The controller can recommend flow changes from learned `k1` values. Adjusting the manifold remains a manual step.

### 8.6 Pilot room

This uses the simulator in this repository, with the implemented controller: PID and cycles only, no prediction or learning. Run it with `python -m tests.simulation.pilot`. The results cover seven assumed room types at a water temperature of 30, 34 or 38 °C with a 21 °C target, with the wall losing heat to the ground. One physically impossible case (high losses at 30 °C) is left out, where both variants stop at 19.6 °C. The thermostat is modelled as switching on at setpoint - 0.3 °C and off at the setpoint, which is an assumption about the real device.

| Steady state | Thermostat | Controller |
|---|---|---|
| Within ±0.3 °C | 37-88% | 97-100% |
| RMS deviation | 0.19-0.44 °C | 0.04-0.21 °C |
| Longest closed period | 1.1-5.6 h | 0.6-1.8 h |
| Simulated floor swing | 1.5-4.2 K | 0.9-2.4 K |
| Setpoint writes per day | 0 | up to 32 |

Cold start, with the floor at air temperature, walls 1 K colder, and air at 13, 16 or 19 °C:
- Peak above the target: at most +0.52 °C, close to the thermostat's +0.45 °C.
- Time to come within 0.3 °C of the target: usually the same as the thermostat, since the valve is simply open during most of the recovery. The widest gap was 30 h against 12 h, with high losses at 34 °C.
- Afterwards the room stays within the band at least 99% of the time, except for a room with heavy air at 30 °C water, at 79-83%.

Real basement walls and soil are likely to warm much more slowly than this model, so the first days in a real room will not be representative.

Error in the configured water temperature, over the same room types. At a real 34 or 38 °C and an error within ±2 K, the worst room stayed within the band 92-100% of the time. At ±4 K half of the rooms were still at 100%, but the worst fell to 51-95%. At ±6 K the worst fell to 22-71%. At a real 30 °C, where some rooms are near their limit, ±2 K already took the worst room to 67-72%.

### 8.7 Fixed 30 °C water

Stable water, 21 °C target, wall losing heat to the ground. Time within ±0.3 °C and mean duty, by outdoor temperature:

| Room type | 8 °C | 3 °C | -5 °C | -10 °C |
|---|---|---|---|---|
| Reference | 100%, 46% | 100%, 60% | 100%, 82% | 100%, 96% |
| Low losses | 100%, 18% | 100%, 22% | 100%, 29% | 100%, 34% |
| High losses | 0%, stops at 20.1-20.7 °C | 0%, stops at 19.0-19.7 °C | 0%, stops at 17.4-18.0 °C | 0%, stops at 16.4-17.0 °C |
| Cold ground | 100%, 62% | 100%, 77% | 99%, 97% | 0%, stops at 20.2-20.5 °C |
| Slow floor | 100%, 57% | 100%, 76% | 27%, 100% | 0%, stops at 19.7-20.0 °C |
| Light room | 100%, 41% | 100%, 54% | 100%, 79% | 100%, 93% |
| Heavy air | 100%, 60% | 84%, 86% | 0%, stops at 19.0-19.8 °C | 0%, stops at 17.7-18.5 °C |

Where it holds, stable water keeps most of these rooms within about ±0.15 °C. Where it does not, the water simply cannot deliver enough heat, and no control can change that. The real limit of each room still has to be measured.

### 8.8 Window length

Compared on the simulator with the implemented controller and 2.5 minute actuators, for five room types at a 21 °C target: water at 34 °C with outdoor means of 15, 3 and -8 °C, and water at 30 °C with 3 °C. The first column is the earlier setting.

| | 90 min window, 12 min minimum | 30 min window, 5 min minimum |
|---|---|---|
| RMS deviation | 0.04-0.13 °C | 0.03-0.12 °C |
| Longest closed period | up to 7.0 h, in mild weather | up to 1.8 h |
| Setpoint writes per day | up to 32 | up to 96 |

These ranges leave out a room with heavy air near its limit, at about 90% duty, where the window made little difference to the RMS deviation: 0.30 against 0.28 °C at 34 °C water and -8 °C, and 0.21 against 0.22 °C at 30 °C water and 3 °C. In that second case the time within ±0.3 °C fell from 100% to 76%. A 3 minute minimum gave nearly the same results as 5 minutes.

A rough figure for a real room: on a plain thermostat, the reading of one room moved about 0.6 K/h in both directions and reacted within about 10 to 20 minutes. At 50% duty that suggests a swing of about 0.15 K with this window, against about 0.45 K with 90 minutes. This comes from the slope and has not been measured under the controller.

The first real night with this window, in that room at 30 °C water: from 03:30 to 09:06 the reading stayed within 22.7-23.0 °C at a 23 °C target, with a mean of 22.84 °C and the valve open 51% of the time. On a plain thermostat, on a day without sun and at an unknown water temperature, it moved within 22.7-23.3 °C. The mean was still low because the integral was catching up.

Cycles stretched at extreme duties were compared with a fixed 30 minutes, on five room types with a daily sun peak of 800 or 1500 W at 34 °C water, and 800 W at 30 °C. The lowest temperature after the sun rose in most cases, for example from 20.45 to 20.87 °C and from 20.07 to 20.69 °C at a 21 °C target. Without sun the results stayed about the same, with fewer writes in mild weather. The table above comes from before the cycle was fixed, so it still shows the stretched variant.

### 8.9 Solar profile from PV

Run it with `python -m tests.simulation.sun`. Five room types (reference, low losses, slow floor, light room, heavy air) at a 21 °C target, water at 30 or 34 °C, outdoor mean -1 °C, and sun through the windows peaking at 800 or 1500 W. Each run lasts 3 weeks, of which the last 2 are measured. The days repeat a week of full sun with one day at 30% and one at 60%. The panels see the sun from 07:30 to 15:30 and the windows from 09:20 to 16:20, shaped on the pilot house in November. Means over the 20 cases:

| | Plain thermostat | Controller without PV | Controller with the solar profile |
|---|---|---|---|
| Within ±0.3 °C | 44% | 57% | 65% |
| RMS deviation | 0.83 °C | 0.93 °C | 0.74 °C |
| Highest | 23.14 °C | 23.33 °C | 22.98 °C |
| Lowest | 20.46 °C | 20.64 °C | 20.65 °C |
| Above the band | 7.3 K·h a day | 9.1 K·h a day | 6.5 K·h a day |
| Below the band | 1.6 K·h a day | 1.2 K·h a day | 0.9 K·h a day |

- Without PV the controller overheats sunny rooms more than the plain thermostat, which lets the floor cool further between its long cycles.
- With full sun every day, the profile closes the valve earlier in the morning. The lowest temperature then fell by up to 0.2 °C, with almost no time below the band.
- In rooms the sun does not reach while the panels see it, the profile changed nothing worth noting: RMS 0.130 against 0.143 °C.
- Not lowering the integral while the sun had recently shone, so that a sun-warmed room would not lower its steady demand, made no difference (RMS 0.740 against 0.732 °C) and was left out.
- Before the hours were interpolated, a rate of 0.5 or a lag of 3 hours did slightly better than the chosen 0.25 and 2 hours, at an RMS of 0.71-0.72 against 0.73 °C, and a rate of 0.1 or a lag of 1 hour slightly worse, at 0.76-0.78 °C. Without smoothing, or with values limited to 50, the RMS was 0.76-0.78 °C. The settings stay on the cautious side and on the lag seen in the pilot house.
- The model does not include sun falling on the thermostat itself, which the pilot house showed.

### 8.10 Outdoor correction

Run it with `python -m tests.simulation.outdoor`. All seven room types of 8.6 at a 21 °C target, water at 34 or 38 °C, outdoor mean 0 °C with a daily swing of ±5 K, shaped on the pilot house in November. Each run lasts 4 weeks, of which the last 2 are measured. "Fronts" repeat a week whose daily mean moves between -6 and +3 K. In the model only the air loses heat to the outdoor air, and the walls to the ground. Means over the 14 cases:

| Scenario | Without the correction | With it |
|---|---|---|
| Fronts, no sun | 91.3% within ±0.3 °C, RMS 0.169 °C | 94.2%, 0.138 °C |
| Steady weather, no sun | 95.0%, 0.130 °C | 96.1%, 0.103 °C |
| Fronts, sun up to 1000 W, with the solar profile | 70.3%, 0.522 °C | 72.3%, 0.514 °C |

- The largest gain was a room with high losses at 38 °C water under fronts, from 80% to 93% within the band.
- In sunny weather the sun dominates, and the correction changes little.
- Smoothing the reading over 15 minutes did slightly better than over 1 or 3 hours, a rate of 0.03 about the same as 0.01, 0.003 slightly worse, and a usual temperature over 12 or 48 hours about the same as 24.

---

## 9. Roadmap

| Stage | Scope | Done when |
|---|---|---|
| 0 Preparation | Extend recorder retention, start a baseline in the pilot room | Retention extended |
| 1 Core and simulator | Pure Python core and simulator with failure injection | Done for the pilot scope: PID, cycles, valve, watchdog, zone |
| 2 Integration | Home Assistant layer with `observe`, `active` and `handback` modes, and daily rows logged | Built and tested against a stand-in thermostat. Calculated duty still has to be checked next to the real thermostat. |
| 3 Pilot | One room live, see 9.1 | Criteria in 9.1 met |
| 4 Learning and prediction | Learning and feed-forward, first in the simulator, then on the pilot room. The solar profile from PV is built. | Smaller RMS deviation than PID alone |
| 5 All rooms | All zones, phase staggering, manifold recommendations | One stable week |
| Later, optional | Shading, online EKF, MPC | Justified by data |

### 9.1 Pilot

A real test on one closed basement room, chosen for its small outside influence, at a target of 21 °C. The steps are in the [pilot test guide](pilot-test.md).

- Only PID and cycles run. There is no prediction, and only the steady demand is learned, but daily rows are logged from the first day.
- The mixing valves stay at a constant temperature during comparisons, with the same value in the global setting. Other rooms remain on their own thermostats.
- Sequence: a plain thermostat baseline at 21 °C, then `observe` mode, then `active` mode. The first days after a cold room starts warming are not used for comparison. Cold start can be tested later by switching the room off for a few days.
- Measured: time within ±0.3 °C, RMS deviation, longest closed period, setpoint writes per day, watchdog events, and whether the relay follows commands.
- Also to learn from it: real actuator travel, command latency, and how the thermostat switches around its setpoint.
- Done when: smaller deviation than the baseline, no setpoint stuck for more than 10 minutes over 7 days, and a tested Home Assistant restart and outage.

---

## 10. Success criteria

All based on what can be measured: air temperature and valve state.

- Deviation from target within ±0.3 °C for at least 90% of the time. **[TODO]** confirm.
- No overheating beyond +0.7 °C on sunny days, to be reassessed on real data since it may need shading in strongly sunlit rooms.
- No valve cycle shorter than the minimum time.
- No setpoint stuck for more than 10 minutes.
- Energy use no higher at equal comfort, compared with a baseline at similar outdoor temperature.
- "The floor is never cold" is checked indirectly, through the longest continuous closed period of each loop. Floor temperature is not measured.

---

## 11. Risks

| Risk | Mitigation |
|---|---|
| Thermostat loses a command | Setpoint-only control, watchdog, alerts |
| Setpoint writes wear out device flash | Long cycles, write logging. Wear is unknown. |
| Floor overheating with no sensor | The temperature set on the mixing valves limits it |
| The water is too cold for a room in cold weather | The room stays fully open and below target. Raise the temperature by hand, on the valves and in the setting. See 8.7. |
| The global setting differs from the real water temperature, or the buffer falls below the mixing setpoint | The integral compensates a steady difference. See 8.6 for the tolerance. |
| Learning degrades a room | Bounds, trust threshold, fallback to PID, per-room switch |
| The outdoor sensor reads the sun, or fails | Placed in the shade. The weight learns only without sun, the correction stops after 2 h without readings, and the integral covers the rest. |
| PV misreads the sun on a room's windows: snow on the panels, or panels facing elsewhere | Snow reads as no sun, so the room runs as without PV. The solar profile only lowers heating, is bounded, and learns back when the room ends up below its target. |
| Frequent setpoint writes wear out a thermostat | About 96 writes a day per room with the 30 minute window. Whether the device stores each one in flash memory, and how long that lasts, is unknown. If it matters, lengthen the window. |
| Integration bug affects Home Assistant, since it runs in-process | Async only, no blocking work, core tested separately |
| Short cycling of the compressor at low load | Phase staggering, longer open times. Partly limited by hardware. |
| All loops closed with the manifold pump running | Stage 0 check, phase staggering |
| Windows or ventilation | Window sensors or detection, integration pause |
| Simulation does not reflect the house | Observation mode, reference room, gradual rollout |

---

## 12. Open questions [TODO]

1. Other rooms: name, `climate` entity, target temperature.
2. Manifold pump behaviour with all loops closed.
3. Actuator type and travel time.
4. Handling of manual changes on the wall thermostat.
5. Window sensors, if any.
6. Target comfort tolerance.
7. Dashboard requirements.
8. Repository license.

---

## 13. Decisions

| Decision | Reason |
|---|---|
| Built from scratch, with existing projects as references | Owner decision |
| Home Assistant custom integration in Python | All layers in one codebase, first-class entities, restore state, existing test tooling |
| Control through thermostat setpoints in a ±3 °C band | Safe when the software is not running, and wide enough to switch a thermostat with a dead zone of up to 2.5 °C |
| No floor temperature anywhere in the control path | No sensors exist, and simulation shows it is not needed |
| Learning through small per-room layers rather than a neural network | Limited data, explainability, safety |
| No reading or control of the buffer or heat pump, and one global water temperature | Owner decision: each floor has a mixing valve fixed at 30 °C |
| PV power, read locally, as the sun signal | It shows the sun as it shines, often hours before a room does, without a cloud service |
| Outdoor and PV sensors shared by all rooms, in a Shared settings entry, and the water temperature on the sidebar page | One house has one outdoor sensor and one PV installation. Owner decision: settings that rarely change belong in the integration's configuration, and the water temperature, which may change over time, on the page. |
| A new room starts in active mode, and the sidebar page has no mode or reset buttons | Owner decision. The modes stay available through each room's Mode entity. |
| The solar profile in solar time | Owner decision: it must not shift when the clocks change. |
| An outdoor correction learned per room, only without sun | It anticipates the night and fronts that the integral would follow late, and a basement room learns that it hardly feels the weather. Learning in the sun would mix the weather up with the sun. |
| First real test on one closed basement room at 21 °C, PID and cycles only | Least outside influence, smallest risk |
| English only in the repository; work goes straight to the default branch | Owner decision |

---

## 14. Sources

- lnagel/hass-ufh-controller: https://github.com/lnagel/hass-ufh-controller
- snazzybean/roommind: https://github.com/snazzybean/roommind
- krahabb/meross_lan: https://github.com/krahabb/meross_lan
- Home Assistant SmartThings integration: https://github.com/home-assistant/core/tree/dev/homeassistant/components/smartthings
- Home Assistant AccuWeather integration: https://github.com/home-assistant/core/tree/dev/homeassistant/components/accuweather
- jmcollin78/versatile_thermostat: https://github.com/jmcollin78/versatile_thermostat
- vindaalex/multizone-thermostat: https://github.com/vindaalex/multizone-thermostat
