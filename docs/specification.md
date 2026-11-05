# what-the-heat: specification

Smart control of water-based underfloor heating in Home Assistant, built from scratch as a custom integration.

Conventions: **[REQUIREMENT]** comes from the owner, **[PROPOSAL]** comes from analysis and may change, **[TODO]** is missing information.

All simulation figures in this document come from throwaway models with assumed room data. They compare design options. They do not predict how a real house behaves, and every threshold must be checked against real data.

---

## 1. Goal

Keep each room at its target temperature with the smallest possible deviation, using a low buffer temperature and loops that stay open for as long as possible.

Today each room runs a plain on/off thermostat with a 0.3 °C differential. That heats the screed in bursts and ignores the large thermal inertia of the floor, the sun and the buffer temperature.

The guiding principle **[REQUIREMENT]**: it is better to lower the buffer temperature and keep a loop open nearly 100% of the time than to hold a high buffer temperature and run rare, short cycles.

---

## 2. Owner requirements

### 2.1 Current state
- **[REQUIREMENT]** Water-based underfloor heating. Every room has a thermostat and every thermostat is connected to Home Assistant.
- **[REQUIREMENT]** A thermostat is normally set to about 21 °C with a 0.3 °C differential.
- **[REQUIREMENT]** The heat source is a heat pump with a buffer. The buffer temperature follows the temperature set on the heat pump, and it can be read and written from Home Assistant.
- **[REQUIREMENT]** There are no floor sensors. Floor temperature is unknown and will stay unknown.

### 2.2 Predictive switching
- **[REQUIREMENT]** Use historical data to determine how the floor behaves in each room.
- **[REQUIREMENT]** When a room temperature gradually falls, open the loop earlier than the thermostat would, by raising the thermostat setpoint from Home Assistant.
- **[REQUIREMENT]** Likewise close the loop earlier, because the floor keeps releasing heat for a long time.
- **[REQUIREMENT]** Take time of day and the sun into account.
- **[REQUIREMENT]** Take the buffer temperature into account.

### 2.3 Loop modulation, like an induction hob (preferred)
- **[REQUIREMENT]** Loops open and close at a frequency chosen by the algorithm, for example 20 minutes open and 20 minutes closed at 35 °C in the buffer.
- **[REQUIREMENT]** The floor is never cold, and heating it from cold is avoided.
- **[REQUIREMENT]** Control still works through thermostat setpoints from Home Assistant.

### 2.4 Learning
- **[REQUIREMENT]** A learning algorithm studies each room individually and adapts the parameters accordingly. The buffer temperature and external factors such as the sun matter.

### 2.5 Buffer control
- **[REQUIREMENT]** The heat pump may run at a fixed temperature, and the algorithm may set that temperature, which equals the buffer temperature.
- **[REQUIREMENT]** To keep things simple, the temperature set on the heat pump is treated as the real buffer temperature.
- **[REQUIREMENT]** The buffer temperature must not exceed 38 °C.

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
| Valve actuators | Driven directly by the thermostat relay | **[TODO]** type and travel time (assumed 3.5 minutes). |
| Heat pump | Samsung EHS Mono, 12 kW, through the SmartThings integration (cloud) | See section 3.2. **[TODO]** minimum modulation power. |
| Buffer | About 200 L | Its set temperature is treated as the real temperature (2.5). |
| Manifold pump | Unknown | **[TODO]** behaviour when all loops are closed (bypass, relief valve, pump stop). |
| Floors | No floor sensors | The 38 °C buffer limit is the only firm protection for the floor. |
| Outdoor temperature | Sonoff SNZB-02P over Zigbee, placed in the shade | Primary outdoor reading. Weak link margin (about -89 dBm) and 42% battery seen, so a fallback is required. |
| Weather | AccuWeather integration | Hourly forecast with cloud coverage. |
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

### 3.2 Samsung EHS through SmartThings (checked in the Home Assistant source and on the device)
- In `auto` mode (expected to be the weather-compensation curve, to be confirmed) the integration does not expose a target temperature. In `heat` mode it does, so buffer control requires `heat` mode. While the pump is in `auto`, the controller works from a configured typical buffer temperature.
- The climate entity's current temperature read 55-58 °C while the diverter valve was on the tank. It is not the buffer temperature. Its meaning while heating the room is **[TODO]**.
- The diverter valve position (`room` or `tank`) shows domestic hot water (DHW) periods, during which the buffer is not charged.
- `Power` and `Energy` sensors allow energy baselines and compressor start detection.
- It is a cloud integration. On the day this was written the heat pump entities were unavailable for over three hours. Nothing critical may depend on it.
- Two earlier automations that acted on the heat pump have been disabled by the owner and no longer affect the setpoint.

