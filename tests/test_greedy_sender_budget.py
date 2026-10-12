"""E9B-2 Greedy pure25 task-retirement hard sender payload cap tests.

These do not modify E9A historical CSVs, global arbitration, or CBAA.
"""
from __future__ import annotations

import unittest

from democracy_mrta.coordination import simulate_democracy_hungarian_retirement
from democracy_mrta.diagnostics import ProtocolError
from democracy_mrta.network import SenderPayloadBudget


COSTS = (
    (1.0, 9.0),
    (2.0, 1.0),
    (3.0, 2.0),
)


class ConstantDelay:
    def sample_ms(self, _key: str) -> float:
        return 10.0


class NoLoss:
    def is_delivered(self, _key: str, _p_loss: float) -> bool:
        return True


class AllLoss:
    def is_delivered(self, _key: str, _p_loss: float) -> bool:
        return False


def run_retirement(*, cap=None, costs=COSTS, p_loss=0.0, loss_sampler=None):
    budget = None if cap is None else SenderPayloadBudget(cap)
    result = simulate_democracy_hungarian_retirement(
        cost_matrix=costs,
        sampler=ConstantDelay(),
        loss_sampler=NoLoss() if loss_sampler is None else loss_sampler,
        p_loss=p_loss,
        p_vote_loss=p_loss,
        phase_timeout_ms=20.0,
        max_rounds=6,
        voting_strategy="greedy_task",
        vote_decision_rule="quarter_plurality",
        vote_repetitions=1,
        send_budget=budget,
    )
    return result, budget


