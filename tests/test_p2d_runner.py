"""Frozen P2D no-retry four-algorithm experiment configuration."""
import unittest
from argparse import Namespace
from democracy_mrta.diagnostics import ProtocolError
from experiments.run_p2d_centralized import (
    LOSSES, METHODS, validate_config, summarize, validate_complete_grid,
)


class P2DRunnerTests(unittest.TestCase):
    def test_frozen_methods_and_loss_resolution(self):
        self.assertEqual(METHODS, ("voting","cbaa","cbba","centralized"))
        self.assertEqual(LOSSES, tuple(range(0, 91, 10)))
        args = Namespace(losses=",".join(f"{x/100:.2f}" for x in LOSSES),
                         seeds=100, first_seed=0, formal=True,
                         p2c_voting_zip="first.zip", original_p2_zip="second.zip")
        self.assertEqual(validate_config(args), LOSSES)
        args.seeds = 99
        with self.assertRaises(ProtocolError):
            validate_config(args)

    def test_summary_does_not_invent_partial_quality(self):
        rows = []
        for method in METHODS:
            rows.append({
                "loss_percent": 90, "seed": 0, "method": method,
                "native_success": int(method != "centralized"),
                "final_feasible": int(method != "centralized"),
                "native_stop_ms": 500.0,
                "native_sender_bytes": 25,
                "task_coverage": 0.4 if method == "centralized" else "",
                "quality_vs_full_info_greedy": "" if method == "centralized" else 1.1,
                "native_guard_censored": 0,
                "scene_sha256":"same",
            })
        validate_complete_grid(rows,(90,),0,1,methods=METHODS)
        summary=summarize(rows,(90,))
        central=next(r for r in summary if r["method"]=="centralized")
        self.assertEqual(central["native_complete"],0)
        self.assertEqual(central["quality_sample_count"],0)
        self.assertEqual(central["mean_cost_over_full_info_greedy"],"")
        self.assertEqual(central["mean_task_coverage"],0.4)

    def test_incomplete_method_grid_rejected(self):
        with self.assertRaises(ProtocolError):
            validate_complete_grid([], (0,), 0, 1, methods=METHODS)


if __name__ == "__main__":
    unittest.main()
