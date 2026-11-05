import unittest

from custom_components.what_the_heat.core.runner import (
    Command,
    CommandKind,
    Mode,
    Problem,
    RunnerConfig,
    ThermostatReading,
    ZoneRunner,
)
from custom_components.what_the_heat.core.valve import ValveConfig
from custom_components.what_the_heat.core.zone import ZoneConfig, ZoneStatus

MINUTE = 60.0
HOUR = 3600.0
TARGET = 21.0
OPEN = TARGET + ValveConfig().band
CLOSED = TARGET - ValveConfig().band


def runner(mode: Mode = Mode.ACTIVE, **kwargs) -> ZoneRunner:
    return ZoneRunner(RunnerConfig(zone=ZoneConfig(target=TARGET)), mode, **kwargs)


def reading(temperature: float | None = 20.0, setpoint: float | None = CLOSED, **kwargs) -> ThermostatReading:
    defaults = {"hvac_mode": "heat", "hvac_action": "idle", "hvac_modes": ("off", "heat")}
    return ThermostatReading(temperature, setpoint, **{**defaults, **kwargs})


class ObserveModeTest(unittest.TestCase):
    def test_never_writes(self) -> None:
        zone = runner(Mode.OBSERVE)
        for minute in range(600):
            step = zone.step(minute * MINUTE, reading(temperature=18.0, setpoint=15.0, hvac_mode="off"))
            self.assertEqual(step.commands, ())
        self.assertEqual(step.writes, 0)

    def test_still_calculates(self) -> None:
        step = runner(Mode.OBSERVE).step(0.0, reading(temperature=19.0))
        self.assertGreater(step.decision.duty, 0.0)
        self.assertTrue(step.decision.valve_open)


