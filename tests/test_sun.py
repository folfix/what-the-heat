import unittest

from custom_components.what_the_heat.core.sun import HOURS, SolarConfig, SolarProfile, SunSignal

DAY_S = 86400.0
HOUR = 3600.0
SUNNY_HOURS = range(8, 15)


def live_day(
    profile: SolarProfile,
    date: str,
    deviation: float,
    sun: float = 1.0,
    deviation_hours: range = range(10, 17),
) -> None:
    """One day: sun during SUNNY_HOURS, and the given deviation from the target during deviation_hours."""
    for hour in range(HOURS):
        profile.add(date, hour, HOUR, sun if hour in SUNNY_HOURS else 0.0, deviation if hour in deviation_hours else 0.0)


def close_day(profile: SolarProfile, date: str = "next") -> None:
    profile.add(date, 0, 0.0, None, None)


class SunSignalTest(unittest.TestCase):
    def test_share_of_the_highest_power_seen(self) -> None:
        signal = SunSignal()
        self.assertEqual(signal.update(4000.0, 0.0), 1.0)
        self.assertAlmostEqual(signal.update(1000.0, 60.0), 0.25, places=3)

    def test_unknown_power_gives_no_share(self) -> None:
        self.assertIsNone(SunSignal().update(None, 0.0))

    def test_little_power_without_a_reference_is_no_sun(self) -> None:
        self.assertEqual(SunSignal().update(50.0, 0.0), 0.0)

    def test_negative_power_counts_as_none(self) -> None:
        signal = SunSignal()
        signal.update(4000.0, 0.0)
        self.assertEqual(signal.update(-20.0, 60.0), 0.0)

    def test_full_sun_fades_so_that_a_lower_sun_reaches_it_again(self) -> None:
        signal = SunSignal()
        signal.update(4000.0, 0.0)
        self.assertAlmostEqual(signal.update(2000.0, 30 * DAY_S), 1.0, places=3)

    def test_state_survives_a_restart(self) -> None:
        signal = SunSignal()
        signal.update(4000.0, 0.0)
        restored = SunSignal(**signal.snapshot())
        self.assertAlmostEqual(restored.update(1000.0, 60.0), 0.25, places=3)


class SolarProfileTest(unittest.TestCase):
    def test_a_room_warm_after_the_sun_learns_to_need_less_heat_then(self) -> None:
        profile = SolarProfile()
        live_day(profile, "1", deviation=1.0)
        close_day(profile)
        for hour in SUNNY_HOURS:
            self.assertGreater(profile.values[hour], 0.0)
        self.assertEqual(profile.values[3], 0.0)

    def test_a_room_cold_after_the_sun_learns_to_need_more_again(self) -> None:
        profile = SolarProfile(values=[50.0] * HOURS)
        live_day(profile, "1", deviation=-0.5)
        close_day(profile)
        self.assertLess(profile.values[10], 50.0)

    def test_values_stay_within_their_limits(self) -> None:
        config = SolarConfig()
        low = SolarProfile(values=[1.0] * HOURS)
        high = SolarProfile(values=[config.max_value] * HOURS)
        live_day(low, "1", deviation=-3.0)
        live_day(high, "1", deviation=3.0)
        close_day(low)
        close_day(high)
        self.assertEqual(min(low.values), 0.0)
        self.assertEqual(max(high.values), config.max_value)

    def test_it_acts_only_after_enough_sunny_days(self) -> None:
        profile = SolarProfile()
        for day in range(SolarConfig().min_sunny_days):
            self.assertFalse(profile.active)
            self.assertEqual(profile.feedforward(10, 1.0), 0.0)
            live_day(profile, str(day), deviation=1.0)
        close_day(profile)
        self.assertTrue(profile.active)
        self.assertLess(profile.feedforward(10, 1.0), 0.0)

    def test_a_dull_day_does_not_count_as_sunny(self) -> None:
        profile = SolarProfile()
        live_day(profile, "1", deviation=1.0, sun=0.2)
        close_day(profile)
        self.assertEqual(profile.sunny_days, 0)

    def test_the_change_follows_the_share_of_sun(self) -> None:
        profile = SolarProfile(values=[40.0] * HOURS, sunny_days=SolarConfig().min_sunny_days)
        self.assertEqual(profile.feedforward(10, 0.5), -20.0)
        self.assertEqual(profile.feedforward(10, 0.0), 0.0)
        self.assertEqual(profile.feedforward(10, None), 0.0)

    def test_an_hour_with_too_little_data_is_left_out(self) -> None:
        profile = SolarProfile()
        profile.add("1", 10, 10 * 60.0, 1.0, 0.0)
        profile.add("1", 12, HOUR, 0.0, 2.0)
        close_day(profile)
        self.assertEqual(profile.values, (0.0,) * HOURS)

    def test_reset_forgets_everything(self) -> None:
        profile = SolarProfile(values=[40.0] * HOURS, sunny_days=5)
        live_day(profile, "1", deviation=1.0)
        profile.reset()
        close_day(profile)
        self.assertEqual(profile.values, (0.0,) * HOURS)
        self.assertEqual(profile.sunny_days, 0)

    def test_state_survives_a_restart_in_the_middle_of_a_day(self) -> None:
        profile = SolarProfile()
        restored = SolarProfile()
        live_day(profile, "1", deviation=1.0)
        live_day(restored, "1", deviation=1.0)
        restored = SolarProfile(**restored.snapshot())
        close_day(profile)
        close_day(restored)
        self.assertEqual(restored.values, profile.values)
        self.assertEqual(restored.sunny_days, profile.sunny_days)


if __name__ == "__main__":
    unittest.main()
