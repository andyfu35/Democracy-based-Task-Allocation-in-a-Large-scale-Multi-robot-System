from __future__ import annotations

import unittest

from democracy_mrta.coordination import (
    simulate_democracy_hungarian_lossy,
    simulate_democracy_hungarian_retirement,
)
from democracy_mrta.diagnostics import ProtocolError
from democracy_mrta.network import BernoulliLossSampler
from democracy_mrta.protocol import (
    apply_announced_retirement_commits,
    initialize_retirement_membership,
)


COSTS = (
    (1.0, 10.0),
    (10.0, 1.0),
    (3.0, 4.0),
    (9.0, 8.0),
)


class FixedLatency:
    def sample_ms(self, key: str) -> float:
        return 10.0


class ControlledCostLoss:
    """First round commits task 0 only; second round delivers full costs."""
    def is_delivered(self, key: str, p_loss: float) -> bool:
        if key.startswith("broadcast|cost|") and key.endswith("|round=0"):
            parts = key.split("|")
            sender, receiver = int(parts[2]), int(parts[3])
            return (sender, receiver) in {(0, 1), (0, 2), (1, 0)}
        return True


class FirstRoundBlackout:
    def is_delivered(self, key: str, p_loss: float) -> bool:
        return not (key.startswith("broadcast|cost|") and key.endswith("|round=0"))


class RetirementProtocolTests(unittest.TestCase):
    def test_announced_commit_removes_only_its_robot_and_task(self) -> None:
        first = initialize_retirement_membership(num_robots=4, num_tasks=2)
        second = apply_announced_retirement_commits(
            membership=first,
            announced_pairs=((0, 0),),
        )
        self.assertEqual(first.active_robot_ids, (0, 1, 2, 3))
        self.assertEqual(second.active_robot_ids, (1, 2, 3))
        self.assertEqual(second.pending_task_ids, (1,))
        self.assertEqual(second.committed_pairs, ((0, 0),))
        self.assertEqual(second.epoch_index, 1)
        third = apply_announced_retirement_commits(
            membership=second,
            announced_pairs=((1, 1),),
        )
        self.assertEqual(third.pending_task_ids, ())
        self.assertEqual(third.active_robot_ids, (2, 3))
        self.assertEqual(third.committed_pairs, ((0, 0), (1, 1)))

    def test_ineligible_executor_is_rejected(self) -> None:
        state = initialize_retirement_membership(num_robots=4, num_tasks=2)
        state = apply_announced_retirement_commits(
            membership=state, announced_pairs=((0, 0),),
        )
        with self.assertRaises(ProtocolError) as context:
            apply_announced_retirement_commits(
                membership=state,
                announced_pairs=((0, 1),),
            )
        self.assertEqual(
            context.exception.diagnostic.code, "RETIREMENT_COMMIT_NOT_ELIGIBLE"
        )

    def test_announced_commit_cannot_assign_one_robot_to_multiple_tasks(self) -> None:
        state = initialize_retirement_membership(num_robots=4, num_tasks=2)
        with self.assertRaises(ProtocolError) as context:
            apply_announced_retirement_commits(
                membership=state,
                announced_pairs=((0, 0), (0, 1)),
            )
        self.assertEqual(
            context.exception.diagnostic.code, "DUPLICATE_ROBOT_COMMIT"
        )


