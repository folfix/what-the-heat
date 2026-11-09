"""Compares the controller with and without the learned outdoor correction, on assumed rooms.

The weather is an assumption: a daily swing of ±5 K, and in two scenarios a week of fronts
that move the daily mean between -6 and +3 K. The results compare the variants with each
other and do not predict a real room.
Run from the repository root with: python -m tests.simulation.outdoor
"""

from __future__ import annotations

from custom_components.what_the_heat.core.zone import ZoneConfig

from .harness import Environment, Result, simulate
from .pilot import ROOMS

TARGET = 21.0
DAYS = 28.0
SETTLE_DAYS = 14.0
WATER_TEMPERATURES = (34.0, 38.0)
FRONTS = (0.0, -3.0, -6.0, -4.0, 0.0, 3.0, 1.0)
SCENARIOS: dict[str, dict] = {
    "Fronts, no sun": {"outdoor_days": FRONTS},
    "Steady weather, no sun": {},
    "Fronts, sun up to 1000 W, with PV": {"outdoor_days": FRONTS, "sun_peak_w": 1000.0, "clear_days": (1.0, 1.0, 0.3, 1.0, 1.0, 0.6, 1.0)},
}


def run(label: str, water: float, scenario: dict, use_outdoor: bool) -> Result:
    parameters, ground = ROOMS[label]
    environment = Environment(water_setpoint=water, ground=ground, outdoor_mean=0.0, outdoor_swing=5.0, **scenario)
    return simulate(
        parameters,
        environment,
        TARGET,
        ZoneConfig(target=TARGET),
        days=DAYS,
        settle_days=SETTLE_DAYS,
        use_pv="sun_peak_w" in scenario,
        use_outdoor=use_outdoor,
    )


def main() -> None:
    """Print, for each scenario, both variants per room type and their means."""
    for title, scenario in SCENARIOS.items():
        print(f"\n{title}")
        print(f"{'room':<12} {'water':>5}  {'without':>17}  {'with outdoor':>17}")
        totals: dict[bool, list[Result]] = {False: [], True: []}
        for label in ROOMS:
            for water in WATER_TEMPERATURES:
                without, with_outdoor = (run(label, water, scenario, use) for use in (False, True))
                totals[False].append(without)
                totals[True].append(with_outdoor)
                print(
                    f"{label:<12} {water:>5.0f}  {without.within_band_pct:>6.1f}% {without.rms:>5.3f} °C"
                    f"  {with_outdoor.within_band_pct:>6.1f}% {with_outdoor.rms:>5.3f} °C"
                )
        for use, results in totals.items():
            count = len(results)
            print(
                f"{'mean, ' + ('with outdoor' if use else 'without'):<24} in band {sum(r.within_band_pct for r in results) / count:5.1f}%  "
                f"rms {sum(r.rms for r in results) / count:.3f} °C  low {sum(r.low for r in results) / count:.2f}  "
                f"below {sum(r.below_band_kh_per_day for r in results) / count:.2f} K·h a day"
            )


if __name__ == "__main__":
    main()
