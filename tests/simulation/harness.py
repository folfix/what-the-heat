"""Runs one room with its thermostat, actuator and, optionally, the zone runner."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from custom_components.what_the_heat.core.runner import (
    CommandKind,
    Mode,
    Problem,
    RunnerConfig,
    ThermostatReading,
    ZoneRunner,
)
from custom_components.what_the_heat.core.valve import WatchdogConfig
from custom_components.what_the_heat.core.zone import ZoneConfig, ZoneStatus

from .plant import Actuator, Room, RoomParameters, Thermostat

STEP_S = 60.0
DAY_S = 86400.0


@dataclass(frozen=True)
class Environment:
    """Conditions around the room. The real water moves around the setpoint the controller assumes."""

    water_setpoint: float = 34.0
    water_ripple: float = 1.5
    water_ripple_period_s: float = 3 * 3600.0
    hot_water_sag: float = 3.0
    hot_water_starts_h: tuple[float, ...] = (6.0, 15.0)
    hot_water_half_duration_h: float = 0.75
    outdoor_mean: float = 3.0
    outdoor_swing: float = 3.0
    ground: float = 11.0

    def outdoor(self, now_s: float) -> float:
        hour = (now_s / 3600.0) % 24.0
        return self.outdoor_mean + self.outdoor_swing * math.sin(2.0 * math.pi * (hour - 9.0) / 24.0)

    def water(self, now_s: float) -> float:
        phase = (now_s / self.water_ripple_period_s) % 1.0
        value = self.water_setpoint + self.water_ripple * (2.0 * phase - 1.0)
        hour = (now_s / 3600.0) % 24.0
        half = self.hot_water_half_duration_h
        for start in self.hot_water_starts_h:
            if start <= hour < start + half:
                value -= self.hot_water_sag * (hour - start) / half
            elif start + half <= hour < start + 2.0 * half:
                value -= self.hot_water_sag * (1.0 - (hour - start - half) / half)
        return value


@dataclass(frozen=True)
class Faults:
    """Things that go wrong during a run. Periods are (start_s, end_s)."""

    lost_write_probability: float = 0.0
    reading_gap: tuple[float, float] | None = None
    controller_outage: tuple[float, float] | None = None
    seed: int = 1


@dataclass
class Result:
    """Measured behaviour. Only `floor_swing` needs a value that a real installation cannot measure."""

    within_band_pct: float = 0.0
    rms: float = 0.0
    low: float = 0.0
    high: float = 0.0
    first_days_high: float = 0.0
    mean_duty: float = 0.0
    valve_cycles_per_day: float = 0.0
    writes_per_day: float = 0.0
    shortest_open_s: float = 0.0
    shortest_closed_s: float = 0.0
    longest_closed_s: float = 0.0
    floor_swing: float = 0.0
    wrong_setpoint_s: float = 0.0
    resends: int = 0
    alerts: int = 0
    final_air: float = 0.0
    reached_target_s: float | None = None
    statuses: set[ZoneStatus] = field(default_factory=set)


def simulate(
    parameters: RoomParameters,
    environment: Environment,
    target: float = 20.0,
    zone_config: ZoneConfig | None = None,
    use_controller: bool = True,
    days: float = 14.0,
    settle_days: float = 4.0,
    faults: Faults | None = None,
    initial_air: float = 19.1,
    initial_floor: float | None = None,
    initial_wall: float | None = None,
    initial_integral: float = 30.0,
    band: float = 0.3,
    observe_days: float = 0.0,
    assumed_water: float | None = None,
    reset_learning_at_s: float | None = None,
) -> Result:
    """Run the room and return what happened after the settling period.

    With observe_days the room first runs on the plain thermostat, with the runner in
    observe mode, and the runner then takes over. In that case settle_days counts from
    the takeover. With assumed_water the controller believes in a water temperature
    other than the real setpoint. With reset_learning_at_s the owner presses the reset
    button at that moment.
    """
    faults = faults or Faults()
    rng = random.Random(faults.seed)
    room = Room(
        parameters,
        air=initial_air,
        floor=initial_air + 2.0 if initial_floor is None else initial_floor,
        wall=initial_air - 2.0 if initial_wall is None else initial_wall,
    )
    thermostat = Thermostat(setpoint=target)
    actuator = Actuator()
    config = RunnerConfig(
        zone=zone_config or ZoneConfig(target=target),
        watchdog=WatchdogConfig(differential=thermostat.differential),
    )
    runner = None
    if use_controller:
        start_mode = Mode.OBSERVE if observe_days > 0 else Mode.ACTIVE
        runner = ZoneRunner(config, start_mode, integral=initial_integral if observe_days <= 0 else 0.0)
    result = Result()
    samples: list[float] = []
    floors: list[float] = []
    duty_sum = 0.0
    duty_count = 0
    relay_was = False
    settle_s = (observe_days + settle_days) * DAY_S
    relay_since_s = settle_s
    open_periods: list[float] = []
    closed_periods: list[float] = []
    writes_at_settle = 0
    first_days_high = -math.inf
    total_days = observe_days + days
    takeover_s = observe_days * DAY_S

    for index in range(int(total_days * DAY_S / STEP_S)):
        now_s = index * STEP_S
        air = room.air
        temperature = thermostat.read(air)
        in_outage = faults.controller_outage is not None and faults.controller_outage[0] <= now_s < faults.controller_outage[1]
        if runner is not None and not in_outage:
            if runner.mode is Mode.OBSERVE and now_s >= takeover_s:
                runner.set_mode(Mode.ACTIVE)
            if reset_learning_at_s is not None and now_s >= reset_learning_at_s:
                runner.reset_learning()
                reset_learning_at_s = None
            gap = faults.reading_gap is not None and faults.reading_gap[0] <= now_s < faults.reading_gap[1]
            step = runner.step(
                now_s,
                ThermostatReading(
                    temperature=None if gap else temperature,
                    setpoint=thermostat.setpoint,
                    hvac_mode="heat",
                    hvac_action="heating" if thermostat.heating else "idle",
                    hvac_modes=("off", "heat"),
                ),
                environment.water_setpoint if assumed_water is None else assumed_water,
            )
            result.statuses.add(step.decision.status)
            result.resends = step.resends
            result.alerts += Problem.THERMOSTAT_NOT_FOLLOWING in step.problems
            if now_s >= takeover_s:
                duty_sum += step.decision.duty
                duty_count += 1
            for command in step.commands:
                if command.kind is CommandKind.SET_TEMPERATURE and rng.random() >= faults.lost_write_probability:
                    thermostat.setpoint = command.temperature
            if runner.commanded is not None and thermostat.setpoint != runner.commanded:
                result.wrong_setpoint_s += STEP_S
        relay = thermostat.step(air)
        flow = actuator.step(STEP_S, relay)
        room.step(STEP_S, flow, environment.water(now_s), environment.outdoor(now_s), environment.ground)
        if result.reached_target_s is None and room.air >= target - band:
            result.reached_target_s = now_s
        if now_s < settle_s:
            if now_s >= takeover_s:
                first_days_high = max(first_days_high, room.air)
            writes_at_settle = step.writes if runner is not None and not in_outage else writes_at_settle
            continue
        samples.append(room.air)
        floors.append(room.floor)
        if relay != relay_was:
            (closed_periods if relay else open_periods).append(now_s - relay_since_s)
            relay_since_s = now_s
            relay_was = relay

    span_days = days - settle_days
    count = len(samples)
    writes = step.writes if runner is not None else 0
    result.within_band_pct = sum(1 for value in samples if abs(value - target) <= band) / count * 100.0
    result.rms = math.sqrt(sum((value - target) ** 2 for value in samples) / count)
    result.low = min(samples)
    result.high = max(samples)
    result.first_days_high = first_days_high
    result.mean_duty = duty_sum / duty_count if duty_count else 0.0
    result.valve_cycles_per_day = len(open_periods) / span_days
    result.writes_per_day = (writes - writes_at_settle) / span_days
    # The first period started before measuring, so it may be cut short.
    result.shortest_open_s = min(open_periods[1:], default=0.0)
    result.shortest_closed_s = min(closed_periods[1:], default=0.0)
    result.longest_closed_s = max(closed_periods, default=0.0)
    result.floor_swing = max(floors) - min(floors)
    result.final_air = room.air
    return result
