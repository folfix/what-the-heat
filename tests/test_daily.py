import unittest

from custom_components.what_the_heat.core.daily import DailyLog

HOUR = 3600.0


class DailyLogTest(unittest.TestCase):
    def test_time_in_band_and_rms(self) -> None:
        log = DailyLog()
        log.add("2026-11-05", HOUR, target=21.0, temperature=21.1)
        log.add("2026-11-05", HOUR, target=21.0, temperature=21.1)
        log.add("2026-11-05", HOUR, target=21.0, temperature=21.1)
        log.add("2026-11-05", HOUR, target=21.0, temperature=20.0)
        today = log.today
        self.assertEqual(today["time_in_band_pct"], 75.0)
        self.assertEqual(today["rms_deviation"], 0.507)
        self.assertAlmostEqual(today["room_mean"], 20.825, delta=0.01)

    def test_a_reading_exactly_at_the_edge_of_the_band_is_inside_it(self) -> None:
        for target, temperature in ((23.0, 23.3), (23.0, 22.7), (21.0, 21.3), (21.0, 20.7)):
            with self.subTest(target=target, temperature=temperature):
                log = DailyLog()
                log.add("2026-11-05", HOUR, target=target, temperature=temperature)
                self.assertEqual(log.today["time_in_band_pct"], 100.0)

    def test_a_reading_beyond_the_band_is_outside_it(self) -> None:
        for temperature in (23.4, 22.6):
            with self.subTest(temperature=temperature):
                log = DailyLog()
                log.add("2026-11-05", HOUR, target=23.0, temperature=temperature)
                self.assertEqual(log.today["time_in_band_pct"], 0.0)

    def test_heating_share_and_longest_closed_period(self) -> None:
        log = DailyLog()
        for is_heating, hours in ((True, 1.0), (False, 2.0), (True, 1.0), (False, 1.0)):
            log.add("2026-11-05", hours * HOUR, target=21.0, is_heating=is_heating)
        today = log.today
        self.assertEqual(today["heating_pct"], 40.0)
        self.assertEqual(today["longest_closed_h"], 2.0)

    def test_unknown_values_stay_empty(self) -> None:
        log = DailyLog()
        log.add("2026-11-05", HOUR, target=21.0)
        today = log.today
        self.assertIsNone(today["time_in_band_pct"])
        self.assertIsNone(today["heating_pct"])
        self.assertIsNone(today["outdoor_mean"])

    def test_pv_energy_and_the_sun_correction(self) -> None:
        log = DailyLog()
        log.add("2026-11-08", HOUR, target=23.0, pv_w=6000.0, sun=-40.0)
        log.add("2026-11-08", HOUR, target=23.0, pv_w=0.0, sun=0.0)
        today = log.today
        self.assertEqual(today["pv_kwh"], 6.0)
        self.assertEqual(today["sun_correction_pct"], -20.0)

    def test_without_pv_there_is_no_energy(self) -> None:
        log = DailyLog()
        log.add("2026-11-08", HOUR, target=23.0)
        self.assertIsNone(log.today["pv_kwh"])

    def test_new_date_closes_the_row(self) -> None:
        log = DailyLog()
        log.add("2026-11-05", HOUR, target=21.0, temperature=21.0, writes=3)
        log.add("2026-11-06", HOUR, target=21.0, temperature=20.0)
        self.assertEqual([row["date"] for row in log.rows], ["2026-11-05"])
        self.assertEqual(log.rows[0]["writes"], 3)
        self.assertEqual(log.today["date"], "2026-11-06")

    def test_old_rows_are_dropped(self) -> None:
        log = DailyLog()
        for day in range(500):
            log.add(f"day-{day}", HOUR, target=21.0)
        self.assertEqual(len(log.rows), 400)
        self.assertEqual(log.rows[-1]["date"], "day-498")

    def test_state_survives_a_restart(self) -> None:
        log = DailyLog()
        log.add("2026-11-05", HOUR, target=21.0, temperature=21.0, is_heating=False)
        log.add("2026-11-06", HOUR, target=21.0, temperature=21.0, is_heating=True, water=34.0, outdoor=3.0, is_active=True)
        restored = DailyLog(**log.snapshot())
        self.assertEqual(restored.rows, log.rows)
        self.assertEqual(restored.today, log.today)
        restored.add("2026-11-06", HOUR, target=21.0, temperature=21.0)
        self.assertEqual(restored.today["hours"], 2.0)

    def test_state_saved_by_an_older_version_loads(self) -> None:
        log = DailyLog()
        log.add("2026-11-06", HOUR, target=21.0, temperature=21.0)
        state = log.snapshot()
        state["current"] |= {"buffer_s": 3600.0, "buffer_sum": 122400.0}
        restored = DailyLog(**state)
        self.assertEqual(restored.today, log.today)


if __name__ == "__main__":
    unittest.main()
