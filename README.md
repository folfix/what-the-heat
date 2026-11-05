# what-the-heat

Makes water-based underfloor heating work like PWM, to eliminate the delay.

A planned Home Assistant custom integration that keeps each room at its target temperature with the smallest possible deviation. It uses a low buffer temperature and loops that stay open for as long as possible.

- **Per-room control:** a duty cycle applied through ordinary thermostat setpoints.
- **Learning:** each room's losses, sun exposure and recurring gains are learned from its own data. No floor sensors are needed.
- **Buffer control:** the heat pump setpoint follows the most demanding room and the weather forecast.

## Status

Early development, ready for a first test on one room. So far it has PI control and valve cycles only, without prediction, learning or buffer control. It has been tested against simulated rooms and a stand-in thermostat, but not yet on a real device. Figures in the specification come from simulations with assumed room data and have not been verified in a real house.

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
