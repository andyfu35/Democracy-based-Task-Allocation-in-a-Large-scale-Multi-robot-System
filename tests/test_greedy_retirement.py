from __future__ import annotations

import unittest

from democracy_mrta.coordination import (
    simulate_democracy_hungarian_retirement,
    simulate_democracy_hungarian_lossy,
)
from democracy_mrta.diagnostics import ProtocolError
from democracy_mrta.network import BernoulliLossSampler
from democracy_mrta.optimizer import (
    solve_visible_greedy_task,
    solve_all_visible_greedy_task_votes,
    solve_sequential_greedy_reference,
    solve_hungarian_assignment,
)
from experiments.run_e2_retirement import retirement_result_row


class ConstantLatency:
    def sample_ms(self, key: str) -> float:
        return 10.0


class MissingBestCostAtTwoVoters:
    def is_delivered(self, key: str, p_loss: float) -> bool:
        return not (
            key.startswith("broadcast|cost|0|2|")
            or key.startswith("broadcast|cost|0|3|")
        )


class GreedyOptimizerTests(unittest.TestCase):
    def test_visible_greedy_never_uses_hidden_candidate(self) -> None:
        costs = ((1.0,), (3.0,), (4.0,))
        a = solve_visible_greedy_task(costs, {1, 2})
        self.assertEqual(a.assigned_pairs, ((1, 0),))
        self.assertEqual(a.total_cost, 3.0)

    def test_batched_greedy_matches_individual_visible_choices(self) -> None:
        costs = ((1.0,), (2.0,), (3.0,), (4.0,))
        views = (
            frozenset({0, 1, 2, 3}),
            frozenset({1, 2, 3}),
            frozenset({2, 3}),
            frozenset({0, 3}),
        )
        actual = solve_all_visible_greedy_task_votes(costs, views)
        expected = tuple(
            solve_visible_greedy_task(costs, rows) for rows in views
        )
        self.assertEqual(actual, expected)

    def test_batched_greedy_rejects_incorrect_voter_count(self) -> None:
        with self.assertRaises(ProtocolError) as context:
            solve_all_visible_greedy_task_votes(
                ((1.0,), (2.0,)),
                (frozenset({0}),),
            )
        self.assertEqual(
            context.exception.diagnostic.code, "GREEDY_LOCAL_VIEW_COUNT_MISMATCH"
        )

    def test_visible_greedy_uses_stable_tie_rule(self) -> None:
        costs = ((2.0,), (2.0,), (2.0,))
        self.assertEqual(
            solve_visible_greedy_task(costs, {2, 1}).assigned_pairs,
            ((1, 0),),
        )

    def test_visible_greedy_rejects_multiple_tasks(self) -> None:
        costs = ((1.0, 5.0), (2.0, 4.0))
        with self.assertRaises(ProtocolError) as context:
            solve_visible_greedy_task(costs, {0, 1})
        self.assertEqual(
            context.exception.diagnostic.code, "GREEDY_REQUIRES_ONE_TASK"
        )

    def test_greedy_is_not_hungarian_and_global_optimum_is_a_separate_metric(self) -> None:
        costs = ((1.0, 2.0), (2.0, 100.0))
        greedy = solve_sequential_greedy_reference(costs)
        hungarian = solve_hungarian_assignment(costs)
        self.assertEqual(greedy.assigned_pairs, ((0, 0), (1, 1)))
        self.assertEqual(greedy.total_cost, 101.0)
        self.assertEqual(hungarian.total_cost, 4.0)


