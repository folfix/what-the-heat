"""Uses a thermostat setpoint as a valve, and verifies that the thermostat follows it."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class ValveConfig:
    """Setpoint band and device limits."""

    band: float = 2.0
    setpoint_step: float = 0.5
    device_min: float = 5.0
    device_max: float = 35.0
    differential: float = 0.3

    @property
    def authority(self) -> float:
        """Return how far from the target the controller still decides over the thermostat."""
        return self.band - self.differential


def _round_to_step(value: float, step: float) -> float:
    return round(value / step) * step


def open_setpoint(target: float, config: ValveConfig) -> float:
    """Return the setpoint that makes the thermostat open the valve.

    It stays one step below the device maximum, since some integrations reject the
    exact maximum.
    """
    setpoint = _round_to_step(target + config.band, config.setpoint_step)
    return min(setpoint, config.device_max - config.setpoint_step)


def closed_setpoint(target: float, config: ValveConfig) -> float:
    """Return the setpoint that makes the thermostat close the valve."""
    setpoint = _round_to_step(target - config.band, config.setpoint_step)
    return max(setpoint, config.device_min)


class WatchdogResult(Enum):
    """Outcome of a watchdog check."""

    OK = "ok"
    RESEND = "resend"
    ALERT = "alert"


@dataclass(frozen=True)
class WatchdogConfig:
    """Timing of the checks."""

    check_interval_s: float = 5 * 60.0
    grace_s: float = 2 * 60.0
    alert_after: int = 3
    differential: float = 0.3
    action_margin: float = 0.2


class ValveWatchdog:
    """Compares the commanded setpoint with what the thermostat later reports.

    A setpoint read right after a write may only be an optimistic value held by the
    integration, so reads within the grace period are ignored, and the reported heating
    state is checked as well. The commanded setpoint is kept here, separately from
    anything read back from the device.
    """

    def __init__(self, config: WatchdogConfig | None = None) -> None:
        self._config = config or WatchdogConfig()
        self._commanded: float | None = None
        self._commanded_at_s = 0.0
        self._next_check_s = 0.0
        self._mismatches = 0

    @property
    def commanded(self) -> float | None:
        """Return the setpoint most recently commanded."""
        return self._commanded

    @property
    def mismatches(self) -> int:
        """Return the number of consecutive failed checks."""
        return self._mismatches

    def command(self, now_s: float, setpoint: float) -> None:
        """Record that a setpoint was sent to the thermostat."""
        if setpoint != self._commanded:
            self._mismatches = 0
        self._commanded = setpoint
        self._commanded_at_s = now_s
        self._next_check_s = now_s + self._config.grace_s

    def check(
        self,
        now_s: float,
        reported_setpoint: float | None,
        is_heating: bool | None,
        room_temperature: float | None,
    ) -> WatchdogResult:
        """Return what to do about the thermostat's reported state."""
        if self._commanded is None or now_s < self._next_check_s:
            return WatchdogResult.OK
        self._next_check_s = now_s + self._config.check_interval_s
        if self._matches(reported_setpoint, is_heating, room_temperature):
            self._mismatches = 0
            return WatchdogResult.OK
        self._mismatches += 1
        if self._mismatches >= self._config.alert_after:
            return WatchdogResult.ALERT
        return WatchdogResult.RESEND

    def _matches(
        self,
        reported_setpoint: float | None,
        is_heating: bool | None,
        room_temperature: float | None,
    ) -> bool:
        if reported_setpoint is None or abs(reported_setpoint - self._commanded) > 0.01:
            return False
        if is_heating is None or room_temperature is None:
            return True
        margin = self._config.action_margin
        if room_temperature <= self._commanded - self._config.differential - margin:
            return is_heating
        if room_temperature >= self._commanded + margin:
            return not is_heating
        return True
