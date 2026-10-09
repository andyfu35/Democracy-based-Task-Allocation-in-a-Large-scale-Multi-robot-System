from __future__ import annotations

import unittest

from democracy_mrta.coordination import (
    simulate_democracy_hungarian,
    simulate_full_view_hungarian,
    simulate_leader_hungarian,
)
from democracy_mrta.optimizer import AssignmentSolution


class ConstantSampler:
    def __init__(self, latency_ms: float):
        self.latency_ms = latency_ms

    def sample_ms(self, key: str) -> float:
        return self.latency_ms


class CoordinationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sampler = ConstantSampler(10.0)
        self.assignment = AssignmentSolution(
            assigned_pairs=((0, 0), (1, 1)),
            total_cost=0.0,
        )

    def test_leader_latency_uses_parallel_messages(self) -> None:
        result = simulate_leader_hungarian(
            num_robots=3,
            num_tasks=2,
            sampler=self.sampler,
        )
        self.assertEqual(result.cost_exchange_completion_ms, 10.0)
        self.assertEqual(result.global_agreement_ms, 20.0)
        self.assertEqual(result.message_count, 4)

    def test_full_view_all_to_all_finishes_after_one_parallel_hop(self) -> None:
        result = simulate_full_view_hungarian(
            num_robots=3,
            num_tasks=2,
            sampler=self.sampler,
        )
        self.assertEqual(result.global_agreement_ms, 10.0)
        self.assertEqual(result.message_count, 6)

    def test_democracy_waits_for_quorum_then_commit(self) -> None:
        result = simulate_democracy_hungarian(
            num_robots=3,
            num_tasks=2,
            assignment=self.assignment,
            sampler=self.sampler,
        )
        self.assertEqual(result.cost_exchange_completion_ms, 10.0)
        self.assertEqual(result.actionable_decision_ms, 20.0)
        self.assertEqual(result.global_agreement_ms, 30.0)
        self.assertEqual(result.message_count, 14)


if __name__ == "__main__":
    unittest.main()
