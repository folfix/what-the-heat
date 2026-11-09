# what-the-heat

Makes water-based underfloor heating work like PWM, to eliminate the delay.

A Home Assistant custom integration that keeps each room at its target temperature with the smallest possible deviation, using loops that stay open for as long as possible at a low, fixed water temperature. Requires Home Assistant 2026.11 or newer.

- **Per-room control:** a duty cycle applied through ordinary thermostat setpoints.
- **No floor sensors:** floor temperature is never needed.
- **No heat source control:** the water temperature is fixed by the mixing valves. The integration only needs to know its value.
- **Learning:** each room's steady demand and, with a PV installation as the sun signal, what the sun does to it at each hour. Losses and recurring gains are planned.

## How it works

A plain thermostat heats until the room is warm and then stops, while the screed keeps releasing heat for hours. This integration instead gives the floor frequent smaller portions of heat, using the thermostat as a remotely controlled valve.

Each room runs on its own, once a minute:

1. **Read:** the room temperature comes from the thermostat and is smoothed over about 10 minutes.
2. **Calculate demand:** a PI controller works out how much heat the room needs from the distance to the target and how long it has lasted.
3. **Convert to duty:** demand becomes the share of time the valve should be open. The hotter the water, the shorter the opening.
4. **Plan cycles:** the duty is split into cycles of 30 minutes, with at least 5 minutes open and 5 minutes closed. An actuator takes 2 to 3 minutes to move, so a shorter pulse would pass little water. On-time too short to run moves to the next cycle.
5. **Move the valve:** a setpoint of target + 3 °C makes the thermostat open it, and target - 3 °C makes it close. A watchdog checks that the thermostat followed, and repeats the command if not. The thermostat's own dead zone should be at most about 2.5 °C, or these setpoints may not switch it while the room is near its target.

If everything stops, the thermostat keeps its last setpoint and holds the room near it. Outside that band the thermostat acts on its own, so the room stays safe.

### Modes

| Mode | What it does | Writes to the thermostat |
|---|---|---|
| **Observe** | Calculates and measures only. Useful as a baseline. | Never, apart from returning the target once when leaving Active |
| **Active** | Controls the thermostat as described above, and keeps it switched on and heating. The default for a new room. | About 100 times a day |
| **Hand back** | Gives the plain target to the thermostat, which then regulates on its own. | Once |

A room's mode is changed with its **Mode** entity, or with the preset of its thermostat entity.

### Shared settings

The first time the integration is added, it asks for the outdoor and PV sensors shared by all rooms, and then each room is added with **Add entry**. These rarely change, so they are kept apart from the rooms: change them with **Configure** on the **Shared settings** entry of the integration. Without that entry the rooms use no sensors.

### Water temperature

This is one setting for all rooms, by default 30 °C. Set it to what the mixing valves are set to, on the **What the Heat** page or with the service `what_the_heat.set_water_temperature`. It may change over time, so unlike the sensors it is not part of the Shared settings.

It only tells the controller what the temperature is: hot water delivers more heat in the same time, so the same demand needs a shorter opening. Nothing is read from or written to the mixing valves, the buffer or the heat pump.

Keep it within about 2 °C of the real value. In simulation that barely changes the results, while at 4 °C some rooms get clearly worse.

If a room stays at 100% and below its target, the water cannot deliver enough heat for it. The integration cannot fix that, so the temperature has to be raised by hand, on the valves and in the setting.

### Outdoor and PV sensors

These are the Shared settings. Neither is required.

- **Outdoor temperature:** preferably in the shade. It drives the weather correction described below.
- **PV power:** the current power of a PV installation, in W or kW. It is the sun signal described below. Use one read locally, since a cloud service may stop for hours.

### What a room learns so far

**Steady demand:** how much of the time the valve must be open to hold the target. The controller works this out while it is in charge. Before that, the integration watches how much the thermostat heats on its own. The value appears after about 6 hours of data near the target, as the **Learned demand** sensor and on the **What the Heat** page.

**The sun:** with a PV sensor set, each room in Active mode learns, for every hour of the day in solar time, how much less heat it needs while the sun shines. Solar time follows the sun rather than the clock, so the profile does not shift when the clocks change. If the room was above its target 2 hours after a sunny hour, that hour asks for less heat the next time the sun shines, and the other way round. After 3 sunny days it starts acting: while the panels see the sun, the valve opens less, in proportion to the PV power compared with the highest seen lately. The panels often see the sun well before the room shows it, so heating that the sun would make unnecessary is left out in advance. It never makes the valve open more. The **Sun correction** sensor shows how much it takes off the valve opening now. In simulated sunny rooms this cut the time above the band by about 30%, at the cost of slightly cooler mornings. It has not yet been measured in a real room.

**The weather:** with an outdoor sensor set, each room adds heat when it is colder outside than usual, and takes some away when it is warmer. The usual temperature is the average over about the last day, which the steady demand already covers, so the correction only follows the swings around it: the night, the afternoon, a front. Each room learns how strongly it feels them from its own deviations, only while the sun does not shine, and a basement room learns that it hardly does. The correction starts after a day of readings, and stops if the sensor is silent for 2 hours. The **Outdoor correction** sensor shows it now. In simulated rooms without sun it cut the typical deviation by about a fifth. It has not yet been measured in a real room.

The **Reset learning** button on a room's device page clears all three when something unusual has misled the controller. The mode, the target and the daily measurements stay. The room needs time to learn again, so expect a temporary dip while the valve stays closed for longer. In simulated rooms the lowest temperature fell by 0.5 to 1.5 °C in most cases, and the room spent up to about half a day outside ±0.3 °C, or about 2.5 days in the slowest case.

### Not there yet

Prediction from the weather forecast and the rest of per-room learning, such as losses and recurring gains, are designed and simulated, but not implemented. See the [specification](docs/specification.md).

### Where to see it

- **Sidebar:** the **What the Heat** page shows all rooms as tiles, where you can change each room's target and the water temperature, and see what each room has learned.
- **Dashboards:** each room has a thermostat entity for a regular tile or thermostat card, along with separate sensors.
- **Diagnostics:** the file you can download on the device page contains one row per day.
- **Logs:** see the [pilot test guide](docs/pilot-test.md).

## Status

Early development, ready for a first test on one room. So far it has PI control and valve cycles, and it learns each room's steady demand and, with PV, what the sun does to it. Prediction from the weather forecast is not there yet. It runs on a real thermostat in a first test, and has otherwise been tested against simulated rooms and a stand-in thermostat. Figures in the specification come from simulations with assumed room data and have not been verified in a real house.

- [Pilot test](docs/pilot-test.md): installation and how to run the test.
- [Specification](docs/specification.md): requirements, architecture, parameters, simulation results and the roadmap.

## Development

The control core and its tests need Python 3.13 or newer and no other packages. Run from the repository root:

```bash
python -m unittest discover -s tests -t .
```

```bash
python -m tests.simulation.pilot
```

```bash
python -m tests.simulation.sun
```

```bash
python -m tests.simulation.outdoor
```

The integration tests run against a real Home Assistant core and need Python 3.14 and the packages in `requirements_test.txt`:

```bash
python -m pytest
```

Home Assistant does not support Windows. To run these tests there, add small stand-ins for the Unix modules `fcntl` and `resource` to the test environment.
