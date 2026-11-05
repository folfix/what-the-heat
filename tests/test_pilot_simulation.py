"""Whole-loop checks for the pilot room. Room data is assumed, so these guard behaviour and predict nothing."""

import unittest

from custom_components.what_the_heat.core.valve import ValveConfig
from custom_components.what_the_heat.core.zone import ZoneStatus
from tests.simulation.harness import DAY_S, Environment, Faults, simulate
from tests.simulation.pilot import ROOMS, TARGET

MINIMUM_RUN_S = 12 * 60.0 - 60.0  # one simulation step of tolerance


class PilotRoomTest(unittest.TestCase):
    def test_controller_holds_the_target_in_reachable_conditions(self) -> None:
        for label, (parameters, ground) in ROOMS.items():
            for water in (34.0, 38.0):
                with self.subTest(room=label, water=water):
                    result = simulate(parameters, Environment(water_setpoint=water, ground=ground), TARGET)
                    self.assertGreaterEqual(result.within_band_pct, 90.0)

    def test_controller_beats_the_thermostat(self) -> None:
        for label, (parameters, ground) in ROOMS.items():
            with self.subTest(room=label):
                environment = Environment(water_setpoint=34.0, ground=ground)
                controlled = simulate(parameters, environment, TARGET)
                plain = simulate(parameters, environment, TARGET, use_controller=False)
                self.assertLess(controlled.rms, plain.rms)
                self.assertLess(controlled.longest_closed_s, plain.longest_closed_s)

    def test_valve_cycles_respect_the_minimum_times(self) -> None:
        for label, (parameters, ground) in ROOMS.items():
            for water in (34.0, 38.0):
                with self.subTest(room=label, water=water):
                    result = simulate(parameters, Environment(water_setpoint=water, ground=ground), TARGET)
                    self.assertGreaterEqual(result.shortest_open_s, MINIMUM_RUN_S)
                    self.assertGreaterEqual(result.shortest_closed_s, MINIMUM_RUN_S)

    def test_start_from_the_current_temperature_does_not_overshoot_much(self) -> None:
        parameters, ground = ROOMS["reference"]
        result = simulate(parameters, Environment(water_setpoint=38.0, ground=ground), TARGET)
        self.assertLess(result.first_days_high, TARGET + 0.5)

    def test_cold_start_after_days_without_heating(self) -> None:
        # Floor at air temperature and colder walls, no learned integral yet.
        for label, (parameters, ground) in ROOMS.items():
            for water in (34.0, 38.0):
                for air in (19.0, 16.0, 13.0):
                    with self.subTest(room=label, water=water, air=air):
                        environment = Environment(water_setpoint=water, ground=ground)
                        start = {"initial_air": air, "initial_floor": air, "initial_wall": air - 1.0}
                        controlled = simulate(parameters, environment, TARGET, initial_integral=0.0, **start)
                        self.assertIsNotNone(controlled.reached_target_s)
                        self.assertLess(controlled.first_days_high, TARGET + 0.8)
                        self.assertGreaterEqual(controlled.within_band_pct, 90.0)

    def test_cold_start_is_about_as_fast_as_the_thermostat(self) -> None:
        parameters, ground = ROOMS["reference"]
        environment = Environment(water_setpoint=34.0, ground=ground)
        start = {"initial_air": 16.0, "initial_floor": 16.0, "initial_wall": 15.0}
        controlled = simulate(parameters, environment, TARGET, initial_integral=0.0, **start)
        plain = simulate(parameters, environment, TARGET, use_controller=False, **start)
        self.assertLess(controlled.reached_target_s, plain.reached_target_s + 6 * 3600.0)

    def test_taking_over_from_the_thermostat_is_smooth(self) -> None:
        # The runner first watches the thermostat for 3 days, then takes over.
        for label, (parameters, ground) in ROOMS.items():
            with self.subTest(room=label):
                environment = Environment(water_setpoint=34.0, ground=ground)
                result = simulate(parameters, environment, TARGET, initial_air=TARGET, observe_days=3.0)
                self.assertGreaterEqual(result.within_band_pct, 90.0)
                self.assertLess(result.first_days_high, TARGET + 0.6)

    def test_a_reset_costs_a_temporary_dip_and_the_room_recovers(self) -> None:
        for label, (parameters, ground) in ROOMS.items():
            environment = Environment(water_setpoint=34.0, ground=ground)
            for hour in (0, 9, 17):
                with self.subTest(room=label, hour=hour):
                    result = simulate(parameters, environment, TARGET, reset_learning_at_s=6.5 * DAY_S + hour * 3600.0)
                    self.assertGreater(result.low, TARGET - 2.0)
                    self.assertLess(result.high, TARGET + 1.0)
                    self.assertLess(abs(result.final_air - TARGET), 0.4)

    def test_small_error_in_the_assumed_water_is_tolerated(self) -> None:
        for label, (parameters, ground) in ROOMS.items():
            for error in (-2.0, 2.0):
                with self.subTest(room=label, error=error):
                    environment = Environment(water_setpoint=34.0, ground=ground)
                    result = simulate(parameters, environment, TARGET, assumed_water=34.0 + error, days=21.0, settle_days=7.0)
                    self.assertGreaterEqual(result.within_band_pct, 90.0)

    def test_unreachable_target_saturates_without_alarm_from_the_watchdog(self) -> None:
        parameters, ground = ROOMS["high losses"]
        result = simulate(parameters, Environment(water_setpoint=30.0, ground=ground), TARGET)
        self.assertGreater(result.mean_duty, 95.0)
        self.assertEqual(result.alerts, 0)


class PilotFaultTest(unittest.TestCase):
    def setUp(self) -> None:
        self.parameters, ground = ROOMS["reference"]
        self.environment = Environment(water_setpoint=34.0, ground=ground)

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
                limit = ValveConfig().band + 0.5
                self.assertGreater(result.low, TARGET - limit)
                self.assertLess(result.high, TARGET + limit)


if __name__ == "__main__":
    unittest.main()
