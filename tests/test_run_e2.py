from __future__ import annotations

import unittest

from democracy_mrta.network import BernoulliLossSampler
from democracy_mrta.optimizer import solve_hungarian_assignment
from experiments.run_e2 import result_row, simulate_methods, summarize_rows


class ConstantLatencySampler:
    def sample_ms(self, key: str) -> float:
        return 10.0


class E2RunnerTests(unittest.TestCase):
    def test_vote_loss_override_is_passed_through_and_grouped(self) -> None:
        cost_matrix = (
            (1.0, 5.0),
            (5.0, 1.0),
            (3.0, 4.0),
        )
        oracle = solve_hungarian_assignment(cost_matrix)
        metrics = []

        for vote_loss in (0.0, 1.0):
            results = simulate_methods(
                cost_matrix=cost_matrix,
                oracle=oracle,
                latency_sampler=ConstantLatencySampler(),
                loss_sampler=BernoulliLossSampler(seed=5),
                p_loss=0.0,
                phase_timeout_ms=10.0,
                p_vote_loss=vote_loss,
            )
            democracy = next(
                result for result in results
                if result.method == "democracy_hungarian"
            )
            metrics.append(
                result_row(
                    seed=5,
                    num_robots=3,
                    num_tasks=2,
                    p_loss=0.0,
                    p_vote_loss=vote_loss,
                    oracle=oracle,
                    result=democracy,
                )
            )

        self.assertEqual(metrics[0]["task_commit_rate"], 1.0)
        self.assertEqual(metrics[1]["task_commit_rate"], 0.0)
        self.assertEqual(metrics[0]["p_loss"], metrics[1]["p_loss"])
        self.assertNotEqual(
            metrics[0]["p_vote_loss"], metrics[1]["p_vote_loss"]
        )

        grouped = summarize_rows(metrics)
        self.assertEqual(len(grouped), 2)
        self.assertEqual(
            sorted(float(row["p_vote_loss"]) for row in grouped),
            [0.0, 1.0],
        )
        self.assertEqual(
            sorted(float(row["mean_task_commit_rate"]) for row in grouped),
            [0.0, 1.0],
        )


if __name__ == "__main__":
    unittest.main()
