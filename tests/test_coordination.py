from __future__ import annotations

import unittest

from democracy_mrta.coordination import (
    BROADCAST_RECEIVER_ID,
    simulate_democracy_hungarian_lossy,
    simulate_full_view_hungarian_lossy,
    simulate_leader_hungarian_lossy,
    simulate_democracy_hungarian,
    simulate_full_view_hungarian,
    simulate_leader_hungarian,
)
from democracy_mrta.network import BernoulliLossSampler
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

    def test_lossy_zero_loss_matches_e1_democracy_timing(self) -> None:
        cost_matrix = (
            (1.0, 5.0),
            (5.0, 1.0),
            (3.0, 4.0),
        )
        zero_loss = simulate_democracy_hungarian_lossy(
            cost_matrix=cost_matrix,
            sampler=self.sampler,
            loss_sampler=BernoulliLossSampler(seed=5),
            p_loss=0.0,
            phase_timeout_ms=10.0,
        )
        e1 = simulate_democracy_hungarian(
            num_robots=3,
            num_tasks=2,
            assignment=self.assignment,
            sampler=self.sampler,
        )

        self.assertEqual(zero_loss.decision_completion_ms, e1.actionable_decision_ms)
        self.assertEqual(zero_loss.global_agreement_ms, e1.global_agreement_ms)
        self.assertEqual(zero_loss.logical_message_count, e1.message_count)
        self.assertTrue(zero_loss.full_assignment_success)

    def test_lossy_full_view_requires_complete_information(self) -> None:
        cost_matrix = (
            (1.0, 5.0),
            (5.0, 1.0),
            (3.0, 4.0),
        )
        result = simulate_full_view_hungarian_lossy(
            cost_matrix=cost_matrix,
            assignment=self.assignment,
            sampler=self.sampler,
            loss_sampler=BernoulliLossSampler(seed=5),
            p_loss=1.0,
            phase_timeout_ms=10.0,
        )

        self.assertFalse(result.full_assignment_success)
        self.assertEqual(result.committed_tasks, 0)
        self.assertEqual(result.task_timeout_count, 2)
        self.assertEqual(result.lossy_delivered, 0)

    def test_lossy_leader_can_return_partial_assignment(self) -> None:
        cost_matrix = (
            (1.0, 5.0),
            (5.0, 1.0),
            (3.0, 4.0),
        )
        result = simulate_leader_hungarian_lossy(
            cost_matrix=cost_matrix,
            sampler=self.sampler,
            loss_sampler=BernoulliLossSampler(seed=5),
            p_loss=1.0,
            phase_timeout_ms=10.0,
        )

        self.assertFalse(result.full_assignment_success)
        self.assertEqual(result.committed_tasks, 1)
        self.assertEqual(result.task_timeout_count, 1)

    def test_lossy_democracy_full_loss_has_no_quorum(self) -> None:
        cost_matrix = (
            (1.0, 5.0),
            (5.0, 1.0),
            (3.0, 4.0),
        )
        result = simulate_democracy_hungarian_lossy(
            cost_matrix=cost_matrix,
            sampler=self.sampler,
            loss_sampler=BernoulliLossSampler(seed=5),
            p_loss=1.0,
            phase_timeout_ms=10.0,
        )

        self.assertFalse(result.full_assignment_success)
        self.assertEqual(result.committed_tasks, 0)
        self.assertEqual(result.task_timeout_count, 2)


if __name__ == "__main__":
    unittest.main()
