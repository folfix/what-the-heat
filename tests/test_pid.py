import unittest

from custom_components.what_the_heat.core.pid import PidConfig, PidController


class PidControllerTest(unittest.TestCase):
    def test_proportional_term(self) -> None:
        output = PidController(PidConfig(kp=50.0, ki=0.0)).update(error=0.5, dt_s=60.0)
        self.assertAlmostEqual(output.duty, 25.0)

    def test_integral_accumulates_over_time(self) -> None:
        controller = PidController(PidConfig(kp=0.0, ki=0.001, boost_factor=1.0))
        for _ in range(60):
            output = controller.update(error=1.0, dt_s=60.0)
        self.assertAlmostEqual(output.integral, 3.6)

    def test_integration_is_faster_far_from_the_target(self) -> None:
        config = PidConfig(kp=0.0, ki=0.001, boost_error=0.3, boost_factor=4.0)
        far = PidController(config).update(error=1.0, dt_s=60.0)
        near = PidController(config).update(error=0.25, dt_s=60.0)
        self.assertAlmostEqual(far.integral, 0.24)
        self.assertAlmostEqual(near.integral, 0.015)

    def test_output_is_limited(self) -> None:
        controller = PidController(PidConfig(kp=50.0, ki=0.0))
        self.assertEqual(controller.update(error=5.0, dt_s=60.0).duty, 100.0)
        self.assertEqual(controller.update(error=-5.0, dt_s=60.0).duty, 0.0)

    def test_no_integration_while_saturated_high(self) -> None:
        controller = PidController(PidConfig(kp=50.0, ki=0.001), integral=20.0)
        for _ in range(1000):
            controller.update(error=3.0, dt_s=60.0)
        self.assertEqual(controller.integral, 20.0)

    def test_no_integration_while_saturated_low(self) -> None:
        controller = PidController(PidConfig(kp=50.0, ki=0.001), integral=20.0)
        for _ in range(1000):
            controller.update(error=-3.0, dt_s=60.0)
        self.assertEqual(controller.integral, 20.0)

    def test_integral_recovers_from_saturation(self) -> None:
        controller = PidController(PidConfig(kp=50.0, ki=0.001), integral=20.0)
        controller.update(error=3.0, dt_s=60.0)
        controller.update(error=-0.1, dt_s=60.0)
        self.assertLess(controller.integral, 20.0)

    def test_integral_stays_within_limits(self) -> None:
        controller = PidController(PidConfig(kp=0.0, ki=1.0, integral_min=0.0, integral_max=50.0))
        for _ in range(10):
            controller.update(error=1.0, dt_s=10.0)
        self.assertEqual(controller.integral, 50.0)

    def test_gain_scale_multiplies_the_output(self) -> None:
        controller = PidController(PidConfig(kp=50.0, ki=0.0))
        self.assertAlmostEqual(controller.update(error=0.5, dt_s=60.0, gain_scale=0.5).duty, 12.5)

    def test_feedforward_is_added(self) -> None:
        controller = PidController(PidConfig(kp=0.0, ki=0.0))
        self.assertAlmostEqual(controller.update(error=0.0, dt_s=60.0, feedforward=30.0).duty, 30.0)


if __name__ == "__main__":
    unittest.main()