---

## 4. Prior art

No project combines per-room duty cycling, buffer temperature derived from zone demand, and solar prediction. Parts exist in several projects. Both projects below are MIT licensed, so any reused code must keep the attribution.

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
- Time windows aligned to midnight, where every zone with remaining quota opens at the start of the window. In the simulations here, starting zones together gave worse comfort and a higher buffer temperature.
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
5. **The buffer should follow the most demanding room.** Compared with a fixed 40 °C it lowers the buffer temperature by up to about 11 K without losing comfort.
6. **Buffer control based only on measured duty is dangerous at high targets.** A reactive rule aiming for 90-100% failed to raise the buffer in a cold spell, and rooms fell to about 16 °C. The buffer must come from a model and a forecast, guarded by room temperatures.
7. **A 20/20 minute cycle brings no visible benefit** over longer cycles, at more than twice the writes: 72 writes per day against 32 at 50% duty.
8. **Absolute results depend heavily on assumptions.** Solar overshoot at 1 kW was +1.8 °C in one model and +0.44 °C in another. The ranking of the variants was more stable than the numbers.

---

## 6. Architecture [PROPOSAL]

### 6.1 Control law

For each room:

```
L          = k1 * (T_target - T_outdoor) - sun[hour] - gains[hour]
buffer     = max over rooms of: T_target + k3 * L + L / open_target
duty       = (L + pid_correction) / (buffer - T_room - k3 * L_filtered)
```

- `L` is the heat a room needs, expressed in kelvin of water-to-floor temperature difference.
- `k1` relates room losses to loop power. `k3` is how much warmer than the air the floor must be per unit of `L`. Both are learned.
- `sun[hour]` and `gains[hour]` are learned hourly profiles.
- In `duty`, `L` uses the outdoor temperature forecast 2 hours ahead. `L_filtered` uses current values with a 3 hour low-pass filter, standing in for the unknown floor temperature.

Worked example with `k1 = 0.27`, `k3 = 0.94`, target 21 °C, 3 °C outdoors: `L = 4.8` and `k3 * L = 4.5`. A 100% open target needs a buffer of 21 + 4.5 + 4.8 = 30.3 °C. At 34 °C the same loop would be open 56% of the time.

### 6.2 Layers

| Layer | Purpose | Rate |
|---|---|---|
| L0 Valve | Opens and closes the loop through the setpoint, with a watchdog | writes on change, checks every 5 min |
| L1 Zone | PID, duty calculation, cycle scheduling across zones | 60 s |
| L2 Prediction | Outdoor and solar feed-forward from the forecast | 30 min |
| L3 Buffer | Computes the heat pump setpoint | 3 h |
| Learning | Refits per-room parameters | nightly |

### 6.3 L0: valve

- ON setpoint is target + 2 °C, OFF setpoint is target - 2 °C. Extreme setpoints such as 30 °C and 5 °C are not used.
- With a 0.3 °C differential the controller decides as long as the room stays within about target ±1.7 °C. Outside that range the thermostat takes over, which is intended: it closes on overheating and opens on cooling.
- If Home Assistant stops, the thermostat holds its last setpoint, so the room settles near target ±2 °C without any software running.
- Setpoints are clamped to the device range, one step below `max_temp`.
- Control uses the setpoint only. `hvac_mode` stays on `heat`, in manual mode, with no device schedule.
- Commands are tagged with a context so that user changes can be recognised.
- The watchdog compares the commanded state with later reads and `hvac_action`, retries, and raises an alert after 3 consecutive mismatches. The commanded state is stored by the controller, separately from what is read back.
- Wall display and manual changes: the display shows the setpoint alternating around the target. For now the watchdog overwrites a manual change on the wall. Proposed handling: treat it as shifting the target by the same difference. **[TODO]** decide, or use the `Lock` entity.

### 6.4 L1: zone

- PID in normalised power units, so that the duty scales correctly with the buffer temperature. Integration pauses at saturation, while a window is open, without valid data, and when the thermostat acts outside the L0 band.
- Until `k3` is learned, the floor is assumed to be 3 K warmer than the air when scaling for the buffer temperature.
- Integration runs four times faster while the error exceeds 0.3 K. Without this, a room recovering from a cold start crawls over the last degree for many hours, because the integral starts near zero. No initial estimate of the room's demand is needed. The integral is kept across restarts, so a room that was switched off recovers faster.
- Cycle length: `max(90, 12 / d, 12 / (1 - d))` minutes, capped at 180, where `d` is the duty as a fraction. This gives the algorithm-selected frequency required in 2.3: never a pulse shorter than 12 minutes, and longer cycles at extreme duties.
- On-time that is too short to run is carried over to the next cycle.
- Above about 87% duty the valve simply stays open, which also means fewer writes.
- Zones are staggered in phase, so the load stays even and the loops do not all close at once. Zones are not run strictly in sequence, since heating several at once is better for the source.

