from __future__ import annotations

import unittest

from democracy_mrta.coordination import (
    BROADCAST_RECEIVER_ID,
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

    def test_leader_latency_uses_unicast_costs_and_one_assignment_broadcast(self) -> None:
        result = simulate_leader_hungarian(
            num_robots=3,
            num_tasks=2,
            sampler=self.sampler,
        )
        self.assertEqual(result.cost_exchange_completion_ms, 10.0)
        self.assertEqual(result.global_agreement_ms, 20.0)
        self.assertEqual(result.message_count, 3)
        self.assertEqual(
            sum(event.receiver_id == BROADCAST_RECEIVER_ID for event in result.events),
            1,
        )

    def test_full_view_uses_one_cost_broadcast_per_robot(self) -> None:
        result = simulate_full_view_hungarian(
            num_robots=3,
            num_tasks=2,
            sampler=self.sampler,
        )
        self.assertEqual(result.global_agreement_ms, 10.0)
        self.assertEqual(result.message_count, 3)
        self.assertTrue(all(event.is_broadcast for event in result.events))

    def test_democracy_waits_for_quorum_then_one_commit_broadcast_per_task(self) -> None:
        result = simulate_democracy_hungarian(
            num_robots=3,
            num_tasks=2,
            assignment=self.assignment,
            sampler=self.sampler,
        )
        self.assertEqual(result.cost_exchange_completion_ms, 10.0)
        self.assertEqual(result.actionable_decision_ms, 20.0)
        self.assertEqual(result.global_agreement_ms, 30.0)

        # 3 cost broadcasts + 4 direct votes + 2 commit broadcasts.
        self.assertEqual(result.message_count, 9)
        self.assertEqual(
            sum(event.phase == "cost" and event.is_broadcast for event in result.events),
            3,
        )
        self.assertEqual(
            sum(event.phase == "vote" and not event.is_broadcast for event in result.events),
            4,
        )
        self.assertEqual(
            sum(event.phase == "commit" and event.is_broadcast for event in result.events),
            2,
        )


if __name__ == "__main__":
    unittest.main()
