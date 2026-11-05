import unittest

from custom_components.what_the_heat.core.pid import PidConfig
from custom_components.what_the_heat.core.zone import ZoneConfig, ZoneController, ZoneStatus

MINUTE = 60.0


class ZoneControllerTest(unittest.TestCase):
    def test_before_the_first_reading_the_thermostat_keeps_control(self) -> None:
        decision = ZoneController(ZoneConfig(target=20.0)).step(0.0, None)
        self.assertIs(decision.status, ZoneStatus.INITIALIZING)
        self.assertEqual(decision.setpoint, 20.0)

    def test_cold_room_opens_the_valve(self) -> None:
        decision = ZoneController(ZoneConfig(target=20.0)).step(0.0, 18.0)
        self.assertIs(decision.status, ZoneStatus.NORMAL)
        self.assertTrue(decision.valve_open)
        self.assertEqual(decision.setpoint, 23.0)

    def test_warm_room_closes_the_valve(self) -> None:
        decision = ZoneController(ZoneConfig(target=20.0)).step(0.0, 22.0)
        self.assertFalse(decision.valve_open)
        self.assertEqual(decision.setpoint, 17.0)

    def test_hotter_water_gives_less_duty(self) -> None:
        config = ZoneConfig(target=20.0, pid=PidConfig(kp=50.0, ki=0.0))
        cool = ZoneController(config).step(0.0, 19.8, water_temperature=30.0)
        hot = ZoneController(config).step(0.0, 19.8, water_temperature=38.0)
        self.assertGreater(cool.duty, hot.duty)

    def test_smoothing_ignores_a_short_spike(self) -> None:
        controller = ZoneController(ZoneConfig(target=20.0, pid=PidConfig(kp=50.0, ki=0.0)))
        controller.step(0.0, 20.0)
        decision = controller.step(MINUTE, 25.0)
        self.assertLess(decision.temperature, 20.6)

    def test_missing_readings_hold_the_duty_then_hand_back(self) -> None:
        controller = ZoneController(ZoneConfig(target=20.0))
        duty = controller.step(0.0, 19.5).duty
        short = controller.step(10 * MINUTE, None)
        self.assertIs(short.status, ZoneStatus.NORMAL)
        self.assertEqual(short.duty, duty)
        self.assertIs(controller.step(30 * MINUTE, None).status, ZoneStatus.DEGRADED)
        final = controller.step(60 * MINUTE, None)
        self.assertIs(final.status, ZoneStatus.HANDBACK)
        self.assertEqual(final.setpoint, 20.0)

    def test_no_integration_without_readings(self) -> None:
        controller = ZoneController(ZoneConfig(target=20.0), integral=10.0)
        controller.step(0.0, 19.0)
        integral = controller.snapshot()["integral"]
        controller.step(10 * MINUTE, None)
        self.assertEqual(controller.snapshot()["integral"], integral)

    def test_readings_returning_resume_control(self) -> None:
        controller = ZoneController(ZoneConfig(target=20.0))
        controller.step(0.0, 19.0)
        self.assertIs(controller.step(60 * MINUTE, None).status, ZoneStatus.HANDBACK)
        self.assertIs(controller.step(61 * MINUTE, 19.0).status, ZoneStatus.NORMAL)

    def test_a_long_gap_does_not_inflate_the_integral(self) -> None:
        config = ZoneConfig(target=20.0, pid=PidConfig(kp=0.0, ki=0.001, boost_factor=1.0))
        controller = ZoneController(config)
        controller.step(0.0, 19.0)
        controller.step(24 * 60 * MINUTE, 19.0)
        self.assertLessEqual(controller.snapshot()["integral"], 0.001 * 1.0 * 5 * MINUTE + 1e-9)

    def test_no_integration_while_the_thermostat_acts_on_its_own(self) -> None:
        # Below the closed setpoint the thermostat heats whatever the controller wants.
        config = ZoneConfig(target=21.0, pid=PidConfig(kp=0.0, ki=0.001))
        controller = ZoneController(config)
        controller.step(0.0, 16.0)
        controller.step(MINUTE, 16.0)
        self.assertEqual(controller.snapshot()["integral"], 0.0)

    def test_integration_resumes_inside_the_band(self) -> None:
        config = ZoneConfig(target=21.0, smoothing_s=0.0, pid=PidConfig(kp=0.0, ki=0.001))
        controller = ZoneController(config)
        controller.step(0.0, 20.0)
        controller.step(MINUTE, 20.0)
        self.assertGreater(controller.snapshot()["integral"], 0.0)

    def test_target_change_applies_to_setpoints(self) -> None:
        controller = ZoneController(ZoneConfig(target=20.0))
        controller.target = 21.0
        self.assertEqual(controller.step(0.0, 18.0).setpoint, 24.0)

    def test_state_survives_a_restart(self) -> None:
        controller = ZoneController(ZoneConfig(target=20.0), integral=33.0, carry_s=120.0)
        state = controller.snapshot()
        restored = ZoneController(ZoneConfig(target=20.0), **state)
        self.assertEqual(restored.snapshot(), state)


if __name__ == "__main__":
    unittest.main()