### 6.5 L2: prediction

- Outdoor temperature comes from the local sensor. The forecast contributes only its change: `T_out(+2 h) = sensor(now) + forecast(+2 h) - forecast(now)`. The forecast and the sensor differ (6.8 °C against 4.2 °C on one observed day), and a constant ±2.6 K error did not change the simulated result.
- The solar signal is the hourly cloud forecast through the Kasten-Czeplak attenuation. Scaling by clear-sky irradiance for seasonal change is planned and not yet tested.

### 6.6 L3: buffer

- Runs every 3 hours and computes the required temperature from the formula in 6.1, for each room, using the coldest outdoor temperature forecast over the next 6 hours and ignoring the sun, so that a cloudy morning is still covered.
- The target is 100% open for the most demanding room. In simulation it settles at 85-91%, because of the guards below.
- A trim corrects the model: +0.5 K when any room is more than 0.25 °C below target, -0.25 K when the most demanding zone is at least 10 points under the open target and no room is more than 0.1 °C below target. The trim is limited to ±5 K.
- Rate limits: at most +2 K and -0.5 K per run. Setpoints are rounded to 0.5 °C.
- Hard limit: 38 °C. Without floor sensors this is the only firm protection for the floor. A room that needs more stays at 100% open, and an alert is raised. Simulated cold spells reached 38-39 °C, so the limit may come into play in hard frost.
- The heat pump setpoint is treated as the real buffer temperature, which also keeps L1 from chasing the pump's own hysteresis. No separate buffer sensor is used.
- Rollout is advisory first: log the recommended setpoint, then write it.

### 6.7 Learning

Three layers per room, updated nightly from that room's own data. Before enough data exists, the room runs on PID alone.

**Daily balance: `k1`, `k3` (and a starting value for the sun).** One row per day: fraction of time heating (from `hvac_action`), room temperature, outdoor temperature, buffer temperature, sun estimate. The fit uses a rolling 30 day window:

```
L    = k1 * (T_room - T_outdoor) - k2 * sun
duty = L / (T_buffer - T_room - k3 * L)
```

New values are blended in (85% old, 15% new). No deliberate cooling of rooms is needed, so step tests are optional.

**Solar profile: 24 values.** Each night, each hourly value moves according to the room's mean deviation 2 hours later, weighted by that day's forecast clearness, and the profile is smoothed across neighbouring hours and kept non-negative. Window orientation does not have to be configured. In simulation the peak correction emerged by itself: 8:00 for an east room, 10:00 for a south room, 13:00 for a west room.

**Recurring gains: 24 values.** The same rule, weighted towards cloudy days, with the mean removed and values limited. This captures things like cooking.

**Safeguards.** Parameters are bounded. Learned feed-forward becomes active only after at least 14 days of data and a daily balance error below about 5 percentage points. A room falls back to PID if it performs worse with learning than without it over a recent window (this safeguard is not yet simulated). Learned values are visible in diagnostics, and learning can be switched off per room. Learning skips periods with open windows and re-syncs after data gaps. It also skips days when a room is recovering from a cold start, because heat going into a cold floor and cold walls says nothing about steady losses.

### 6.8 Failure handling

| Failure | Behaviour |
|---|---|
| Home Assistant down | Thermostats keep the room near target ±2 °C. The heat pump keeps its last setpoint, with no weather compensation. A cold spell may cool rooms slowly. Needs an alert from outside Home Assistant, and manual return to `auto` during long outages. |
| Integration unloaded or crashed | Thermostats get the plain target as setpoint and regulate on their own (hand-back). Heartbeat entity for monitoring. |
| Thermostat unavailable | Zone reports unavailable instead of a false "off", and integration pauses. Other zones are unaffected. |
| Room temperature stale | After 30 min the last duty is held. After 60 min the zone is handed back to the thermostat. |
| SmartThings unavailable | L3 freezes, the last setpoint stays assumed, zones keep running, alert raised. |
| Outdoor sensor lost | AccuWeather with the last known offset, alert after 2 h. |
| Forecast lost | Current outdoor temperature is used, and solar feed-forward is disabled. |
| Model not trusted | PID only. |

Valve exercise: any loop idle for 7 days is opened for 15 minutes. The 15 seconds used by RoomMind is too short for thermal actuators.

