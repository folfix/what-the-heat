"""Compares the controller with a plain thermostat for the pilot room: a closed basement room at 21 °C.

Nothing about the real room has been measured yet, so a range of assumed rooms is covered.
Run from the repository root with: python -m tests.simulation.pilot
"""

from __future__ import annotations

from dataclasses import replace

from custom_components.what_the_heat.core.zone import ZoneConfig

from .harness import Environment, Result, simulate
from .plant import RoomParameters

TARGET = 21.0
REFERENCE = RoomParameters()
# Scaling a whole room by area changes nothing in this model, so only its proportions vary.
ROOMS: dict[str, tuple[RoomParameters, float]] = {
    "reference": (REFERENCE, 11.0),
    "low losses": (replace(REFERENCE, air_to_outside=7.0, wall_to_boundary=12.0), 11.0),
    "high losses": (replace(REFERENCE, air_to_outside=30.0, wall_to_boundary=50.0), 11.0),
    "cold ground": (REFERENCE, 7.0),
    "slow floor": (replace(REFERENCE, floor_capacity=900.0, floor_to_air=110.0), 11.0),
    "light room": (replace(REFERENCE, air_capacity=80.0, wall_capacity=500.0, air_to_wall=100.0), 11.0),
    "heavy air": (replace(REFERENCE, air_capacity=500.0, air_to_wall=20.0, air_to_outside=30.0), 11.0),
}
WATER_TEMPERATURES = (30.0, 34.0, 38.0)
HEADER = (
    f"{'room':<14} {'water':>4} {'in 0.3':>7} {'rms':>6} {'low':>6} {'high':>6} {'start':>6} "
    f"{'duty':>6} {'wr/d':>6} {'off h':>6} {'floor':>6}"
)


def _row(label: str, water: float, result: Result) -> str:
    return (
        f"{label:<14} {water:>4.0f} {result.within_band_pct:>6.1f}% {result.rms:>6.3f} {result.low:>6.2f} "
        f"{result.high:>6.2f} {result.first_days_high:>6.2f} {result.mean_duty:>5.0f}% "
        f"{result.writes_per_day:>6.1f} {result.longest_closed_s / 3600.0:>6.1f} {result.floor_swing:>6.2f}"
    )


def main() -> None:
    """Print one table per controller variant."""
    config = ZoneConfig(target=TARGET)
    for title, use_controller in (("Plain thermostat at the target", False), ("Controller", True)):
        print(f"\n{title}")
        print(HEADER)
        for label, (parameters, ground) in ROOMS.items():
            for water in WATER_TEMPERATURES:
                environment = Environment(water_setpoint=water, ground=ground)
                print(_row(label, water, simulate(parameters, environment, TARGET, config, use_controller)))
    cold_start()


def cold_start() -> None:
    """Print how a room recovers after being off for days, with a cold floor and cold walls."""
    print("\nCold start: floor at air temperature, walls 1 K colder")
    print(
        f"{'room':<14} {'water':>4} {'air':>5} {'hours':>6} {'peak':>6} {'after':>7} "
        f"{'plain h':>8} {'plain pk':>9}"
    )
    config = ZoneConfig(target=TARGET)
    for label, (parameters, ground) in ROOMS.items():
        for water in WATER_TEMPERATURES:
            for air in (19.0, 16.0, 13.0):
                environment = Environment(water_setpoint=water, ground=ground)
                start = {"initial_air": air, "initial_floor": air, "initial_wall": air - 1.0}
                run = simulate(parameters, environment, TARGET, config, initial_integral=0.0, **start)
                plain = simulate(parameters, environment, TARGET, use_controller=False, **start)
                print(
                    f"{label:<14} {water:>4.0f} {air:>5.0f} {_hours(run.reached_target_s):>6} "
                    f"{run.first_days_high:>6.2f} {run.within_band_pct:>6.1f}% "
                    f"{_hours(plain.reached_target_s):>8} {plain.first_days_high:>9.2f}"
                )


def _hours(seconds: float | None) -> str:
    return "never" if seconds is None else f"{seconds / 3600.0:.1f}"


if __name__ == "__main__":
    main()
