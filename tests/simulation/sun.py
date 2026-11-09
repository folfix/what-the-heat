"""Compares ways of handling the sun on assumed rooms, with PV as the sun signal.

The rooms, the sun and the timing are assumptions, loosely shaped on a sunny room in
November: the panels see the sun about two hours before the room does. The results
compare the variants with each other and do not predict a real room.
Run from the repository root with: python -m tests.simulation.sun
"""

from __future__ import annotations

from dataclasses import dataclass

from custom_components.what_the_heat.core.sun import SolarConfig
from custom_components.what_the_heat.core.zone import ZoneConfig

from .harness import Environment, Result, simulate
from .pilot import ROOMS

TARGET = 21.0
DAYS = 21.0
SETTLE_DAYS = 7.0
ROOM_TYPES = ("reference", "low losses", "slow floor", "light room", "heavy air")
WATER_TEMPERATURES = (30.0, 34.0)
SUN_PEAKS_W = (800.0, 1500.0)
# A share of full sun for each day, repeating: mostly sunny, with a dull and a hazy day.
CLEAR_DAYS = (1.0, 1.0, 0.3, 1.0, 1.0, 0.6, 1.0)


@dataclass(frozen=True)
class Variant:
    label: str
    use_controller: bool = True
    use_pv: bool = False
    sun_config: SolarConfig | None = None


VARIANTS = (
    Variant("plain thermostat", use_controller=False),
    Variant("controller, no PV"),
    Variant("controller, PV profile", use_pv=True),
)
HEADER = (
    f"{'room':<12} {'water':>5} {'sun W':>6} {'variant':<22} {'in 0.3':>7} {'rms':>6} {'low':>6} {'high':>6} "
    f"{'above':>6} {'below':>6} {'duty':>5} {'wr/d':>5}"
)


def run(label: str, water: float, sun_w: float, variant: Variant) -> Result:
    parameters, ground = ROOMS[label]
    environment = Environment(
        water_setpoint=water,
        ground=ground,
        outdoor_mean=-1.0,
        sun_peak_w=sun_w,
        clear_days=CLEAR_DAYS,
    )
    return simulate(
        parameters,
        environment,
        TARGET,
        ZoneConfig(target=TARGET),
        variant.use_controller,
        days=DAYS,
        settle_days=SETTLE_DAYS,
        use_pv=variant.use_pv,
        sun_config=variant.sun_config,
    )


def main() -> None:
    """Print one row per room, water temperature, sun and variant, then the means."""
    print("Above and below: kelvin-hours a day outside target ±0.3 °C.")
    print(HEADER)
    totals: dict[str, list[Result]] = {variant.label: [] for variant in VARIANTS}
    for label in ROOM_TYPES:
        for water in WATER_TEMPERATURES:
            for sun_w in SUN_PEAKS_W:
                for variant in VARIANTS:
                    result = run(label, water, sun_w, variant)
                    totals[variant.label].append(result)
                    print(
                        f"{label:<12} {water:>5.0f} {sun_w:>6.0f} {variant.label:<22} {result.within_band_pct:>6.1f}% "
                        f"{result.rms:>6.3f} {result.low:>6.2f} {result.high:>6.2f} {result.above_band_kh_per_day:>6.2f} "
                        f"{result.below_band_kh_per_day:>6.2f} {result.mean_duty:>4.0f}% {result.writes_per_day:>5.1f}"
                    )
        print()
    print("Means over all rooms, water temperatures and sun peaks")
    for label, results in totals.items():
        print(_mean(label, results))
    shaded()


def shaded() -> None:
    """Print what the profile does in rooms the sun does not reach while the panels see it."""
    print("\nNo sun in the room, while the panels see it")
    for variant in VARIANTS[1:]:
        results = [run(label, water, 0.0, variant) for label in ROOM_TYPES for water in WATER_TEMPERATURES]
        print(_mean(variant.label, results))


def _mean(label: str, results: list[Result]) -> str:
    count = len(results)
    return (
        f"{label:<24} in band {sum(r.within_band_pct for r in results) / count:5.1f}%  "
        f"rms {sum(r.rms for r in results) / count:.3f}  "
        f"high {sum(r.high for r in results) / count:.2f}  low {sum(r.low for r in results) / count:.2f}  "
        f"above {sum(r.above_band_kh_per_day for r in results) / count:.2f}  "
        f"below {sum(r.below_band_kh_per_day for r in results) / count:.2f} K·h/d"
    )


if __name__ == "__main__":
    main()
