from __future__ import annotations

import unittest

from democracy_mrta.diagnostics import ProtocolError
from democracy_mrta.metrics import (
    evaluate_assignment_correctness,
    require_zero_loss_optimality,
)
from democracy_mrta.optimizer import AssignmentSolution


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


if __name__ == "__main__":
    unittest.main()
