from __future__ import annotations

import unittest
from dataclasses import replace

from democracy_mrta.diagnostics import ProtocolError
from democracy_mrta.metrics import (
    evaluate_e2_vote_audit,
    evaluate_assignment_correctness,
    require_zero_loss_optimality,
)
from democracy_mrta.optimizer import AssignmentSolution, solve_hungarian_assignment
from democracy_mrta.coordination import simulate_democracy_hungarian_lossy
from democracy_mrta.network import BernoulliLossSampler


class MetricsTests(unittest.TestCase):
    def test_zero_loss_equal_costs_pass(self) -> None:
        require_zero_loss_optimality(
            protocol_cost=12.5,
            oracle_cost=12.5,
        )

    def test_zero_loss_nonzero_gap_is_contract_failure(self) -> None:
        with self.assertRaises(ProtocolError) as context:
            require_zero_loss_optimality(
                protocol_cost=12.6,
                oracle_cost=12.5,
            )

        diagnostic = context.exception.diagnostic
        self.assertEqual(diagnostic.owner, "metrics")
        self.assertEqual(diagnostic.function, "require_zero_loss_optimality")
        self.assertEqual(diagnostic.category, "contract")
        self.assertEqual(diagnostic.code, "ZERO_LOSS_OPTIMALITY_MISMATCH")

    def test_assignment_correctness_counts_partial_commits(self) -> None:
        oracle = AssignmentSolution(
            assigned_pairs=((0, 0), (1, 1), (2, 2)),
            total_cost=3.0,
        )

        result = evaluate_assignment_correctness(
            assigned_pairs=((0, 0), (2, 1)),
            oracle_assignment=oracle,
            total_tasks=3,
        )

        self.assertEqual(result.committed_tasks, 2)
        self.assertEqual(result.correct_committed_tasks, 1)
        self.assertEqual(result.incorrect_committed_tasks, 1)
        self.assertAlmostEqual(result.correct_executor_rate, 1 / 3)
        self.assertAlmostEqual(result.correctness_among_committed, 0.5)

    def test_assignment_correctness_empty_commit_has_zero_total_cer(self) -> None:
        oracle = AssignmentSolution(
            assigned_pairs=((0, 0), (1, 1)),
            total_cost=2.0,
        )

        result = evaluate_assignment_correctness(
            assigned_pairs=(),
            oracle_assignment=oracle,
            total_tasks=2,
        )

        self.assertEqual(result.correct_executor_rate, 0.0)
        self.assertTrue(result.correctness_among_committed != result.correctness_among_committed)


    def make_audited_vote_result(self, p_loss: float, capture: bool = True):
        cost_matrix = (
            (1.0, 5.0),
            (5.0, 1.0),
            (3.0, 4.0),
        )

        class ConstantLatencySampler:
            def sample_ms(self, key: str) -> float:
                return 10.0

        result = simulate_democracy_hungarian_lossy(
            cost_matrix=cost_matrix,
            sampler=ConstantLatencySampler(),
            loss_sampler=BernoulliLossSampler(seed=5),
            p_loss=p_loss,
            phase_timeout_ms=10.0,
            capture_vote_audit=capture,
        )
        oracle = solve_hungarian_assignment(cost_matrix)
        return result, oracle

    def test_vote_audit_zero_loss_accounts_for_self_votes_and_unicasts(self) -> None:
        result, oracle = self.make_audited_vote_result(p_loss=0.0)
        audit = evaluate_e2_vote_audit(
            result=result, oracle_assignment=oracle, num_robots=3, num_tasks=2
        )
        self.assertEqual(audit.summary["raw_total_votes"], 6)
        self.assertEqual(audit.summary["raw_correct_votes"], 6)
        self.assertEqual(audit.summary["received_total_votes"], 6)
        self.assertEqual(audit.summary["received_correct_votes"], 6)
        self.assertEqual(audit.summary["remote_vote_attempts"], 4)
        self.assertEqual(audit.summary["remote_vote_delivered"], 4)
        self.assertEqual(audit.summary["self_votes"], 2)
        self.assertEqual(audit.summary["tasks_with_raw_quorum"], 2)
        self.assertEqual(audit.summary["tasks_with_received_quorum"], 2)
        self.assertEqual(audit.summary["committed_tasks"], 2)

    def test_vote_audit_full_loss_retains_only_local_self_votes(self) -> None:
        result, oracle = self.make_audited_vote_result(p_loss=1.0)
        audit = evaluate_e2_vote_audit(
            result=result, oracle_assignment=oracle, num_robots=3, num_tasks=2
        )
        self.assertEqual(audit.summary["raw_total_votes"], 3)
        self.assertEqual(audit.summary["self_votes"], 3)
        self.assertEqual(audit.summary["remote_vote_attempts"], 0)
        self.assertEqual(audit.summary["tasks_with_received_quorum"], 0)
        self.assertEqual(audit.summary["committed_tasks"], 0)

    def test_vote_audit_capture_does_not_change_protocol_execution(self) -> None:
        captured, _ = self.make_audited_vote_result(p_loss=0.3, capture=True)
        uncaptured, _ = self.make_audited_vote_result(p_loss=0.3, capture=False)
        self.assertEqual(captured.assigned_pairs, uncaptured.assigned_pairs)
        self.assertEqual(captured.events, uncaptured.events)
        self.assertEqual(captured.deliveries, uncaptured.deliveries)
        self.assertEqual(captured.decision_completion_ms, uncaptured.decision_completion_ms)
        self.assertEqual(captured.global_agreement_ms, uncaptured.global_agreement_ms)
        self.assertEqual(captured.logical_message_count, uncaptured.logical_message_count)

    def test_vote_audit_rejects_corrupted_protocol_ledger(self) -> None:
        result, oracle = self.make_audited_vote_result(p_loss=0.0)
        corrupted = replace(result, audit_counted_vote_ledgers=())
        with self.assertRaises(ProtocolError) as context:
            evaluate_e2_vote_audit(
                result=corrupted, oracle_assignment=oracle, num_robots=3, num_tasks=2
            )
        self.assertEqual(
            context.exception.diagnostic.code,
            "E2_AUDIT_LEDGER_MISMATCH",
        )

    def test_vote_audit_requires_explicit_capture(self) -> None:
        result, oracle = self.make_audited_vote_result(p_loss=0.0, capture=False)
        with self.assertRaises(ProtocolError) as context:
            evaluate_e2_vote_audit(
                result=result, oracle_assignment=oracle, num_robots=3, num_tasks=2
            )
        self.assertEqual(
            context.exception.diagnostic.code,
            "E2_AUDIT_NOT_CAPTURED",
        )



if __name__ == "__main__":
    unittest.main()