class ActiveModeTest(unittest.TestCase):
    def test_cold_room_gets_the_open_setpoint(self) -> None:
        step = runner().step(0.0, reading(temperature=20.0, setpoint=15.0))
        self.assertEqual(step.commands, (Command(CommandKind.SET_TEMPERATURE, OPEN),))
        self.assertEqual(step.writes, 1)

    def test_warm_room_gets_the_closed_setpoint(self) -> None:
        step = runner().step(0.0, reading(temperature=22.0, setpoint=15.0))
        self.assertEqual(step.commands, (Command(CommandKind.SET_TEMPERATURE, CLOSED),))

    def test_no_write_when_the_device_already_has_the_setpoint(self) -> None:
        step = runner().step(0.0, reading(temperature=22.0, setpoint=CLOSED))
        self.assertEqual(step.commands, ())
        self.assertEqual(step.writes, 0)

    def test_setpoint_is_written_once_per_change(self) -> None:
        zone = runner()
        total = 0
        for minute in range(30):
            step = zone.step(minute * MINUTE, reading(temperature=20.0, setpoint=OPEN, hvac_action="heating"))
            total += len(step.commands)
        self.assertEqual(total, 0)

    def test_nothing_is_written_before_the_first_reading(self) -> None:
        step = runner().step(0.0, reading(temperature=None, setpoint=CLOSED))
        self.assertIs(step.decision.status, ZoneStatus.INITIALIZING)
        self.assertEqual(step.commands, ())

    def test_unavailable_thermostat_gets_no_commands(self) -> None:
        step = runner().step(0.0, ThermostatReading())
        self.assertEqual(step.commands, ())

    def test_lost_command_is_sent_again(self) -> None:
        zone = runner()
        zone.step(0.0, reading(temperature=20.0, setpoint=15.0))
        step = zone.step(2 * MINUTE, reading(temperature=20.0, setpoint=15.0))
        self.assertEqual(step.commands, (Command(CommandKind.SET_TEMPERATURE, OPEN),))
        self.assertEqual(step.resends, 1)

    def test_repeated_mismatches_raise_a_problem_that_clears(self) -> None:
        zone = runner()
        now = 0.0
        zone.step(now, reading(temperature=20.0, setpoint=15.0))
        for _ in range(3):
            now += 2 * MINUTE
            step = zone.step(now, reading(temperature=20.0, setpoint=15.0))
        self.assertIn(Problem.THERMOSTAT_NOT_FOLLOWING, step.problems)
        now += 2 * MINUTE
        step = zone.step(now, reading(temperature=20.0, setpoint=OPEN, hvac_action="heating"))
        self.assertNotIn(Problem.THERMOSTAT_NOT_FOLLOWING, step.problems)

    def test_thermostat_that_is_off_gets_switched_on(self) -> None:
        step = runner().step(0.0, reading(temperature=20.0, setpoint=OPEN, hvac_mode="off", hvac_action="off"))
        self.assertIn(Command(CommandKind.SET_HEAT_MODE), step.commands)

    def test_thermostat_that_is_off_without_a_setpoint_gets_switched_on(self) -> None:
        step = runner().step(0.0, reading(temperature=20.0, setpoint=None, hvac_mode="off", hvac_action="off"))
        self.assertEqual(
            step.commands,
            (Command(CommandKind.SET_HEAT_MODE), Command(CommandKind.SET_TEMPERATURE, OPEN)),
        )

    def test_heat_mode_command_is_rate_limited(self) -> None:
        zone = runner()
        off = reading(temperature=20.0, setpoint=OPEN, hvac_mode="off", hvac_action="off")
        zone.step(0.0, off)
        step = zone.step(MINUTE, off)
        self.assertNotIn(Command(CommandKind.SET_HEAT_MODE), step.commands)
        step = zone.step(5 * MINUTE, off)
        self.assertIn(Command(CommandKind.SET_HEAT_MODE), step.commands)

    def test_summer_mode_thermostat_is_left_alone(self) -> None:
        cooling_only = reading(temperature=20.0, setpoint=15.0, hvac_mode="cool", hvac_modes=("off", "cool"))
        step = runner().step(0.0, cooling_only)
        self.assertEqual(step.commands, ())
        self.assertIn(Problem.THERMOSTAT_CANNOT_HEAT, step.problems)

    def test_device_limits_are_respected(self) -> None:
        step = runner().step(0.0, reading(temperature=20.0, setpoint=15.0, max_temp=22.0, setpoint_step=0.5))
        self.assertEqual(step.commands, (Command(CommandKind.SET_TEMPERATURE, 21.5),))

    def test_missing_readings_hand_back_the_target(self) -> None:
        zone = runner()
        zone.step(0.0, reading(temperature=20.0, setpoint=OPEN, hvac_action="heating"))
        step = zone.step(HOUR, reading(temperature=None, setpoint=OPEN))
        self.assertIs(step.decision.status, ZoneStatus.HANDBACK)
        self.assertIn(Problem.READINGS_MISSING, step.problems)
        self.assertEqual(step.commands, (Command(CommandKind.SET_TEMPERATURE, TARGET),))

    def test_target_change_moves_the_setpoint(self) -> None:
        zone = runner()
        zone.step(0.0, reading(temperature=20.0, setpoint=OPEN, hvac_action="heating"))
        zone.target = 21.5
        step = zone.step(MINUTE, reading(temperature=20.0, setpoint=OPEN, hvac_action="heating"))
        self.assertEqual(step.commands, (Command(CommandKind.SET_TEMPERATURE, OPEN + 0.5),))


class HandbackModeTest(unittest.TestCase):
    def test_target_is_written_once_and_the_thermostat_left_alone(self) -> None:
        zone = runner(Mode.HANDBACK)
        first = zone.step(0.0, reading(temperature=20.0, setpoint=OPEN, hvac_action="heating"))
        self.assertEqual(first.commands, (Command(CommandKind.SET_TEMPERATURE, TARGET),))
        for minute in range(1, 100):
            step = zone.step(minute * MINUTE, reading(temperature=20.0, setpoint=TARGET, hvac_action="heating"))
            self.assertEqual(step.commands, ())

    def test_thermostat_that_was_switched_off_stays_off(self) -> None:
        step = runner(Mode.HANDBACK).step(0.0, reading(temperature=20.0, setpoint=TARGET, hvac_mode="off", hvac_action="off"))
        self.assertNotIn(Command(CommandKind.SET_HEAT_MODE), step.commands)


