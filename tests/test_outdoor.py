import unittest

from custom_components.what_the_heat.core.outdoor import OutdoorConfig, OutdoorCorrection

HOUR = 3600.0
DAY = 24 * HOUR


def settled(usual: float = 0.0, now: float | None = None, weight: float = 1.0) -> OutdoorCorrection:
    """A correction that has seen a day at the usual temperature, and now reads `now`."""
    correction = OutdoorCorrection(weight=weight, usual=usual, smoothed=usual if now is None else now, history_s=DAY)
    return correction


class OutdoorCorrectionTest(unittest.TestCase):
    def test_nothing_happens_before_a_day_of_readings(self) -> None:
        correction = OutdoorCorrection(weight=2.0)
        correction.update(-5.0, 0.0)
        correction.update(-5.0, 12 * HOUR)
        self.assertIsNone(correction.difference)
        self.assertEqual(correction.feedforward(), 0.0)

    def test_colder_than_usual_means_more_heat(self) -> None:
        correction = settled(usual=0.0, now=-4.0, weight=1.5)
        self.assertEqual(correction.difference, 4.0)
        self.assertEqual(correction.feedforward(), 6.0)

    def test_warmer_than_usual_means_less_heat(self) -> None:
        self.assertEqual(settled(usual=0.0, now=3.0, weight=1.0).feedforward(), -3.0)

    def test_a_room_too_cold_in_colder_weather_learns_a_larger_weight(self) -> None:
        correction = settled(usual=0.0, now=-4.0, weight=1.0)
        correction.learn(error=0.5, dt_s=HOUR, sun=None)
        self.assertAlmostEqual(correction.weight, 1.0 + OutdoorConfig().rate * 0.5 * 4.0)

    def test_a_room_too_warm_in_colder_weather_learns_a_smaller_weight(self) -> None:
        correction = settled(usual=0.0, now=-4.0, weight=1.0)
        correction.learn(error=-0.5, dt_s=HOUR, sun=None)
        self.assertLess(correction.weight, 1.0)

    def test_the_weight_stays_within_its_limits(self) -> None:
        low = settled(usual=0.0, now=-4.0, weight=0.0)
        low.learn(error=-3.0, dt_s=DAY, sun=None)
        high = settled(usual=0.0, now=-4.0, weight=OutdoorConfig().max_weight)
        high.learn(error=3.0, dt_s=DAY, sun=None)
        self.assertEqual(low.weight, 0.0)
        self.assertEqual(high.weight, OutdoorConfig().max_weight)

    def test_nothing_is_learned_while_the_sun_shines(self) -> None:
        correction = settled(usual=0.0, now=-4.0, weight=1.0)
        correction.learn(error=0.5, dt_s=HOUR, sun=0.5)
        self.assertEqual(correction.weight, 1.0)

    def test_the_usual_temperature_follows_slowly(self) -> None:
        correction = settled(usual=0.0)
        correction.update(-6.0, HOUR)
        self.assertGreater(correction.difference, 4.0)
        for _ in range(72):
            correction.update(-6.0, HOUR)
        self.assertLess(abs(correction.difference), 0.5)

    def test_a_lost_sensor_stops_the_correction_until_it_is_back(self) -> None:
        correction = settled(usual=0.0, now=-4.0, weight=1.0)
        correction.update(None, HOUR)
        self.assertEqual(correction.feedforward(), 4.0)
        correction.update(None, 1.5 * HOUR)
        self.assertEqual(correction.feedforward(), 0.0)
        correction.learn(error=0.5, dt_s=HOUR, sun=None)
        self.assertEqual(correction.weight, 1.0)
        correction.update(-4.0, 60.0)
        self.assertGreater(correction.feedforward(), 0.0)

    def test_reset_keeps_the_measured_temperatures(self) -> None:
        correction = settled(usual=0.0, now=-4.0, weight=2.0)
        correction.reset()
        self.assertEqual(correction.weight, 0.0)
        self.assertEqual(correction.difference, 4.0)

    def test_state_survives_a_restart(self) -> None:
        correction = settled(usual=1.0, now=-2.0, weight=0.7)
        restored = OutdoorCorrection(**correction.snapshot())
        self.assertEqual(restored.snapshot(), correction.snapshot())
        self.assertEqual(restored.feedforward(), correction.feedforward())


if __name__ == "__main__":
    unittest.main()
