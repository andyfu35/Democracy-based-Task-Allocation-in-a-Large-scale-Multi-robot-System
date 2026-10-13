"""External-observation acceptance tests; no algorithm or network modifications."""
import unittest

from democracy_mrta.diagnostics import ProtocolError
from experiments.p1_feasibility import (FirstFeasibleObserver,
                                       assess_euclidean_assignment,
                                       valid_unique_assignment)


class TestP1Feasibility(unittest.TestCase):
    def test_first_feasible_after_real_native_snapshots(self):
        observer=FirstFeasibleObserver(3)
        before=((0,0),(1,1))
        observer.observe(10.0,before)
        self.assertIsNone(observer.first_feasible_ms)
        observer.observe(20.0,((0,0),(1,1),(2,1)))
        self.assertIsNone(observer.first_feasible_ms)
        first=((0,1),(1,2),(2,0))
        observer.observe(30.0,first)
        observer.observe(40.0,((0,0),(1,1),(2,2)))
        self.assertEqual(observer.first_feasible_ms,30.0)
        self.assertEqual(observer.first_pairs,first)
        self.assertEqual(observer.last_ms,40.0)
        self.assertEqual(observer.observed_phases,4)
        self.assertFalse(valid_unique_assignment(before,3))

    def test_reject_noncausal_timestamp_without_changing_observer_state(self):
        observer=FirstFeasibleObserver(2)
        observer.observe(12.0,((0,0),))
        with self.assertRaises(ProtocolError) as caught:
            observer.observe(11.0,((0,0),(1,1)))
        self.assertEqual(caught.exception.diagnostic.code,"P1_NONCAUSAL_OBSERVER_TIMESTAMP")
        self.assertEqual(observer.last_ms,12.0)
        self.assertIsNone(observer.first_feasible_ms)

    def test_hungarian_cost_is_read_only_and_common(self):
        matrix=((1.,9.),(5.,2.))
        result=assess_euclidean_assignment(matrix,((0,0),(1,1)),3.)
        self.assertEqual(result["feasible"],1)
        self.assertEqual(result["sum_distance_m"],3.)
        self.assertEqual(result["hungarian_ratio"],1.)
        self.assertEqual(result["makespan_s"],2.)
        poor=assess_euclidean_assignment(matrix,((0,1),(1,0)),3.)
        self.assertEqual(poor["hungarian_ratio"],14/3)
        self.assertEqual(assess_euclidean_assignment(matrix,((0,0),(0,1)),3.)["feasible"],0)


if __name__=="__main__":
    unittest.main()
