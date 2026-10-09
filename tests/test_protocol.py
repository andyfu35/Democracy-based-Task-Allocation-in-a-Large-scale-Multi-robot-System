from __future__ import annotations

import unittest

from democracy_mrta.protocol import (
    Vote,
    quorum_size,
    record_vote,
    run_zero_loss_allocation_epoch,
)
from democracy_mrta.scenario import generate_e0_scenario


class ProtocolTests(unittest.TestCase):
    def test_quorum_is_strict_majority(self) -> None:
        self.assertEqual(quorum_size(1), 1)
        self.assertEqual(quorum_size(2), 2)
        self.assertEqual(quorum_size(3), 2)
        self.assertEqual(quorum_size(100), 51)

    def test_duplicate_vote_is_not_counted(self) -> None:
        ledgers: dict[int, set[int]] = {}
        eligible = frozenset({0, 1, 2})
        vote = Vote(task_id=7, round_id=2, voter_id=0, candidate_id=1)

        first = record_vote(
            vote=vote,
            current_task_id=7,
            current_round_id=2,
            eligible_robots=eligible,
            ledgers_by_candidate=ledgers,
        )
        second = record_vote(
            vote=vote,
            current_task_id=7,
            current_round_id=2,
            eligible_robots=eligible,
            ledgers_by_candidate=ledgers,
        )

        self.assertEqual(first, "ACCEPTED")
        self.assertEqual(second, "DUPLICATE_REJECTED")
        self.assertEqual(ledgers, {1: {0}})

    def test_stale_round_vote_is_rejected(self) -> None:
        ledgers: dict[int, set[int]] = {}
        status = record_vote(
            vote=Vote(task_id=3, round_id=1, voter_id=0, candidate_id=1),
            current_task_id=3,
            current_round_id=2,
            eligible_robots=frozenset({0, 1}),
            ledgers_by_candidate=ledgers,
        )
        self.assertEqual(status, "STALE_REJECTED")
        self.assertEqual(ledgers, {})

    def test_zero_loss_epoch_assigns_each_robot_at_most_once(self) -> None:
        scenario = generate_e0_scenario(seed=42, num_robots=10, num_tasks=5)
        result = run_zero_loss_allocation_epoch(scenario.cost_matrix)
        winners = [robot_id for robot_id, _ in result.assigned_pairs]
        self.assertEqual(len(winners), len(set(winners)))
        self.assertEqual(result.assigned_tasks, 5)

    def test_seed_replay_is_deterministic(self) -> None:
        first = generate_e0_scenario(seed=99, num_robots=10, num_tasks=5)
        second = generate_e0_scenario(seed=99, num_robots=10, num_tasks=5)
        self.assertEqual(first, second)
        self.assertEqual(
            run_zero_loss_allocation_epoch(first.cost_matrix),
            run_zero_loss_allocation_epoch(second.cost_matrix),
        )


if __name__ == "__main__":
    unittest.main()
