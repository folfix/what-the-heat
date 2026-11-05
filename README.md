# what-the-heat

Makes water-based underfloor heating work like PWM, to eliminate the delay.

A planned Home Assistant custom integration that keeps each room at its target temperature with the smallest possible deviation. It uses a low buffer temperature and loops that stay open for as long as possible.

- **Per-room control:** a duty cycle applied through ordinary thermostat setpoints.
- **Learning:** each room's losses, sun exposure and recurring gains are learned from its own data. No floor sensors are needed.
- **Buffer control:** the heat pump setpoint follows the most demanding room and the weather forecast.

## Status

Early development, not usable yet. The control core and a simulator exist, while the Home Assistant layer does not. Figures in the specification come from simulations with assumed room data and have not been verified in a real house.

See the [specification](docs/specification.md) for requirements, architecture, parameters, simulation results and the roadmap.

## Development

Requires Python 3.13 or newer and no other packages. Run from the repository root:

```bash
python -m unittest discover -s tests -t .
```

```bash
python -m tests.simulation.pilot
```