class ModeChangeTest(unittest.TestCase):
    def _observed(self, temperature: float, heating_every: int) -> ZoneRunner:
        zone = runner(Mode.OBSERVE)
        for minute in range(60 * 48):
            action = "heating" if minute % heating_every == 0 else "idle"
            zone.step(minute * MINUTE, reading(temperature=temperature, setpoint=TARGET, hvac_action=action), 34.0)
        return zone

    def test_integral_starts_from_recent_heating_near_the_target(self) -> None:
        zone = self._observed(TARGET, heating_every=4)
        zone.set_mode(Mode.ACTIVE)
        self.assertGreater(zone.snapshot()["integral"], 10.0)
        self.assertLess(zone.snapshot()["integral"], 60.0)

    def test_cold_room_starts_from_zero(self) -> None:
        zone = self._observed(TARGET - 3.0, heating_every=1)
        zone.set_mode(Mode.ACTIVE)
        self.assertEqual(zone.snapshot()["integral"], 0.0)

    def test_too_little_observation_starts_from_zero(self) -> None:
        zone = runner(Mode.OBSERVE)
        zone.step(0.0, reading(temperature=TARGET, setpoint=TARGET, hvac_action="heating"))
        zone.set_mode(Mode.ACTIVE)
        self.assertEqual(zone.snapshot()["integral"], 0.0)

    def test_going_active_takes_over_from_the_thermostat(self) -> None:
        zone = runner(Mode.OBSERVE)
        zone.step(0.0, reading(temperature=20.0, setpoint=TARGET))
        zone.set_mode(Mode.ACTIVE)
        step = zone.step(MINUTE, reading(temperature=20.0, setpoint=TARGET))
        self.assertEqual(step.commands, (Command(CommandKind.SET_TEMPERATURE, OPEN),))

    def test_state_survives_a_restart(self) -> None:
        zone = runner(Mode.ACTIVE, integral=33.0, writes=5, learned_s=7200.0)
        state = zone.snapshot()
        restored = ZoneRunner(
            RunnerConfig(zone=ZoneConfig(target=state["target"])),
            Mode(state["mode"]),
            integral=state["integral"],
            carry_s=state["carry_s"],
            heating_share=state["heating_share"],
            observed_s=state["observed_s"],
            writes=state["writes"],
            learned_s=state["learned_s"],
        )
        self.assertEqual(restored.snapshot(), state)


