"""P2D one-shot central Cost evidence and full-info planning gates."""
import unittest

from democracy_mrta.centralized_method import simulate_one_shot_centralized
from democracy_mrta.network import EmpiricalLatencyProfile
from democracy_mrta.optimizer import solve_visible_batched_greedy_assignment


def profile():
    return EmpiricalLatencyProfile(
        "test", "test", "test", "2", "test", "ax_160mhz_6ghz",
        "test", 120.0, 181.0, (10.0, 15.0, 25.0),
    )


COSTS = ((2., 1., 4.), (4., 2., 3.), (9., 3., 1.))
TASKS = ((0., 0.), (1., 0.), (0., 1.))


class CentralizedOneShotTests(unittest.TestCase):
    def test_zero_loss_full_info_matches_greedy(self):
        r = simulate_one_shot_centralized(
            cost_matrix=COSTS, task_positions=TASKS, profile=profile(),
            seed=12, p_loss=0.0,
        )
        expected = solve_visible_batched_greedy_assignment(
            COSTS, frozenset(range(3)),
        ).assigned_pairs
        self.assertEqual(r.assignment, expected)
        self.assertEqual(r.native_success, True)
        self.assertEqual(r.cost_sender_sends, 2)
        self.assertEqual(r.task_coverage, 1.0)
        self.assertEqual(r.commit_sender_sends, 3)
        self.assertEqual(r.decision_sender_sends, 1)

    def test_full_cost_loss_never_uses_hidden_costs(self):
        r = simulate_one_shot_centralized(
            cost_matrix=COSTS, task_positions=TASKS, profile=profile(),
            seed=12, p_loss=1.0,
        )
        self.assertEqual(r.received_robot_ids, (0,))
        self.assertEqual(r.assignment, ((0, 1),))
        self.assertFalse(r.native_success)
        self.assertEqual(r.task_coverage, 1/3)
        self.assertEqual(r.cost_sender_sends, 2)
        self.assertEqual(r.cost_receiver_drops, 2)
        self.assertGreater(r.cost_airtime_ms, 0)
        self.assertGreater(r.native_stop_ms, 0)

    def test_physical_cost_sends_not_refunded_on_full_drop(self):
        a = simulate_one_shot_centralized(
            cost_matrix=COSTS, task_positions=TASKS, profile=profile(),
            seed=12, p_loss=0.0,
        )
        b = simulate_one_shot_centralized(
            cost_matrix=COSTS, task_positions=TASKS, profile=profile(),
            seed=12, p_loss=1.0,
        )
        self.assertEqual(a.cost_sender_bytes, b.cost_sender_bytes)
        self.assertEqual(a.cost_sender_bytes, 2 * (16 + 8*3))
        self.assertAlmostEqual(a.cost_airtime_ms, b.cost_airtime_ms)

    def test_rejects_invalid_inputs(self):
        from democracy_mrta.diagnostics import ProtocolError
        with self.assertRaises(ProtocolError) as err:
            simulate_one_shot_centralized(
                cost_matrix=COSTS, task_positions=TASKS, profile=profile(),
                seed=12, p_loss=-0.1,
            )
        self.assertEqual(err.exception.diagnostic.category, "data")


if __name__ == "__main__":
    unittest.main()