### 6.9 Integration and repository

Each room is one configuration entry. The integration exposes the target, duty, PID terms, valve state, status and daily comfort metrics as entities, plus a diagnostics download with one row per day. Each zone has a mode: `observe` (calculates and logs only, the default for a new room), `active`, or `handback`.

On switching from `observe` to `active`, the integral starts from how much the thermostat has recently been heating, but only if the room is near its target. Otherwise it starts from zero.

```
custom_components/what_the_heat/
  core/          pure Python, no Home Assistant imports
                 (pid, cycle, valve, zone, runner, daily)
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
| Cycle length | 90-180 min | simulation |
| Minimum open and closed time | 12 min | hass-ufh-controller (9 min) plus margin |
| Actuator travel | 3.5 min, to be measured | hass-ufh-controller |
| Setpoint band | target ±2 °C | this project |
| Outdoor lead | 2 h | simulation |
| Floor offset filter | 3 h | simulation |
| Buffer run interval | 3 h, forecast 6 h ahead | simulation |
| Buffer open target | 100% of the most demanding room | owner principle, simulation |
| Buffer limit | 38 °C | owner |
| Buffer rate limit | +2 K, -0.5 K per run | simulation |
| Learning window | 30 days, minimum 14 days | simulation |
| Solar and gains learning rate | 2 and 1 per day, deviation lag 2 h | simulation |
| Model trust threshold | daily balance error under about 5 points | proposal, unverified |
| Watchdog | every 5 min, alert after 3 mismatches | hass-ufh-controller, this project |
| Valve exercise | 7 days, 15 min | RoomMind (interval) |

---

## 8. Simulation evidence

Common assumptions: a 20 m² reference room scaled by area, three thermal nodes (screed, air, wall mass) with 60% of solar gain landing on the floor, screed 0.65 kWh/K, actuators 3.5 minutes with flow at 85% position, sensor resolution 0.1 °C. The controller sees room air temperature, buffer temperature or setpoint, valve state and forecasts. The controller and the fits assume a simpler model than the plant. Results vary by several points between runs. The complete system (learning, buffer control and shared buffer together) has not yet been simulated as one.

### 8.1 Floor temperature is not needed

Fixed 36 °C buffer, outdoor 3 ±3 °C, sun every other day. Time within ±0.3 °C and temperature range:

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

The buffer temperature matters when it varies. With setpoint steps of ±3 K, learning that knows the buffer temperature reached 96.5%, and without it 79%.

### 8.4 Buffer control

Six zones with differing demand, 100 L buffer, sun on some zones, DHW twice a day. Values are for: stable 5 °C / cold front / -5 °C / thaw 8 °C.

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

Reducing flow in low-demand loops evens out opening times: with an open target of 90%, zone opening ranged 27-66% before and 49-68% after, and at a target of 100% it ranged 56-83%. Starts also fall. The controller can recommend flow changes from learned `k1` values. Adjusting the manifold remains a manual step.

### 8.6 Pilot room

This uses the simulator in this repository, with the implemented controller: PID and cycles only, no prediction or learning. Run it with `python -m tests.simulation.pilot`. The results cover seven assumed room types at a 30, 34 or 38 °C buffer with a 21 °C target, with the wall losing heat to the ground. One physically impossible case (high losses at 30 °C) is left out, where both variants stop at 19.6 °C. The thermostat is modelled as switching on at setpoint - 0.3 °C and off at the setpoint, which is an assumption about the real device.

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
- Afterwards the room stays within the band at least 99% of the time, except for a room with heavy air at a 30 °C buffer, at 79-83%.

Real basement walls and soil are likely to warm much more slowly than this model, so the first days in a real room will not be representative.

Error in the assumed buffer temperature, over the same room types. At a real 34 or 38 °C and an error within ±2 K, the worst room stayed within the band 92-100% of the time. At ±4 K half of the rooms were still at 100%, but the worst fell to 51-95%. At ±6 K the worst fell to 22-71%. At a real 30 °C, where some rooms are near their limit, ±2 K already took the worst room to 67-72%.

---

## 9. Roadmap

| Stage | Scope | Done when |
|---|---|---|
| 0 Preparation | Extend recorder retention, start a baseline in the pilot room | Retention extended |
| 1 Core and simulator | Pure Python core and simulator with failure injection | Done for the pilot scope: PID, cycles, valve, watchdog, zone |
| 2 Integration | Home Assistant layer with `observe`, `active` and `handback` modes, and daily rows logged | Built and tested against a stand-in thermostat. Calculated duty still has to be checked next to the real thermostat. |
| 3 Pilot | One room live, see 9.1 | Criteria in 9.1 met |
| 4 Learning and prediction | Learning and feed-forward, first in the simulator, then on the pilot room | Smaller RMS deviation than PID alone |
| 5 All rooms | All zones, phase staggering, manifold recommendations, shared buffer in the simulator | One stable week |
| 6 Buffer | L3 advisory, then writing the heat pump setpoint | Lower mean buffer temperature at equal comfort |
| Later, optional | Shading, online EKF, MPC | Justified by data |

### 9.1 Pilot

A real test on one closed basement room, chosen for its small outside influence, at a target of 21 °C. The steps are in the [pilot test guide](pilot-test.md).

- Only PID and cycles run. There is no prediction, learning or buffer control yet, but daily rows are logged from the first day.
- The heat pump stays in one mode during comparisons: on its own curve, or at a constant fixed temperature of at most 38 °C. Changing it would also affect all other rooms, which remain on their own thermostats. On the curve, the 38 °C limit depends on the curve's settings.
- Sequence: a plain thermostat baseline at 21 °C, then `observe` mode, then `active` mode. The first days after a cold room starts warming are not used for comparison. Cold start can be tested later by switching the room off for a few days.
- Measured: time within ±0.3 °C, RMS deviation, longest closed period, setpoint writes per day, watchdog events, and whether the relay follows commands.
- Also to learn from it: real actuator travel, command latency, and how the thermostat switches around its setpoint.
- Done when: smaller deviation than the baseline, no setpoint stuck for more than 10 minutes over 7 days, and a tested Home Assistant restart and outage.

---

## 10. Success criteria

All based on what can be measured: air temperature, valve state and heat pump data.

- Deviation from target within ±0.3 °C for at least 90% of the time. **[TODO]** confirm.
- No overheating beyond +0.7 °C on sunny days, to be reassessed on real data since it may need shading in strongly sunlit rooms.
- No valve cycle shorter than the minimum time.
- No setpoint stuck for more than 10 minutes.
- Lower mean buffer temperature and lower energy use at equal comfort, compared with a baseline at similar outdoor temperature.
- Compressor starts no higher than the baseline.
- "The floor is never cold" is checked indirectly, through the longest continuous closed period of each loop. Floor temperature is not measured.

---

## 11. Risks

| Risk | Mitigation |
|---|---|
| Thermostat loses a command | Setpoint-only control, watchdog, alerts |
| Setpoint writes wear out device flash | Long cycles, write logging. Wear is unknown. |
| Heat pump stays at a low setpoint during an outage | Alert from outside Home Assistant, manual return to `auto` |
| Floor overheating with no sensor | 38 °C buffer limit |
| The buffer limit is too low in hard frost | Rooms run fully open, an alert is raised |
| The set temperature differs from the real buffer temperature | Accepted for simplicity. The integral compensates a steady difference. |
| On the heat pump's own curve, the real buffer temperature moves away from the configured typical value | See 8.6 for the tolerance. Use a fixed temperature if a room reacts badly. |
| Learning degrades a room | Bounds, trust threshold, fallback to PID, per-room switch |
| Integration bug affects Home Assistant, since it runs in-process | Async only, no blocking work, core tested separately |
| Short cycling of the compressor at low load | Phase staggering, longer open times, measured starts. Partly limited by hardware. |
| All loops closed with the manifold pump running | Stage 0 check, phase staggering |
| Windows or ventilation | Window sensors or detection, integration pause |
| Simulation does not reflect the house | Observation mode, reference room, gradual rollout |

---

## 12. Open questions [TODO]

1. Other rooms: name, `climate` entity, target temperature.
2. Heat pump minimum modulation power.
3. Manifold pump behaviour with all loops closed.
4. Actuator type and travel time.
5. Handling of manual changes on the wall thermostat.
6. Window sensors, if any.
7. Target comfort tolerance.
8. Dashboard requirements.
9. Repository license.

---

## 13. Decisions

| Decision | Reason |
|---|---|
| Built from scratch, with existing projects as references | Owner decision |
| Home Assistant custom integration in Python | All layers in one codebase, first-class entities, restore state, existing test tooling |
| Control through thermostat setpoints in a ±2 °C band | Safe when the software is not running |
| No floor temperature anywhere in the control path | No sensors exist, and simulation shows it is not needed |
| Learning through small per-room layers rather than a neural network | Limited data, explainability, safety |
| Buffer computed from model and forecast, aiming at 100% open | Owner principle, simulation |
| Set heat pump temperature treated as the real buffer temperature, 38 °C limit | Owner decision, for simplicity |
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
