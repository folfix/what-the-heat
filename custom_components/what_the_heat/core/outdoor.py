"""What the outdoor temperature does to a room, learned while the sun does not interfere."""

from __future__ import annotations

from dataclasses import dataclass

from .smoothing import ExponentialFilter


@dataclass(frozen=True)
class OutdoorConfig:
    """How a room learns what the outdoor temperature does to it."""

    # The usual outdoor temperature. The steady demand in the integral belongs to it.
    usual_time_constant_s: float = 24 * 3600.0
    # Smoothing of the reading, so that a single odd reading does not move the valve.
    smoothing_s: float = 15 * 60.0
    # The usual temperature needs this much data before the correction acts.
    min_history_s: float = 24 * 3600.0
    # Without a reading for this long, the correction stops until the sensor is back.
    max_gap_s: float = 2 * 3600.0
    # Change of the weight per hour, per kelvin of room deviation and per kelvin of
    # difference from the usual outdoor temperature.
    rate: float = 0.01
    max_weight: float = 5.0  # percent per kelvin, like the integral
    # The sun warms the air outside and the room at the same time, so the weight learns
    # only while the share of full sun is below this.
    max_sun: float = 0.1


class OutdoorCorrection:
    """More heat when it is colder outside than usual, and less when it is warmer.

    The correction is the weight times how much colder than usual it is outside. The
    weight learns from the room's own deviation: if the room is too cold while it is
    colder outside than usual, the weight grows, and the other way round. It is never
    negative, so colder weather never means less heat. A basement room that hardly feels
    the weather learns a small weight.
    """

    def __init__(
        self,
        config: OutdoorConfig | None = None,
        weight: float = 0.0,
        usual: float | None = None,
        smoothed: float | None = None,
        history_s: float = 0.0,
    ) -> None:
        self._config = config or OutdoorConfig()
        self._weight = weight
        self._usual = ExponentialFilter(self._config.usual_time_constant_s)
        self._smoothed = ExponentialFilter(self._config.smoothing_s)
        if usual is not None:
            self._usual.update(usual, 0.0)
        if smoothed is not None:
            self._smoothed.update(smoothed, 0.0)
        self._history_s = history_s
        self._gap_s = 0.0

    @property
    def weight(self) -> float:
        """Return the learned weight, in percent per kelvin."""
        return self._weight

    @property
    def difference(self) -> float | None:
        """Return how much colder than usual it is outside, or None while that is unknown."""
        config = self._config
        usual, smoothed = self._usual.value, self._smoothed.value
        if usual is None or smoothed is None or self._history_s < config.min_history_s or self._gap_s > config.max_gap_s:
            return None
        return usual - smoothed

    def feedforward(self) -> float:
        """Return the change of the controller output for the outdoor temperature now."""
        difference = self.difference
        return 0.0 if difference is None else self._weight * difference

    def update(self, outdoor: float | None, dt_s: float) -> None:
        """Add an outdoor reading taken dt_s seconds after the previous step, or None without one."""
        if outdoor is None:
            self._gap_s += max(0.0, dt_s)
            return
        self._gap_s = 0.0
        self._usual.update(outdoor, dt_s)
        self._smoothed.update(outdoor, dt_s)
        self._history_s += max(0.0, dt_s)

    def learn(self, error: float, dt_s: float, sun: float | None) -> None:
        """Move the weight by the room's error, the target minus the room temperature."""
        config = self._config
        difference = self.difference
        if difference is None or (sun is not None and sun > config.max_sun):
            return
        change = config.rate * error * difference * dt_s / 3600.0
        self._weight = min(config.max_weight, max(0.0, self._weight + change))

    def reset(self) -> None:
        """Forget the weight. The measured temperatures stay."""
        self._weight = 0.0

    def snapshot(self) -> dict[str, float | None]:
        """Return the state worth keeping across a restart."""
        return {
            "weight": self._weight,
            "usual": self._usual.value,
            "smoothed": self._smoothed.value,
            "history_s": self._history_s,
        }
