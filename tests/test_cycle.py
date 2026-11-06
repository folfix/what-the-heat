import unittest

from custom_components.what_the_heat.core.cycle import CycleScheduler

MINUTE = 60.0


def run(scheduler: CycleScheduler, duty: float, minutes: int, start_s: float = 0.0) -> list[bool]:
    return [scheduler.step(start_s + index * MINUTE, duty) for index in range(minutes)]


def runs_of(states: list[bool]) -> list[tuple[bool, int]]:
    """Return (state, length) for each complete run, leaving out the first and last."""
    runs: list[tuple[bool, int]] = []
    for state in states:
        if runs and runs[-1][0] == state:
            runs[-1] = (state, runs[-1][1] + 1)
        else:
            runs.append((state, 1))
    return runs[1:-1]


class DemandChangeTest(unittest.TestCase):
    def test_a_very_low_duty_does_not_keep_the_valve_closed_for_long(self) -> None:
        # A room cooling through its target passes through very low duties on the way.
        scheduler = CycleScheduler()
        run(scheduler, 1.0, 1)
        self.assertFalse(scheduler.is_open)
        states = run(scheduler, 50.0, 60, start_s=MINUTE)
        self.assertEqual(states.index(True), 29)

    def test_a_very_high_duty_does_not_keep_the_valve_open_for_long(self) -> None:
        scheduler = CycleScheduler()
        run(scheduler, 99.0, 1)
        self.assertTrue(scheduler.is_open)
        states = run(scheduler, 50.0, 60, start_s=MINUTE)
        self.assertEqual(states.index(False), 44)

    def test_a_low_duty_is_delivered_by_skipping_cycles(self) -> None:
        states = run(CycleScheduler(), 5.0, 120)
        self.assertEqual(states[:90], [False] * 90)
        self.assertEqual(states[90:96], [True] * 6)
        self.assertFalse(states[96])

    def test_a_high_duty_closes_only_now_and_then(self) -> None:
        states = run(CycleScheduler(), 97.0, 180)
        self.assertTrue(all(states[:150]))
        self.assertEqual(states.count(False), 5)


class CycleSchedulerTest(unittest.TestCase):
    def test_average_matches_duty(self) -> None:
        for duty in (5.0, 10.0, 25.0, 50.0, 75.0, 90.0, 95.0):
            with self.subTest(duty=duty):
                states = run(CycleScheduler(), duty, 60 * 24 * 30)
                # One-minute steps round each opening up, by at most 1/30 of a window.
                self.assertAlmostEqual(sum(states) / len(states) * 100.0, duty, delta=3.4)

    def test_minimum_times_are_respected(self) -> None:
        for duty in (3.0, 8.0, 15.0, 50.0, 85.0, 92.0, 97.0):
            with self.subTest(duty=duty):
                for state, length in runs_of(run(CycleScheduler(), duty, 60 * 24 * 10)):
                    self.assertGreaterEqual(length, 5, f"state {state}")

    def test_full_duty_keeps_the_valve_open(self) -> None:
        self.assertTrue(all(run(CycleScheduler(), 100.0, 600)))

    def test_zero_duty_keeps_the_valve_closed(self) -> None:
        self.assertFalse(any(run(CycleScheduler(), 0.0, 600)))

    def test_zero_demand_closes_after_the_minimum_time(self) -> None:
        scheduler = CycleScheduler()
        run(scheduler, 50.0, 2)
        self.assertTrue(scheduler.is_open)
        states = run(scheduler, 0.0, 30, start_s=2 * MINUTE)
        self.assertEqual(states.index(False), 3)

    def test_full_demand_opens_after_the_minimum_time(self) -> None:
        scheduler = CycleScheduler()
        run(scheduler, 50.0, 17)
        self.assertFalse(scheduler.is_open)
        states = run(scheduler, 100.0, 30, start_s=17 * MINUTE)
        self.assertEqual(states.index(True), 3)

    def test_phase_offset_delays_the_first_cycle(self) -> None:
        scheduler = CycleScheduler(start_s=30 * MINUTE)
        states = run(scheduler, 50.0, 40)
        self.assertEqual(states.index(True), 30)


if __name__ == "__main__":
    unittest.main()
