"""Exponential smoothing of irregularly sampled readings."""

from __future__ import annotations

import math


class ExponentialFilter:
    """First-order low-pass filter with a time constant in seconds."""

    def __init__(self, time_constant_s: float) -> None:
        if time_constant_s < 0:
            raise ValueError("time_constant_s must not be negative")
        self._time_constant_s = time_constant_s
        self._value: float | None = None

    @property
    def value(self) -> float | None:
        """Return the filtered value, or None before the first sample."""
        return self._value

    def reset(self) -> None:
        """Forget everything seen so far."""
        self._value = None

    def update(self, sample: float, dt_s: float) -> float:
        """Add a sample taken dt_s seconds after the previous one and return the new value."""
        if self._value is None or self._time_constant_s == 0:
            self._value = sample
        elif dt_s > 0:
            self._value += (sample - self._value) * (1.0 - math.exp(-dt_s / self._time_constant_s))
        return self._value
