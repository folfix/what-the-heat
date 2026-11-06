"""Turns a duty cycle into valve open and closed periods."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CycleConfig:
    """Timing of the valve."""

    # Demand is only looked at when a cycle starts, so a longer cycle leaves a room cooling
    # behind a closed valve for longer. The length therefore does not depend on the duty.
    cycle_s: float = 30 * 60.0
    # An actuator takes 2 to 3 minutes to move, so a shorter pulse passes little or no water.
    min_on_s: float = 5 * 60.0
    min_off_s: float = 5 * 60.0


class CycleScheduler:
    """Decides whether the valve should be open, one cycle at a time.

    On-time that is too short to run is carried over to the next cycle, so low duties
    are still delivered on average. Large demand changes may interrupt a cycle, but only
    after the minimum open or closed time has passed.
    """

    def __init__(self, config: CycleConfig | None = None, start_s: float = 0.0, carry_s: float = 0.0) -> None:
        self._config = config or CycleConfig()
        self._cycle_end_s = start_s
        self._off_at_s = float("-inf")
        self._state_since_s = start_s
        self._is_open = False
        self._carry_s = carry_s

    @property
    def is_open(self) -> bool:
        """Return the state decided by the last step."""
        return self._is_open

    @property
    def carry_s(self) -> float:
        """Return the on-time carried over to the next cycle, in seconds."""
        return self._carry_s

    def reset_carry(self) -> None:
        """Forget the on-time owed from earlier cycles. The running cycle carries on."""
        self._carry_s = 0.0

    def step(self, now_s: float, duty_percent: float) -> bool:
        """Return True if the valve should be open at now_s."""
        if now_s >= self._cycle_end_s or self._demand_interrupts(now_s, duty_percent):
            self._plan(now_s, duty_percent)
        should_open = now_s < self._off_at_s
        if should_open != self._is_open:
            self._is_open = should_open
            self._state_since_s = now_s
        return should_open

    def _demand_interrupts(self, now_s: float, duty_percent: float) -> bool:
        in_state_s = now_s - self._state_since_s
        if self._is_open:
            return duty_percent <= 0.0 and in_state_s >= self._config.min_on_s
        return duty_percent >= 100.0 and in_state_s >= self._config.min_off_s

    def _plan(self, now_s: float, duty_percent: float) -> None:
        config = self._config
        duty_percent = min(100.0, max(0.0, duty_percent))
        length = config.cycle_s
        wanted = duty_percent / 100.0 * length + self._carry_s
        if duty_percent <= 0.0 or wanted < config.min_on_s:
            on_time = 0.0
        elif duty_percent >= 100.0 or wanted > length - config.min_off_s:
            on_time = length
        else:
            on_time = wanted
        self._carry_s = max(-config.min_on_s, min(config.min_on_s, wanted - on_time))
        self._off_at_s = now_s + on_time
        self._cycle_end_s = now_s + length
