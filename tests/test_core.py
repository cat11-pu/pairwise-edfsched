"""edfsched.core 的验收测试。

只描述期望行为，覆盖可调度性判定、区间需求、调度统计、边界输入与不变量。
"""

import unittest
from fractions import Fraction

from edfsched import (
    TaskSpec,
    demand,
    hyperperiod,
    is_schedulable,
    simulate,
    utilization,
)


def spec(name, cost, period, deadline=None, offset=0):
    """构造一个任务描述。"""
    return TaskSpec(name, cost, period, deadline, offset)


def names(result):
    """取执行轨迹里的任务名序列。"""
    return [step["task"] for step in result.trace]


class UtilizationTests(unittest.TestCase):

    def test_utilization_is_an_exact_fraction(self):
        self.assertIsInstance(utilization([spec("a", 1, 3)]), Fraction)
        self.assertEqual(
            utilization([spec("a", 2, 3), spec("b", 1, 6)]), Fraction(5, 6))
        self.assertEqual(
            utilization([spec("a", 1, 3), spec("b", 1, 2)]), Fraction(5, 6))
        self.assertEqual(
            utilization([spec("a", 1, 2), spec("b", 1, 3), spec("c", 1, 6)]),
            Fraction(1))
        self.assertEqual(utilization([]), Fraction(0))

    def test_utilization_boundary_verdicts(self):
        full_a = [spec("a", 1, 2), spec("b", 1, 3), spec("c", 1, 6)]
        full_b = [spec("a", 2, 3), spec("b", 1, 6), spec("c", 1, 6)]
        self.assertTrue(is_schedulable(full_a))
        self.assertTrue(is_schedulable(full_b))
        overloaded = [spec("a", 2, 3), spec("b", 1, 3), spec("c", 1, 3)]
        self.assertFalse(is_schedulable(overloaded))


class SchedulabilityTests(unittest.TestCase):

    def test_constrained_deadline_set_is_infeasible_at_full_utilization(self):
        tight = [spec("a", 2, 5, 3), spec("b", 3, 5, 4)]
        self.assertFalse(is_schedulable(tight))
        result = simulate(tight, horizon=5)
        self.assertEqual(result.miss_count, 1)
        self.assertEqual([job.task.name for job in result.misses], ["b"])
        self.assertEqual(result.busy, 4)
        self.assertEqual(result.idle, 1)

        roomy = [spec("a", 2, 5, 4), spec("b", 1, 5, 4)]
        self.assertTrue(is_schedulable(roomy))
        self.assertEqual(simulate(roomy, horizon=5).miss_count, 0)

    def test_demand_and_late_overload_need_the_full_interval(self):
        short = [spec("a", 2, 5, 3), spec("b", 3, 5, 4)]
        self.assertEqual(demand(short, 3), 2)
        self.assertEqual(demand(short, 4), 5)
        self.assertEqual(demand(short, 0), 0)
        self.assertEqual(demand(short, -3), 0)

        late = [spec("a", 3, 5, 4), spec("b", 3, 8, 6)]
        self.assertEqual(demand(late, 14), 15)
        self.assertFalse(is_schedulable(late))
        self.assertGreaterEqual(simulate(late, horizon=40).miss_count, 1)

    def test_hyperperiod_is_the_least_common_multiple(self):
        pair = [spec("a", 1, 4), spec("b", 1, 6)]
        self.assertEqual(hyperperiod(pair), 12)
        self.assertEqual(
            hyperperiod([spec("a", 1, 2), spec("b", 1, 3), spec("c", 1, 7)]),
            42)
        self.assertEqual(hyperperiod([]), 1)

        result = simulate(pair)
        self.assertEqual(result.horizon, 12)
        self.assertEqual(len(result.jobs), 5)


