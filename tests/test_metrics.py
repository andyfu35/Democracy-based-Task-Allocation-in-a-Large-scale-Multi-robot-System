from __future__ import annotations

import unittest

from democracy_mrta.diagnostics import ProtocolError
from democracy_mrta.metrics import require_zero_loss_optimality


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


if __name__ == "__main__":
    unittest.main()
