# what-the-heat

Makes water-based underfloor heating work like PWM, to eliminate the delay.

A Home Assistant custom integration that keeps each room at its target temperature with the smallest possible deviation, using loops that stay open for as long as possible at a low, fixed water temperature. Requires Home Assistant 2026.11 or newer.

- **Per-room control:** a duty cycle applied through ordinary thermostat setpoints.
- **No floor sensors:** floor temperature is never needed.
- **No heat source control:** the water temperature is fixed by the mixing valves. The integration only needs to know its value.
- **Learning (planned):** each room's losses, sun exposure and recurring gains, learned from its own data.

## How it works

A plain thermostat heats until the room is warm and then stops, while the screed keeps releasing heat for hours. This integration instead gives the floor frequent smaller portions of heat, using the thermostat as a remotely controlled valve.

Each room runs on its own, once a minute:

1. **Read:** the room temperature comes from the thermostat and is smoothed over about 10 minutes.
2. **Calculate demand:** a PI controller works out how much heat the room needs from the distance to the target and how long it has lasted.
3. **Convert to duty:** demand becomes the share of time the valve should be open. The hotter the water, the shorter the opening.
4. **Plan cycles:** the duty is split into cycles of 90 to 180 minutes, with at least 12 minutes open and 12 minutes closed. On-time too short to run moves to the next cycle.
5. **Move the valve:** a setpoint of target + 2 °C makes the thermostat open it, and target - 2 °C makes it close. A watchdog checks that the thermostat followed, and repeats the command if not.

If everything stops, the thermostat keeps its last setpoint and holds the room near it. Outside that band the thermostat acts on its own, so the room stays safe.

### Modes

| Mode | What it does | Writes to the thermostat |
|---|---|---|
| **Observe** | Calculates and measures only. The default for a new room, and useful as a baseline. | Never, apart from returning the target once when leaving Active |
| **Active** | Controls the thermostat as described above, and keeps it switched on and heating. | About 30 times a day |
| **Hand back** | Gives the plain target to the thermostat, which then regulates on its own. | Once |

### Water temperature

This is one global setting for all rooms, by default 30 °C. Set it to what the mixing valves are set to, on the **What the Heat** page or with the service `what_the_heat.set_water_temperature`.

It only tells the controller what the temperature is: hot water delivers more heat in the same time, so the same demand needs a shorter opening. Nothing is read from or written to the mixing valves, the buffer or the heat pump.

Keep it within about 2 °C of the real value. In simulation that barely changes the results, while at 4 °C some rooms get clearly worse.

If a room stays at 100% and below its target, the water cannot deliver enough heat for it. The integration cannot fix that, so the temperature has to be raised by hand, on the valves and in the setting.

### Not there yet

Prediction from the weather forecast and per-room learning are designed and simulated, but not implemented. See the [specification](docs/specification.md).

### Where to see it

- **Sidebar:** the **What the Heat** page shows all rooms as tiles, where you can change the target and the mode.
- **Dashboards:** each room has a thermostat entity for a regular tile or thermostat card, along with separate sensors.
- **Diagnostics:** the file you can download on the device page contains one row per day.
- **Logs:** see the [pilot test guide](docs/pilot-test.md).

## Status

Early development, ready for a first test on one room. So far it has PI control and valve cycles only, without prediction or learning. It runs on a real thermostat in a first test, and has otherwise been tested against simulated rooms and a stand-in thermostat. Figures in the specification come from simulations with assumed room data and have not been verified in a real house.

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

The integration tests run against a real Home Assistant core and need Python 3.14 and the packages in `requirements_test.txt`:

```bash
python -m pytest
```

Home Assistant does not support Windows. To run these tests there, add small stand-ins for the Unix modules `fcntl` and `resource` to the test environment.