class SimulationTests(unittest.TestCase):

    def test_completion_at_the_deadline_is_on_time(self):
        result = simulate([spec("busy", 5, 5, 5)], horizon=10)
        self.assertEqual(result.miss_count, 0)
        self.assertEqual(result.misses, [])
        self.assertEqual([job.finished_at for job in result.jobs], [5, 10])
        self.assertEqual(result.responses["busy"], [5, 5])
        self.assertEqual(result.busy, 10)
        self.assertEqual(result.idle, 0)
        self.assertEqual(len(result.trace), 10)

    def test_deadline_ties_are_broken_deterministically(self):
        tied = [spec("zulu", 2, 4, 4), spec("alpha", 2, 4, 4)]
        result = simulate(tied, horizon=8)
        self.assertEqual(names(result),
                         ["alpha", "alpha", "zulu", "zulu",
                          "alpha", "alpha", "zulu", "zulu"])
        self.assertEqual([job.finished_at for job in result.jobs], [4, 2, 8, 6])
        self.assertEqual(result.busy, 8)
        self.assertEqual(result.idle, 0)

    def test_preemption_count_ignores_completed_jobs(self):
        mixed = [spec("low", 3, 6, 6), spec("high", 1, 3, 3, offset=1)]
        result = simulate(mixed, horizon=6)
        self.assertEqual(names(result), ["low", "high", "low", "low", "high"])
        self.assertEqual(result.preemptions, 1)
        self.assertEqual(result.busy, 5)
        self.assertEqual(result.idle, 1)
        self.assertEqual(result.miss_count, 0)


class InputValidationTests(unittest.TestCase):

    def test_invalid_specs_and_empty_sets_are_rejected(self):
        self.assertRaises(ValueError, spec, "a", 0, 5)
        self.assertRaises(ValueError, spec, "a", -2, 5)
        self.assertRaises(ValueError, spec, "a", 1, 0)
        self.assertRaises(ValueError, spec, "a", 1, 5, 0)
        self.assertRaises(ValueError, spec, "a", 1, 5, 6)
        self.assertRaises(ValueError, spec, "", 1, 5)
        self.assertRaises(ValueError, spec, "a", 1, 5, 5, -1)
        self.assertRaises(TypeError, spec, "a", 1.5, 5)
        self.assertRaises(TypeError, spec, "a", 1, True)

        self.assertEqual(utilization([]), Fraction(0))
        self.assertEqual(hyperperiod([]), 1)
        self.assertEqual(demand([], 10), 0)
        self.assertTrue(is_schedulable([]))

        empty = simulate([])
        self.assertEqual(empty.horizon, 1)
        self.assertEqual(empty.trace, [])
        self.assertEqual(empty.busy, 0)
        self.assertEqual(empty.idle, 1)
        self.assertEqual(empty.miss_count, 0)

        self.assertRaises(ValueError, simulate, [spec("a", 1, 2)], -1)
        self.assertRaises(TypeError, simulate, [object()])
        self.assertRaises(TypeError, utilization, ["a"])


class RegressionTests(unittest.TestCase):

    def test_end_to_end_schedule_and_accounting(self):
        feasible = [spec("sensor", 1, 4, 4), spec("ctrl", 2, 8, 8)]
        self.assertTrue(is_schedulable(feasible))
        result = simulate(feasible, horizon=8)
        self.assertEqual(names(result), ["sensor", "ctrl", "ctrl", "sensor"])
        self.assertEqual(result.busy, 4)
        self.assertEqual(result.idle, 4)
        self.assertEqual(result.busy + result.idle, result.horizon)
        self.assertEqual(result.miss_count, 0)
        self.assertEqual(result.preemptions, 0)
        self.assertEqual(len(result.jobs), 3)
        executed = sum(job.task.cost - job.remaining for job in result.jobs)
        self.assertEqual(executed, result.busy)
        for job in result.jobs:
            self.assertIsNotNone(job.finished_at)
            self.assertLessEqual(job.finished_at, job.deadline)

        tied = [spec("zulu", 2, 4, 4), spec("alpha", 2, 4, 4)]
        self.assertEqual(names(simulate(tied, horizon=8)),
                         ["alpha", "alpha", "zulu", "zulu",
                          "alpha", "alpha", "zulu", "zulu"])


if __name__ == "__main__":
    unittest.main()