class GreedySenderBudgetTests(unittest.TestCase):
    def check_accounting(self, result, budget):
        events = [
            e for trace in result.rounds for e in trace.coordination.events
        ]
        self.assertLessEqual(result.payload_bytes, budget.limit_bytes)
        self.assertEqual(result.payload_bytes, budget.sent_bytes)
        self.assertEqual(result.logical_message_count, budget.sent_messages)
        self.assertEqual(sum(e.payload_bytes for e in events), budget.sent_bytes)
        self.assertEqual(len(events), budget.sent_messages)
        self.assertEqual(
            {(e.sender_id, e.task_id) for e in events if e.phase == "commit"},
            set(result.assigned_pairs),
        )
        self.assertEqual(len({r for r, _ in result.assigned_pairs}), result.committed_tasks)

    def test_zero_cap_denies_first_cost_without_any_vote_or_commit(self):
        result, budget = run_retirement(cap=0)
        self.check_accounting(result, budget)
        self.assertTrue(result.budget_exhausted)
        self.assertEqual(result.budget_stop_phase, "cost")
        self.assertEqual(result.committed_tasks, 0)
        self.assertEqual(result.remaining_task_ids, (0, 1))
        self.assertEqual(result.active_robot_ids, (0, 1, 2))
        self.assertEqual(budget.denied_messages, 1)
        self.assertEqual(result.budget_stop_diagnostic.owner, "network")
        self.assertEqual(result.budget_stop_diagnostic.function, "reserve_sender_payload")
        self.assertEqual(result.budget_stop_diagnostic.code, "SEND_PAYLOAD_BUDGET_EXHAUSTED")

    def test_each_physical_stage_keeps_only_actual_sent_packets(self):
        for cap, phase, messages in (
            (64, "cost", 2),
            (96, "vote", 3),
            (160, "vote_score_announcement", 5),
            (192, "commit", 6),
        ):
            with self.subTest(cap=cap):
                result, budget = run_retirement(cap=cap)
                self.check_accounting(result, budget)
                self.assertTrue(result.budget_exhausted)
                self.assertEqual(result.budget_stop_phase, phase)
                self.assertEqual(result.logical_message_count, messages)
                self.assertEqual(result.committed_tasks, 0)
                self.assertEqual(result.remaining_task_ids, (0, 1))
                self.assertEqual(result.active_robot_ids, (0, 1, 2))
                self.assertEqual(budget.denied_messages, 1)
                self.assertTrue(all(trace.newly_committed_pairs == () for trace in result.rounds))

    def test_already_committed_task_survives_later_budget_stop(self):
        result, budget = run_retirement(cap=220)
        self.check_accounting(result, budget)
        self.assertTrue(result.budget_exhausted)
        self.assertEqual(result.budget_stop_phase, "vote")
        self.assertEqual(result.assigned_pairs, ((0, 0),))
        self.assertEqual(result.remaining_task_ids, (1,))
        self.assertEqual(result.active_robot_ids, (1, 2))
        self.assertEqual(result.committed_tasks, 1)
        self.assertEqual(len(result.rounds), 2)
        self.assertEqual(result.rounds[0].newly_committed_pairs, ((0, 0),))
        self.assertEqual(result.rounds[1].newly_committed_pairs, ())

    def test_exact_full_cap_agrees_with_unbudgeted_original(self):
        baseline, _ = run_retirement()
        self.assertEqual(baseline.committed_tasks, 2)
        result, budget = run_retirement(cap=baseline.payload_bytes)
        self.check_accounting(result, budget)
        self.assertFalse(result.budget_exhausted)
        self.assertIsNone(result.budget_stop_phase)
        self.assertIsNone(result.budget_stop_diagnostic)
        self.assertEqual(result.assigned_pairs, baseline.assigned_pairs)
        self.assertEqual(result.payload_bytes, baseline.payload_bytes)
        self.assertEqual(
            tuple(e for r in result.rounds for e in r.coordination.events),
            tuple(e for r in baseline.rounds for e in r.coordination.events),
        )
        self.assertEqual((budget.denied_messages, budget.remaining_bytes), (0, 0))

    def test_explicit_none_is_identical_to_legacy_no_budget(self):
        original = simulate_democracy_hungarian_retirement(
            cost_matrix=COSTS,
            sampler=ConstantDelay(),
            loss_sampler=NoLoss(),
            p_loss=0.0, p_vote_loss=0.0,
            phase_timeout_ms=20.0, max_rounds=6,
            voting_strategy="greedy_task",
            vote_decision_rule="quarter_plurality",
            vote_repetitions=1,
        )
        explicit, _ = run_retirement(cap=None)
        self.assertEqual(original, explicit)

    def test_unbudgeted_complete_loss_only_counts_real_commit(self):
        # With N=3 and >25% threshold=1, an actual local self-vote can qualify;
        # all remote Cost/Vote packets are lost but reliable score/Commit remain.
        result, _ = run_retirement(
            costs=((1.0,), (3.0,), (4.0,)),
            p_loss=1.0, loss_sampler=AllLoss(),
        )
        self.assertFalse(result.budget_exhausted)
        self.assertEqual(result.lossy_delivered, 0)
        self.assertEqual(result.committed_tasks, 1)
        self.assertEqual(result.budget_stop_phase, None)
        sent_commits = {
            (event.sender_id, event.task_id)
            for trace in result.rounds for event in trace.coordination.events
            if event.phase == "commit"
        }
        self.assertEqual(sent_commits, set(result.assigned_pairs))

    def test_budget_on_other_algorithm_is_rejected_without_emissions(self):
        for method, rule, repetitions in (
            ("greedy_task", "strict_majority", 1),
            ("hungarian", "strict_majority", 1),
            ("greedy_task", "quarter_plurality", 2),
        ):
            with self.subTest(method=method, rule=rule, repetitions=repetitions):
                budget = SenderPayloadBudget(1000)
                with self.assertRaises(ProtocolError) as ctx:
                    simulate_democracy_hungarian_retirement(
                        cost_matrix=COSTS,
                        sampler=ConstantDelay(),
                        loss_sampler=NoLoss(),
                        p_loss=0.0, p_vote_loss=0.0,
                        phase_timeout_ms=20.0, max_rounds=6,
                        voting_strategy=method, vote_decision_rule=rule,
                        vote_repetitions=repetitions, send_budget=budget,
                    )
                self.assertEqual(
                    ctx.exception.diagnostic.code,
                    "BUDGETED_RETIREMENT_REQUIRES_GREEDY_QUARTER_K1",
                )
                self.assertEqual(budget.sent_messages, 0)


if __name__ == "__main__":
    unittest.main()