class LearningTest(unittest.TestCase):
    def _run(self, zone: ZoneRunner, hours: float, temperature: float, water: float = 34.0, start_s: float = 0.0) -> None:
        for minute in range(int(hours * 60) + 1):
            zone.step(start_s + minute * MINUTE, reading(temperature=temperature, setpoint=TARGET), water)

    def test_nothing_is_known_at_first(self) -> None:
        learned = runner().learned()
        self.assertIsNone(learned.demand)
        self.assertEqual(learned.hours, 0.0)
        self.assertIsNone(learned.recent_heating)

    def test_demand_comes_from_the_controller_while_active(self) -> None:
        zone = runner(Mode.ACTIVE, integral=30.0, learned_s=7 * HOUR)
        zone.step(0.0, reading(temperature=TARGET), 34.0)
        learned = zone.learned()
        self.assertEqual(learned.source, "controller")
        self.assertAlmostEqual(learned.demand, 30.0)
        self.assertAlmostEqual(learned.hours, 7.0)

    def test_colder_water_needs_a_longer_opening(self) -> None:
        zone = runner(Mode.ACTIVE, integral=30.0, learned_s=7 * HOUR)
        zone.step(0.0, reading(temperature=TARGET), 28.0)
        self.assertAlmostEqual(zone.learned().demand, 75.0)

    def test_demand_never_exceeds_a_fully_open_valve(self) -> None:
        zone = runner(Mode.ACTIVE, integral=60.0, learned_s=7 * HOUR)
        zone.step(0.0, reading(temperature=TARGET), 28.0)
        self.assertEqual(zone.learned().demand, 100.0)

    def test_a_short_time_is_not_enough_to_show_a_demand(self) -> None:
        zone = runner(Mode.ACTIVE, integral=30.0, learned_s=5 * HOUR)
        zone.step(0.0, reading(temperature=TARGET), 34.0)
        self.assertIsNone(zone.learned().demand)

    def test_time_counts_while_the_controller_can_adjust_its_demand(self) -> None:
        zone = runner(Mode.ACTIVE)
        self._run(zone, 2.0, TARGET - 0.1)
        self.assertAlmostEqual(zone.learned().hours, 2.0)

    def test_a_cold_room_teaches_nothing(self) -> None:
        # Outside the setpoint band the thermostat acts on its own.
        zone = runner(Mode.ACTIVE)
        self._run(zone, 8.0, TARGET - 3.0)
        self.assertEqual(zone.learned().hours, 0.0)
        self.assertIsNone(zone.learned().demand)

    def test_time_with_a_saturated_output_teaches_nothing(self) -> None:
        zone = runner(Mode.ACTIVE)
        self._run(zone, 8.0, TARGET - 1.5)
        self.assertEqual(zone.learned().hours, 0.0)

    def test_a_long_gap_does_not_count_as_learning(self) -> None:
        zone = runner(Mode.ACTIVE)
        zone.step(0.0, reading(temperature=TARGET - 0.1), 34.0)
        zone.step(10 * HOUR, reading(temperature=TARGET - 0.1), 34.0)
        self.assertLess(zone.learned().hours, 0.1)

    def test_observing_uses_what_the_thermostat_has_been_doing(self) -> None:
        zone = runner(Mode.OBSERVE)
        for minute in range(60 * 48):
            action = "heating" if minute % 4 == 0 else "idle"
            zone.step(minute * MINUTE, reading(temperature=TARGET, setpoint=TARGET, hvac_action=action), 34.0)
        learned = zone.learned()
        self.assertEqual(learned.source, "thermostat")
        self.assertGreater(learned.demand, 20.0)
        self.assertLess(learned.demand, 40.0)
        self.assertAlmostEqual(learned.recent_heating, learned.demand)
        self.assertAlmostEqual(learned.hours, 48.0, delta=0.1)

    def test_observing_a_cold_room_shows_no_demand(self) -> None:
        zone = runner(Mode.OBSERVE)
        self._run(zone, 8.0, TARGET - 3.0)
        self.assertIsNone(zone.learned().demand)
        self.assertAlmostEqual(zone.learned().hours, 8.0)

    def test_taking_over_keeps_what_was_seen_of_the_thermostat(self) -> None:
        zone = runner(Mode.OBSERVE)
        for minute in range(60 * 48):
            action = "heating" if minute % 4 == 0 else "idle"
            zone.step(minute * MINUTE, reading(temperature=TARGET, setpoint=TARGET, hvac_action=action), 34.0)
        seen = zone.learned().demand
        zone.set_mode(Mode.ACTIVE)
        learned = zone.learned()
        self.assertEqual(learned.source, "controller")
        self.assertAlmostEqual(learned.demand, seen)
        self.assertAlmostEqual(learned.hours, 48.0, delta=0.1)

    def test_taking_over_a_cold_room_starts_from_nothing(self) -> None:
        zone = runner(Mode.OBSERVE, learned_s=9 * HOUR)
        self._run(zone, 8.0, TARGET - 3.0)
        zone.set_mode(Mode.ACTIVE)
        self.assertEqual(zone.learned().hours, 0.0)

    def test_reset_forgets_everything_learned(self) -> None:
        zone = runner(Mode.ACTIVE, integral=40.0, carry_s=120.0, heating_share=0.5, observed_s=9 * HOUR, learned_s=9 * HOUR)
        zone.reset_learning()
        state = zone.snapshot()
        self.assertEqual(state["integral"], 0.0)
        self.assertEqual(state["carry_s"], 0.0)
        self.assertIsNone(state["heating_share"])
        self.assertEqual(state["observed_s"], 0.0)
        self.assertEqual(state["learned_s"], 0.0)
        self.assertIsNone(zone.learned().demand)

    def test_reset_keeps_the_mode_target_and_counters(self) -> None:
        zone = runner(Mode.ACTIVE, integral=40.0, writes=5)
        before = zone.snapshot()
        zone.reset_learning()
        after = zone.snapshot()
        for key in ("mode", "target", "writes"):
            self.assertEqual(after[key], before[key])

    def test_reset_while_observing_writes_nothing(self) -> None:
        zone = runner(Mode.OBSERVE, integral=40.0)
        zone.step(0.0, reading(temperature=TARGET))
        zone.reset_learning()
        step = zone.step(MINUTE, reading(temperature=TARGET))
        self.assertEqual(step.commands, ())

    def test_after_a_reset_the_room_learns_again(self) -> None:
        zone = runner(Mode.ACTIVE, integral=40.0, learned_s=9 * HOUR)
        self._run(zone, 1.0, TARGET)
        zone.reset_learning()
        self._run(zone, 7.0, TARGET - 0.2, start_s=2 * HOUR)
        learned = zone.learned()
        self.assertAlmostEqual(learned.hours, 7.0, delta=0.1)
        self.assertGreater(learned.demand, 0.0)
        self.assertLess(learned.demand, 40.0)


if __name__ == "__main__":
    unittest.main()
