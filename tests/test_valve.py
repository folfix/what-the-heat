import unittest

from custom_components.what_the_heat.core.valve import (
    ValveConfig,
    ValveWatchdog,
    WatchdogConfig,
    WatchdogResult,
    closed_setpoint,
    open_setpoint,
)


class SetpointTest(unittest.TestCase):
    def test_band_around_the_target(self) -> None:
        config = ValveConfig()
        self.assertEqual(open_setpoint(20.0, config), 22.0)
        self.assertEqual(closed_setpoint(20.0, config), 18.0)

    def test_rounded_to_the_device_step(self) -> None:
        config = ValveConfig()
        self.assertEqual(open_setpoint(20.3, config), 22.5)
        self.assertEqual(closed_setpoint(20.3, config), 18.5)

    def test_stays_one_step_below_the_device_maximum(self) -> None:
        self.assertEqual(open_setpoint(34.0, ValveConfig()), 34.5)

    def test_stays_above_the_device_minimum(self) -> None:
        self.assertEqual(closed_setpoint(6.0, ValveConfig()), 5.0)


class WatchdogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.watchdog = ValveWatchdog(WatchdogConfig(check_interval_s=300.0, grace_s=120.0, alert_after=3))
        self.watchdog.command(0.0, 22.0)

    def test_nothing_commanded_is_fine(self) -> None:
        self.assertIs(ValveWatchdog().check(1000.0, 18.0, False, 20.0), WatchdogResult.OK)

    def test_reads_within_the_grace_period_are_ignored(self) -> None:
        self.assertIs(self.watchdog.check(60.0, 18.0, False, 20.0), WatchdogResult.OK)
        self.assertEqual(self.watchdog.mismatches, 0)

    def test_matching_state_is_fine(self) -> None:
        self.assertIs(self.watchdog.check(120.0, 22.0, True, 20.0), WatchdogResult.OK)

    def test_wrong_setpoint_is_resent(self) -> None:
        self.assertIs(self.watchdog.check(120.0, 18.0, False, 20.0), WatchdogResult.RESEND)

    def test_missing_setpoint_is_resent(self) -> None:
        self.assertIs(self.watchdog.check(120.0, None, None, 20.0), WatchdogResult.RESEND)

    def test_correct_setpoint_without_heating_is_detected(self) -> None:
        # An optimistic setpoint in the integration can look right while the relay is off.
        self.assertIs(self.watchdog.check(120.0, 22.0, False, 20.0), WatchdogResult.RESEND)

    def test_heating_above_a_closed_setpoint_is_detected(self) -> None:
        self.watchdog.command(0.0, 18.0)
        self.assertIs(self.watchdog.check(120.0, 18.0, True, 20.0), WatchdogResult.RESEND)

    def test_heating_state_is_not_judged_inside_the_differential(self) -> None:
        self.assertIs(self.watchdog.check(120.0, 22.0, False, 21.9), WatchdogResult.OK)

    def test_alert_after_repeated_mismatches(self) -> None:
        results = [self.watchdog.check(120.0 + index * 300.0, 18.0, False, 20.0) for index in range(4)]
        self.assertEqual(
            results,
            [WatchdogResult.RESEND, WatchdogResult.RESEND, WatchdogResult.ALERT, WatchdogResult.ALERT],
        )

    def test_recovery_clears_mismatches(self) -> None:
        self.watchdog.check(120.0, 18.0, False, 20.0)
        self.assertEqual(self.watchdog.mismatches, 1)
        self.watchdog.check(420.0, 22.0, True, 20.0)
        self.assertEqual(self.watchdog.mismatches, 0)

    def test_checks_are_rate_limited(self) -> None:
        self.watchdog.check(120.0, 18.0, False, 20.0)
        self.watchdog.check(180.0, 18.0, False, 20.0)
        self.assertEqual(self.watchdog.mismatches, 1)


if __name__ == "__main__":
    unittest.main()