class RetirementCoordinationTests(unittest.TestCase):
    def test_executor_exits_after_announcement_and_next_quorum_shrinks(self) -> None:
        result = simulate_democracy_hungarian_retirement(
            cost_matrix=COSTS,
            sampler=FixedLatency(),
            loss_sampler=ControlledCostLoss(),
            p_loss=0.3,
            p_vote_loss=0.0,
            phase_timeout_ms=10.0,
            max_rounds=3,
        )
        self.assertTrue(result.full_assignment_success)
        self.assertEqual(result.assigned_pairs, ((0, 0), (1, 1)))
        self.assertEqual(result.total_cost, 2.0)
        self.assertEqual(len(result.rounds), 2)

        first, second = result.rounds
        self.assertEqual(first.quorum, 3)
        self.assertEqual(first.active_robot_ids, (0, 1, 2, 3))
        self.assertEqual(first.pending_task_ids, (0, 1))
        self.assertEqual(first.newly_committed_pairs, ((0, 0),))
        self.assertEqual(second.quorum, 2)
        self.assertEqual(second.active_robot_ids, (1, 2, 3))
        self.assertEqual(second.pending_task_ids, (1,))
        self.assertEqual(second.newly_committed_pairs, ((1, 1),))
        self.assertEqual(
            [(event.sender_id, event.task_id)
             for event in first.coordination.events if event.phase == "commit"],
            [(0, 0)],
        )
        self.assertFalse(any(
            event.sender_id == 0
            for event in second.coordination.events
        ))
        self.assertFalse(any(
            obs.receiver_id == 0
            for obs in second.coordination.deliveries
        ))
        self.assertTrue(all(
            obs.round_id == 1 for obs in second.coordination.deliveries
        ))
        self.assertGreater(second.elapsed_end_ms, first.elapsed_end_ms)

    def test_retry_uses_new_round_and_can_complete_after_no_quorum(self) -> None:
        result = simulate_democracy_hungarian_retirement(
            cost_matrix=COSTS,
            sampler=FixedLatency(),
            loss_sampler=FirstRoundBlackout(),
            p_loss=0.3,
            p_vote_loss=0.0,
            phase_timeout_ms=10.0,
            max_rounds=2,
        )
        self.assertEqual(result.rounds[0].newly_committed_pairs, ())
        self.assertEqual(result.rounds[0].active_robot_ids, (0, 1, 2, 3))
        self.assertEqual(result.rounds[1].active_robot_ids, (0, 1, 2, 3))
        self.assertTrue(result.full_assignment_success)
        self.assertEqual(result.assigned_pairs, ((0, 0), (1, 1)))

    def test_zero_loss_matches_single_round_e2_exactly(self) -> None:
        reference = simulate_democracy_hungarian_lossy(
            cost_matrix=COSTS,
            sampler=FixedLatency(),
            loss_sampler=BernoulliLossSampler(seed=9),
            p_loss=0.0,
            p_vote_loss=0.0,
            phase_timeout_ms=10.0,
        )
        repeated = simulate_democracy_hungarian_retirement(
            cost_matrix=COSTS,
            sampler=FixedLatency(),
            loss_sampler=BernoulliLossSampler(seed=9),
            p_loss=0.0,
            p_vote_loss=0.0,
            phase_timeout_ms=10.0,
            max_rounds=5,
        )
        self.assertEqual(len(repeated.rounds), 1)
        self.assertEqual(repeated.assigned_pairs, reference.assigned_pairs)
        self.assertEqual(repeated.rounds[0].coordination.events, reference.events)
        self.assertEqual(
            repeated.global_agreement_ms, reference.global_agreement_ms
        )

    def test_one_round_cap_preserves_partial_commit(self) -> None:
        result = simulate_democracy_hungarian_retirement(
            cost_matrix=COSTS,
            sampler=FixedLatency(),
            loss_sampler=ControlledCostLoss(),
            p_loss=0.3,
            p_vote_loss=0.0,
            phase_timeout_ms=10.0,
            max_rounds=1,
        )
        self.assertEqual(result.assigned_pairs, ((0, 0),))
        self.assertEqual(result.remaining_task_ids, (1,))
        self.assertFalse(result.full_assignment_success)

    def test_round_limit_must_be_positive(self) -> None:
        with self.assertRaises(ProtocolError) as context:
            simulate_democracy_hungarian_retirement(
                cost_matrix=COSTS,
                sampler=FixedLatency(),
                loss_sampler=BernoulliLossSampler(seed=9),
                p_loss=0.3,
                p_vote_loss=0.0,
                phase_timeout_ms=10.0,
                max_rounds=0,
            )
        self.assertEqual(
            context.exception.diagnostic.code, "INVALID_RETIREMENT_ROUND_LIMIT"
        )


if __name__ == "__main__":
    unittest.main()