class GreedyRetirementTests(unittest.TestCase):
    def test_zero_loss_greedy_commits_one_task_then_retires_executor(self) -> None:
        costs = ((1.0, 2.0), (2.0, 100.0))
        result = simulate_democracy_hungarian_retirement(
            cost_matrix=costs,
            sampler=ConstantLatency(),
            loss_sampler=BernoulliLossSampler(seed=8),
            p_loss=0.0,
            p_vote_loss=0.0,
            phase_timeout_ms=10.0,
            max_rounds=3,
            voting_strategy="greedy_task",
        )
        self.assertTrue(result.full_assignment_success)
        self.assertEqual(result.method, "democracy_greedy_retirement")
        self.assertEqual(result.assigned_pairs, ((0, 0), (1, 1)))
        self.assertEqual(result.total_cost, 101.0)
        self.assertEqual(len(result.rounds), 2)
        a, b = result.rounds
        self.assertEqual(a.voted_task_id, 0)
        self.assertEqual(a.quorum, 2)
        self.assertEqual(a.pending_task_ids, (0, 1))
        self.assertEqual(a.newly_committed_pairs, ((0, 0),))
        self.assertEqual(b.voted_task_id, 1)
        self.assertEqual(b.quorum, 1)
        self.assertEqual(b.active_robot_ids, (1,))
        self.assertEqual(b.pending_task_ids, (1,))
        self.assertEqual(b.newly_committed_pairs, ((1, 1),))
        self.assertEqual(
            sum(event.phase == "cost" for round_ in result.rounds
                for event in round_.coordination.events),
            2,
        )
        self.assertFalse(any(e.phase == "cost" for e in b.coordination.events))
        self.assertFalse(any(e.sender_id == 0 for e in b.coordination.events))
        self.assertTrue(all(
            event.round_id == 1 for event in b.coordination.events
        ))

    def test_no_quorum_rotates_task_and_later_commit_excludes_robot(self) -> None:
        costs = (
            (1.0, 4.0),
            (2.0, 1.0),
            (3.0, 3.0),
            (4.0, 4.0),
        )
        result = simulate_democracy_hungarian_retirement(
            cost_matrix=costs,
            sampler=ConstantLatency(),
            loss_sampler=MissingBestCostAtTwoVoters(),
            p_loss=0.3,
            p_vote_loss=0.0,
            phase_timeout_ms=10.0,
            max_rounds=3,
            voting_strategy="greedy_task",
        )
        self.assertEqual(len(result.rounds), 3)
        one, two, three = result.rounds
        self.assertEqual(
            (one.voted_task_id, two.voted_task_id, three.voted_task_id),
            (0, 1, 0),
        )
        self.assertEqual(one.newly_committed_pairs, ())
        self.assertEqual(two.newly_committed_pairs, ((1, 1),))
        self.assertEqual(three.active_robot_ids, (0, 2, 3))
        self.assertEqual(three.quorum, 2)
        self.assertEqual(three.newly_committed_pairs, ((2, 0),))
        self.assertEqual(result.assigned_pairs, ((2, 0), (1, 1)))
        self.assertTrue(result.full_assignment_success)
        self.assertFalse(any(e.phase == "cost" for e in two.coordination.events))
        self.assertFalse(any(e.phase == "cost" for e in three.coordination.events))
        self.assertFalse(any(
            obs.receiver_id == 1 for obs in three.coordination.deliveries
        ))

    def test_first_greedy_vote_has_no_hungarian_coupling(self) -> None:
        costs = ((1.0, 2.0), (2.0, 100.0))
        result = simulate_democracy_hungarian_lossy(
            cost_matrix=((1.0,), (2.0,)),
            sampler=ConstantLatency(),
            loss_sampler=BernoulliLossSampler(seed=1),
            p_loss=0.0,
            p_vote_loss=0.0,
            phase_timeout_ms=10.0,
            voting_strategy="greedy_task",
        )
        self.assertEqual(result.method, "democracy_greedy")
        self.assertEqual(result.assigned_pairs, ((0, 0),))

    def test_all_vote_loss_blocks_commits_without_cost_resend(self) -> None:
        costs = ((1.0,), (2.0,), (3.0,))
        result = simulate_democracy_hungarian_retirement(
            cost_matrix=costs,
            sampler=ConstantLatency(),
            loss_sampler=BernoulliLossSampler(seed=9),
            p_loss=0.0,
            p_vote_loss=1.0,
            phase_timeout_ms=10.0,
            max_rounds=3,
            voting_strategy="greedy_task",
        )
        self.assertEqual(result.committed_tasks, 0)
        self.assertEqual(len(result.rounds), 3)
        self.assertEqual(result.remaining_task_ids, (0,))
        self.assertEqual(
            [r.voted_task_id for r in result.rounds], [0, 0, 0]
        )
        self.assertFalse(any(
            e.phase == "cost" for r in result.rounds[1:]
            for e in r.coordination.events
        ))

    def test_round_limit_of_one_leaves_other_tasks_pending(self) -> None:
        costs = ((1.0, 2.0), (2.0, 1.0))
        result = simulate_democracy_hungarian_retirement(
            cost_matrix=costs,
            sampler=ConstantLatency(),
            loss_sampler=BernoulliLossSampler(seed=8),
            p_loss=0.0,
            p_vote_loss=0.0,
            phase_timeout_ms=10.0,
            max_rounds=1,
            voting_strategy="greedy_task",
        )
        self.assertEqual(result.committed_tasks, 1)
        self.assertEqual(result.remaining_task_ids, (1,))
        self.assertFalse(result.full_assignment_success)

    def test_result_metrics_separate_two_oracles_at_zero_loss(self) -> None:
        costs = ((1.0, 2.0), (2.0, 100.0))
        result = simulate_democracy_hungarian_retirement(
            cost_matrix=costs,
            sampler=ConstantLatency(),
            loss_sampler=BernoulliLossSampler(seed=8),
            p_loss=0.0,
            p_vote_loss=0.0,
            phase_timeout_ms=10.0,
            max_rounds=3,
            voting_strategy="greedy_task",
        )
        row = retirement_result_row(
            seed=8, robots=2, tasks=2,
            p_cost_loss=0.0, p_vote_loss=0.0, max_rounds=3,
            oracle=solve_hungarian_assignment(costs),
            greedy_oracle=solve_sequential_greedy_reference(costs),
            result=result, git_sha="test", timestamp="2026-test",
        )
        self.assertEqual(row["greedy_correct_executor_rate"], 1.0)
        self.assertEqual(row["greedy_gap_percent_successful"], 0.0)
        self.assertEqual(row["correct_executor_rate"], 0.0)
        self.assertEqual(row["optimal_solution"], 0)
        self.assertGreater(row["optimality_gap_percent_successful"], 0.0)


if __name__ == "__main__":
    unittest.main()
