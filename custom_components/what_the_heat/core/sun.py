"""The sun as a PV installation sees it, and what each room learns about it.

PV power shows the sun as soon as it shines, often hours before a room's reading does,
since the sun reaches the panels and the windows at different times and the screed and
the air are slow. Each room learns, hour by hour, how much heat the sun makes unnecessary.
"""

from __future__ import annotations

from dataclasses import dataclass, field

HOURS = 24
DAY_S = 86400.0


@dataclass(frozen=True)
class SunSignalConfig:
    """How PV power becomes a share of full sun."""

    # The highest power seen counts as full sun. It fades slowly, so that the lower sun of
    # another season reaches full sun again after a few weeks.
    half_life_days: float = 30.0
    # Below this, nothing is known yet about how strong the sun can be.
    min_reference_w: float = 200.0


class SunSignal:
    """Turns PV power into a share of full sun, from 0 to 1. One for the whole house."""

    def __init__(
        self,
        config: SunSignalConfig | None = None,
        reference_w: float = 0.0,
        updated_s: float | None = None,
    ) -> None:
        self._config = config or SunSignalConfig()
        self._reference_w = reference_w
        self._updated_s = updated_s

    @property
    def reference_w(self) -> float:
        """Return the power that counts as full sun."""
        return self._reference_w

    def update(self, power_w: float | None, now_s: float) -> float | None:
        """Return the share of full sun, or None while the power is unknown."""
        if power_w is None:
            return None
        if self._updated_s is not None and now_s > self._updated_s:
            elapsed_days = (now_s - self._updated_s) / DAY_S
            self._reference_w *= 0.5 ** (elapsed_days / self._config.half_life_days)
        if self._updated_s is None or now_s > self._updated_s:
            self._updated_s = now_s
        power = max(0.0, power_w)
        self._reference_w = max(self._reference_w, power)
        if self._reference_w < self._config.min_reference_w:
            return 0.0
        return power / self._reference_w

    def snapshot(self) -> dict[str, float | None]:
        """Return the state worth keeping across a restart."""
        return {"reference_w": self._reference_w, "updated_s": self._updated_s}


@dataclass(frozen=True)
class SolarConfig:
    """How a room learns what the sun does to it."""

    # The sun shows in the room's reading about this many hours after it shows on the panels.
    lag_h: int = 2
    # After each day, the value of an hour moves by rate * gain * the share of full sun in
    # that hour * the mean deviation from the target lag_h hours later.
    rate: float = 0.25
    gain: float = 80.0  # percent per kelvin, like the proportional gain
    max_value: float = 100.0
    # Share of each neighbouring hour mixed into an hour after a day's update.
    smoothing: float = 0.2
    # An hour with less data than this is left out.
    min_hour_s: float = 30 * 60.0
    # A day with at least this many hours' worth of full sun counts as sunny.
    sunny_day_hours: float = 2.0
    # The profile acts only after this many sunny days.
    min_sunny_days: int = 3


@dataclass
class _Day:
    """Hourly totals of one day."""

    date: str
    sun_sum: list[float] = field(default_factory=lambda: [0.0] * HOURS)
    sun_s: list[float] = field(default_factory=lambda: [0.0] * HOURS)
    error_sum: list[float] = field(default_factory=lambda: [0.0] * HOURS)
    error_s: list[float] = field(default_factory=lambda: [0.0] * HOURS)


class SolarProfile:
    """For each hour of the day, how much less heat the room needs at full sun.

    The values are in the controller's percent, like the integral. Each day they learn from
    what happened: if the room was above its target lag_h hours after a sunny hour, that
    hour asks for less heat the next time the sun shines, and the other way round. Values
    never go below zero, so the sun never makes the valve open more.
    """

    def __init__(
        self,
        config: SolarConfig | None = None,
        values: list[float] | None = None,
        sunny_days: int = 0,
        day: dict | None = None,
    ) -> None:
        self._config = config or SolarConfig()
        self._values = [float(value) for value in values] if values and len(values) == HOURS else [0.0] * HOURS
        self._sunny_days = sunny_days
        self._day = _Day(**day) if day else None

    @property
    def values(self) -> tuple[float, ...]:
        """Return the learned value of each hour."""
        return tuple(self._values)

    @property
    def sunny_days(self) -> int:
        """Return how many sunny days the profile has learned from."""
        return self._sunny_days

    @property
    def active(self) -> bool:
        """Return whether the profile has learned enough to act."""
        return self._sunny_days >= self._config.min_sunny_days

    def feedforward(self, hour: int, sun: float | None) -> float:
        """Return the change of the controller output for the sun now. It is never positive."""
        if not self.active or not sun:
            return 0.0
        return -self._values[hour % HOURS] * sun

    def add(self, date: str, hour: int, dt_s: float, sun: float | None, deviation: float | None) -> None:
        """Add one interval. A new date closes the previous day and learns from it."""
        if self._day is None or self._day.date != date:
            if self._day is not None:
                self._learn(self._day)
            self._day = _Day(date)
        if dt_s <= 0:
            return
        index = hour % HOURS
        if sun is not None:
            self._day.sun_sum[index] += sun * dt_s
            self._day.sun_s[index] += dt_s
        if deviation is not None:
            self._day.error_sum[index] += deviation * dt_s
            self._day.error_s[index] += dt_s

    def reset(self) -> None:
        """Forget everything learned."""
        self._values = [0.0] * HOURS
        self._sunny_days = 0
        self._day = None

    def snapshot(self) -> dict:
        """Return the state worth keeping across a restart."""
        day = self._day
        return {
            "values": list(self._values),
            "sunny_days": self._sunny_days,
            "day": None if day is None else {
                "date": day.date,
                "sun_sum": list(day.sun_sum),
                "sun_s": list(day.sun_s),
                "error_sum": list(day.error_sum),
                "error_s": list(day.error_s),
            },
        }

    def _learn(self, day: _Day) -> None:
        config = self._config
        sun_hours = 0.0
        changed = False
        for hour in range(HOURS):
            if day.sun_s[hour] < config.min_hour_s:
                continue
            share = day.sun_sum[hour] / day.sun_s[hour]
            sun_hours += share
            later = hour + config.lag_h
            if share <= 0.0 or later >= HOURS or day.error_s[later] < config.min_hour_s:
                continue
            error = day.error_sum[later] / day.error_s[later]
            self._values[hour] += config.rate * config.gain * share * error
            changed = True
        if changed:
            self._smooth()
        if sun_hours >= config.sunny_day_hours:
            self._sunny_days += 1

    def _smooth(self) -> None:
        config = self._config
        weight = config.smoothing
        old = self._values
        self._values = [
            min(
                config.max_value,
                max(
                    0.0,
                    (1.0 - 2.0 * weight) * old[hour]
                    + weight * old[max(0, hour - 1)]
                    + weight * old[min(HOURS - 1, hour + 1)],
                ),
            )
            for hour in range(HOURS)
        ]
