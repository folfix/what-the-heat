"""PID-style controller producing a duty cycle in percent. The derivative term is not used."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PidConfig:
    """Controller gains, expressed at a gain scale of 1."""

    kp: float = 80.0  # percent per kelvin
    ki: float = 0.0005  # percent per kelvin-second
    integral_min: float = 0.0
    integral_max: float = 100.0
    # Integrate faster while far from the target, so a room recovering from a cold start
    # does not crawl over the last degree. Close to the target the normal rate applies.
    boost_error: float = 0.3
    boost_factor: float = 4.0


@dataclass(frozen=True)
class PidOutput:
    """Result of one controller update."""

    error: float
    proportional: float
    integral: float
    feedforward: float
    duty: float


class PidController:
    """PI controller with conditional integration to prevent windup."""

    def __init__(self, config: PidConfig | None = None, integral: float = 0.0) -> None:
        self._config = config or PidConfig()
        self._integral = self._clamp_integral(integral)
        self._last: PidOutput | None = None

    @property
    def integral(self) -> float:
        """Return the integral term in percent."""
        return self._integral

    @property
    def last(self) -> PidOutput | None:
        """Return the most recent output."""
        return self._last

    @integral.setter
    def integral(self, value: float) -> None:
        self._integral = self._clamp_integral(value)

    def update(
        self,
        error: float,
        dt_s: float,
        feedforward: float = 0.0,
        gain_scale: float = 1.0,
    ) -> PidOutput:
        """Return the duty for this error.

        The sum of the proportional, integral and feed-forward terms is multiplied by
        gain_scale, which converts required power into valve duty at the current buffer
        temperature. Integration stops while the output is saturated in the direction
        of the error.
        """
        proportional = self._config.kp * error
        raw = (proportional + self._integral + feedforward) * gain_scale
        saturated = (raw >= 100.0 and error > 0) or (raw <= 0.0 and error < 0)
        if not saturated and dt_s > 0:
            config = self._config
            rate = config.ki * (config.boost_factor if abs(error) > config.boost_error else 1.0)
            self._integral = self._clamp_integral(self._integral + rate * error * dt_s)
            raw = (proportional + self._integral + feedforward) * gain_scale
        duty = min(100.0, max(0.0, raw))
        self._last = PidOutput(error, proportional, self._integral, feedforward, duty)
        return self._last

    def _clamp_integral(self, value: float) -> float:
        return min(self._config.integral_max, max(self._config.integral_min, value))
