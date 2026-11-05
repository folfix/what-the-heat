"""Whole-loop checks for the pilot room. Room data is assumed, so these guard behaviour and predict nothing."""

import unittest

from custom_components.what_the_heat.core.zone import ZoneStatus
from tests.simulation.harness import DAY_S, Environment, Faults, simulate
from tests.simulation.pilot import ROOMS, TARGET

MINIMUM_RUN_S = 12 * 60.0 - 60.0  # one simulation step of tolerance


class PilotRoomTest(unittest.TestCase):
    def test_controller_holds_the_target_in_reachable_conditions(self) -> None:
        for label, (parameters, ground) in ROOMS.items():
            for buffer in (34.0, 38.0):
                with self.subTest(room=label, buffer=buffer):
                    result = simulate(parameters, Environment(buffer_setpoint=buffer, ground=ground), TARGET)
                    self.assertGreaterEqual(result.within_band_pct, 90.0)

    def test_controller_beats_the_thermostat(self) -> None:
        for label, (parameters, ground) in ROOMS.items():
            with self.subTest(room=label):
                environment = Environment(buffer_setpoint=34.0, ground=ground)
                controlled = simulate(parameters, environment, TARGET)
                plain = simulate(parameters, environment, TARGET, use_controller=False)
                self.assertLess(controlled.rms, plain.rms)
                self.assertLess(controlled.longest_closed_s, plain.longest_closed_s)

    def test_valve_cycles_respect_the_minimum_times(self) -> None:
        for label, (parameters, ground) in ROOMS.items():
            for buffer in (34.0, 38.0):
                with self.subTest(room=label, buffer=buffer):
                    result = simulate(parameters, Environment(buffer_setpoint=buffer, ground=ground), TARGET)
                    self.assertGreaterEqual(result.shortest_open_s, MINIMUM_RUN_S)
                    self.assertGreaterEqual(result.shortest_closed_s, MINIMUM_RUN_S)

    def test_start_from_the_current_temperature_does_not_overshoot_much(self) -> None:
        parameters, ground = ROOMS["reference"]
        result = simulate(parameters, Environment(buffer_setpoint=38.0, ground=ground), TARGET)
        self.assertLess(result.first_days_high, TARGET + 0.5)

    def test_cold_start_after_days_without_heating(self) -> None:
        # Floor at air temperature and colder walls, no learned integral yet.
        for label, (parameters, ground) in ROOMS.items():
            for buffer in (34.0, 38.0):
                for air in (19.0, 16.0, 13.0):
                    with self.subTest(room=label, buffer=buffer, air=air):
                        environment = Environment(buffer_setpoint=buffer, ground=ground)
                        start = {"initial_air": air, "initial_floor": air, "initial_wall": air - 1.0}
                        controlled = simulate(parameters, environment, TARGET, initial_integral=0.0, **start)
                        self.assertIsNotNone(controlled.reached_target_s)
                        self.assertLess(controlled.first_days_high, TARGET + 0.8)
                        self.assertGreaterEqual(controlled.within_band_pct, 90.0)

    def test_cold_start_is_about_as_fast_as_the_thermostat(self) -> None:
        parameters, ground = ROOMS["reference"]
        environment = Environment(buffer_setpoint=34.0, ground=ground)
        start = {"initial_air": 16.0, "initial_floor": 16.0, "initial_wall": 15.0}
        controlled = simulate(parameters, environment, TARGET, initial_integral=0.0, **start)
        plain = simulate(parameters, environment, TARGET, use_controller=False, **start)
        self.assertLess(controlled.reached_target_s, plain.reached_target_s + 6 * 3600.0)

    def test_unreachable_target_saturates_without_alarm_from_the_watchdog(self) -> None:
        parameters, ground = ROOMS["high losses"]
        result = simulate(parameters, Environment(buffer_setpoint=30.0, ground=ground), TARGET)
        self.assertGreater(result.mean_duty, 95.0)
        self.assertEqual(result.alerts, 0)


class PilotFaultTest(unittest.TestCase):
    def setUp(self) -> None:
        self.parameters, ground = ROOMS["reference"]
        self.environment = Environment(buffer_setpoint=34.0, ground=ground)

    def test_lost_commands_are_recovered(self) -> None:
        result = simulate(self.parameters, self.environment, TARGET, faults=Faults(lost_write_probability=0.2))
        self.assertGreater(result.resends, 0)
        self.assertGreaterEqual(result.within_band_pct, 90.0)
        self.assertLess(result.wrong_setpoint_s, 0.05 * 14 * DAY_S)

    def test_no_resends_when_everything_works(self) -> None:
        result = simulate(self.parameters, self.environment, TARGET)
        self.assertEqual(result.resends, 0)
        self.assertEqual(result.wrong_setpoint_s, 0.0)

    def test_missing_readings_hand_control_back(self) -> None:
        gap = (6 * DAY_S, 6 * DAY_S + 3 * 3600.0)
        result = simulate(self.parameters, self.environment, TARGET, faults=Faults(reading_gap=gap))
        self.assertIn(ZoneStatus.DEGRADED, result.statuses)
        self.assertIn(ZoneStatus.HANDBACK, result.statuses)
        self.assertGreater(result.low, TARGET - 0.7)
        self.assertLess(result.high, TARGET + 0.7)

    def test_controller_outage_stays_inside_the_setpoint_band(self) -> None:
        # Two days without any control. Starting times differ, so both valve states get covered.
        for start_h in range(0, 90, 15):
            with self.subTest(start_h=start_h):
                start = 6 * DAY_S + start_h * 3600.0
                outage = (start, start + 2 * DAY_S)
                result = simulate(self.parameters, self.environment, TARGET, faults=Faults(controller_outage=outage))
                self.assertGreater(result.low, TARGET - 2.5)
                self.assertLess(result.high, TARGET + 2.5)


if __name__ == "__main__":
    unittest.main()
